# QA Agent Flow - Browser-Use → LangGraph Mapping

## 🔍 Browser-Use Architecture (Verified)

### Single Step Execution in Agent.step()
```python
async def step(self):
    # Phase 1: Get browser state
    browser_state_summary = await browser_session.get_browser_state_summary(
        include_screenshot=True,
        include_recent_events=True
    )
    # Returns: BrowserStateSummary with dom_state, screenshot, url, tabs

    # Phase 2: Get LLM decision
    model_output = await llm.ainvoke(messages)
    # Returns: AgentOutput with thinking + list[ActionModel]

    # Phase 3: Execute actions
    results = await multi_act(model_output.action)
    # Calls: tools.act(action, browser_session) for each action
    # Returns: list[ActionResult]
```

### Key Browser-Use Components

#### 1. **BrowserSession.get_browser_state_summary()**
- Dispatches `BrowserStateRequestEvent` to event bus
- **DOMWatchdog** handles event:
  - Takes screenshot via CDP
  - Gets DOM snapshot via CDP
  - Calls **DomService** to process DOM
  - Returns `BrowserStateSummary`

**BrowserStateSummary Structure:**
```python
{
    "url": "https://example.com",
    "title": "Example",
    "tabs": [...],
    "screenshot": "base64...",  # Optional for vision models
    "dom_state": {
        "selector_map": {
            0: DOMElement(tag="button", text="Login", xpath="//button[@id='login']"),
            1: DOMElement(tag="input", text="", xpath="//input[@name='email']"),
            ...
        },
        "element_tree": "...",  # Human-readable tree for LLM
    }
}
```

#### 2. **DomService Processing**
- Gets raw CDP DOM snapshot
- Builds element tree with accessibility info
- Filters interactive elements (clickable, editable)
- Assigns sequential indices to elements
- Generates `selector_map`: `{index → DOMElement}`
- Creates `element_tree`: Text representation for LLM

#### 3. **Tools.act(action, browser_session)**
- Validates action type
- Calls `registry.execute_action(action_name, params, browser_session)`
- Registry maps action to implementation:
  - `go_to_url` → `browser_session.navigate_to(url)`
  - `click_element` → `browser_session.actor.page.click(index)`
  - `input_text` → `browser_session.actor.page.type(index, text)`
- Returns `ActionResult(extracted_content, error, is_done)`

#### 4. **Actor Layer**
- `actor.page.click(index)`:
  1. Gets element from cached selector_map
  2. Scrolls element into view via CDP
  3. Waits for element to be clickable
  4. Clicks via CDP Input.dispatchMouseEvent
  5. Waits for any navigation/changes
- `actor.page.type(index, text)`:
  1. Clicks element first (focus)
  2. Types text via CDP Input.dispatchKeyEvent
  3. Validates input appeared

---

## 🔄 Our LangGraph Flow (Corrected)

### Node Sequence with Browser-Use Integration

```
START
  ↓
INIT (new node needed)
  ↓
THINK
  ↓
ACT
  ↓
VERIFY
  ↓
ROUTER → [continue → THINK] | [done → REPORT]
  ↓
REPORT
  ↓
END
```

---

## 1️⃣ INIT Node (NEW - Currently Missing!)

**Purpose**: Initialize browser session at workflow start

**Current Issue**: We create browser session in workflow.py but don't pass it properly

**Implementation Needed**:
```python
async def init_node(state: QAAgentState) -> Dict[str, Any]:
    """Initialize browser session for the workflow"""
    from qa_agent.utils.browser_manager import create_browser_session

    # Create session
    session_id, session = await create_browser_session(
        start_url=state.get("start_url")
    )

    # Navigate to start URL if provided
    if state.get("start_url"):
        await session.navigate_to(state["start_url"])

    return {
        "browser_session_id": session_id,
        "current_url": session.current_page.url if session.current_page else None,
    }
```

---

## 2️⃣ THINK Node

**Input**:
- `browser_session_id` (from state)
- Task description
- History of previous steps

**Process**:

### Step 1: Get Browser Session
```python
from qa_agent.utils import get_session

session = get_session(state.browser_session_id)
if not session:
    raise ValueError("Browser session not found")
```

### Step 2: Get Browser State (CRITICAL!)
```python
# This is what browser-use does!
browser_state_summary = await session.get_browser_state_summary(
    include_screenshot=False,  # Set True if using vision model
    include_recent_events=False
)

# browser_state_summary contains:
# - url: current URL
# - title: page title
# - tabs: list of open tabs
# - dom_state.selector_map: {index: DOMElement}
# - dom_state.element_tree: formatted text for LLM
```

### Step 3: Format LLM Prompt
```python
from qa_agent.prompts.prompt_builder import build_system_prompt

# Extract interactive elements from DOM
elements_text = browser_state_summary.dom_state.element_tree
# OR manually format:
elements_list = []
for idx, elem in browser_state_summary.dom_state.selector_map.items():
    elements_list.append(f"[{idx}] {elem.tag} - {elem.text or elem.attributes}")

prompt = f"""
Current Page: {browser_state_summary.url}
Title: {browser_state_summary.title}

Interactive Elements:
{elements_text}

Task: {state.task}

Previous Steps: {state.history}

Think about the next action needed and provide your plan.
"""
```

### Step 4: Call LLM
```python
from langchain_openai import ChatOpenAI

llm = ChatOpenAI(model=settings.llm_model)
response = await llm.ainvoke([
    {"role": "system", "content": build_system_prompt()},
    {"role": "user", "content": prompt}
])

# Parse response into actions
planned_actions = parse_llm_action_plan(response.content)
```

**Output**:
```python
{
    "planned_actions": [
        {
            "action": "click_element",
            "index": 42,
            "reasoning": "Click the login button found at index 42"
        }
    ],
    "thinking": "I need to click the login button to proceed",
    "dom_snapshot": browser_state_summary.dom_state.selector_map  # Cache for ACT node
}
```

---

## 3️⃣ ACT Node

**Input**:
- `browser_session_id`
- `planned_actions` (from THINK)
- `dom_snapshot` (cached selector_map from THINK)

**Process**:

### Step 1: Get Session & Initialize Tools
```python
from qa_agent.tools.service import Tools

session = get_session(state.browser_session_id)
tools = Tools(browser_session=session)  # browser-use Tools!
```

### Step 2: Execute Actions Sequentially
```python
action_results = []

for action in state.planned_actions:
    # Convert our action dict to browser-use ActionModel
    from qa_agent.tools.views import (
        ClickElementAction,
        InputTextAction,
        NavigateAction
    )

    # Map action type to ActionModel
    if action["action"] == "click_element":
        action_model = ActionModel(
            click_element=ClickElementAction(
                index=action["index"]
            )
        )
    elif action["action"] == "input_text":
        action_model = ActionModel(
            input_text=InputTextAction(
                index=action["index"],
                text=action["text"]
            )
        )
    elif action["action"] == "go_to_url":
        action_model = ActionModel(
            go_to_url=NavigateAction(
                url=action["url"]
            )
        )

    # Execute via browser-use Tools!
    result = await tools.act(
        action=action_model,
        browser_session=session
    )

    action_results.append({
        "action": action,
        "result": result.extracted_content,
        "error": result.error,
        "success": result.error is None
    })
```

**IMPORTANT**: Browser-use Tools handles:
- Finding element by index from cached selector_map
- Scrolling element into view
- Waiting for element to be ready
- Executing CDP commands
- Handling errors gracefully

**Output**:
```python
{
    "executed_actions": planned_actions,
    "action_results": action_results,
    "last_action_success": action_results[-1]["success"]
}
```

---

## 4️⃣ VERIFY Node

**Input**:
- `browser_session_id`
- `action_results` (from ACT)
- `executed_actions` (from ACT)

**Process**:

### Step 1: Check Action Results
```python
# Basic verification from action results
all_successful = all(r["success"] for r in state.action_results)

if not all_successful:
    failed_actions = [r for r in state.action_results if not r["success"]]
    return {
        "verification_status": "fail",
        "verification_message": f"Actions failed: {failed_actions}"
    }
```

### Step 2: Get Fresh Browser State (if needed)
```python
# For complex verifications, get updated DOM
session = get_session(state.browser_session_id)
new_browser_state = await session.get_browser_state_summary()

# Verify URL changed
if expected_url and new_browser_state.url != expected_url:
    return {
        "verification_status": "fail",
        "verification_message": f"Expected URL {expected_url}, got {new_browser_state.url}"
    }

# Verify element appeared/disappeared
if expected_element_text:
    element_found = any(
        expected_element_text in elem.text
        for elem in new_browser_state.dom_state.selector_map.values()
    )
    if not element_found:
        return {
            "verification_status": "fail",
            "verification_message": f"Expected element with text '{expected_element_text}' not found"
        }
```

**Output**:
```python
{
    "verification_status": "pass",  # or "fail"
    "verification_message": "All actions executed successfully",
    "new_url": new_browser_state.url,
    "new_title": new_browser_state.title
}
```

---

## 5️⃣ ROUTER (Conditional Logic)

**Decision Tree**:
```python
def should_continue(state: QAAgentState) -> str:
    # Check if task is complete
    if state.get("task_complete"):
        return "report"

    # Check verification status
    if state.verification_status == "fail":
        # Count consecutive failures
        consecutive_failures = count_consecutive_failures(state.history)
        if consecutive_failures >= settings.max_retries:
            return "report"  # Give up
        else:
            return "think"  # Retry

    # Check step limit
    if state.step_count >= settings.max_steps:
        return "report"

    # Check for "done" action
    last_action = state.executed_actions[-1] if state.executed_actions else None
    if last_action and last_action.get("action") == "done":
        return "report"

    # Continue to next step
    return "think"
```

---

## 6️⃣ REPORT Node

**Input**: Complete state with history

**Process**:
```python
async def report_node(state: QAAgentState) -> Dict[str, Any]:
    """Generate final test report"""

    # Aggregate results
    total_steps = state.step_count
    successful_steps = count_successful_steps(state.history)
    failed_steps = total_steps - successful_steps

    # Determine overall status
    task_complete = state.get("task_complete", False)
    final_status = "PASS" if task_complete else "FAIL"

    # Format report
    report = {
        "status": final_status,
        "task": state.task,
        "total_steps": total_steps,
        "successful_steps": successful_steps,
        "failed_steps": failed_steps,
        "final_url": state.get("current_url"),
        "execution_time": calculate_execution_time(state),
        "step_history": format_step_history(state.history)
    }

    # Cleanup browser session
    from qa_agent.utils.browser_manager import cleanup_browser_session
    if state.browser_session_id:
        await cleanup_browser_session(state.browser_session_id)

    return {
        "final_report": report,
        "result": final_status
    }
```

---

## 🔑 Critical Integration Points

### 1. **BrowserSession Must Be Initialized Once**
```python
# In workflow.py or INIT node
session_id, session = await create_browser_session()
register_session(session_id, session)

# In all other nodes
session = get_session(state.browser_session_id)
```

### 2. **Always Get Fresh DOM Before Thinking**
```python
# In THINK node - MUST call this!
browser_state = await session.get_browser_state_summary()
```

### 3. **Use Browser-Use Tools, Not Raw CDP**
```python
# ✅ CORRECT
tools = Tools(browser_session=session)
result = await tools.act(action_model, browser_session=session)

# ❌ WRONG - Don't bypass Tools
await session.cdp_client.send.Input.dispatchMouseEvent(...)
```

### 4. **Cache DOM State Between THINK and ACT**
```python
# In THINK node - save selector_map
dom_snapshot = browser_state.dom_state.selector_map

# Pass to ACT via state
state["dom_snapshot"] = dom_snapshot

# Tools will use this cached map for element lookups
```

### 5. **Action Schema Must Match Browser-Use**
```python
# Our actions must use browser-use field names:
{
    "action": "click_element",  # Must match ActionModel fields
    "index": 42,  # Must use "index" not "element_id"
}

# Convert to ActionModel before calling tools.act()
```

---

## 📊 Complete Example Flow

### **Scenario**: Login to website

#### **INIT**
```
Create browser session → Navigate to https://example.com
```

#### **Step 1 - Navigate**
**THINK**:
- Get DOM: Shows [0] input "email", [1] input "password", [2] button "Login"
- LLM plans: Fill form fields

**ACT**:
- Execute: input_text(index=0, text="user@example.com")
- Execute: input_text(index=1, text="password123")
- Results: Both successful

**VERIFY**:
- Check: Both inputs have values
- Status: PASS

**ROUTER**: Continue → THINK

#### **Step 2 - Submit**
**THINK**:
- Get fresh DOM: Form fields filled, submit button ready
- LLM plans: Click submit button

**ACT**:
- Execute: click_element(index=2)
- Results: Page navigated to /dashboard

**VERIFY**:
- Check: URL changed to /dashboard
- Check: "Welcome" text appears in DOM
- Status: PASS

**ROUTER**: Task complete → REPORT

#### **REPORT**
```
✅ PASS
Steps: 2
Success: 2/2
Final URL: https://example.com/dashboard
```

---

## ✅ Key Takeaways

1. **BrowserSession.get_browser_state_summary()** is the gateway to DOM - call it in THINK node
2. **Tools.act()** handles all browser interaction - use it in ACT node
3. **DomService** is internal to BrowserSession - we don't call it directly
4. **selector_map** provides element indices - this is what LLM uses to reference elements
5. **ActionModel** is browser-use's action schema - we must convert our actions to it
6. **INIT node is required** - we need to create browser session before THINK
7. **State must be serializable** - use session_id not session object

This is the robust, browser-use-native architecture!
