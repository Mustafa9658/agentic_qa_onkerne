# Time Estimate: Phase 3 Integration

## Summary
**Total Estimated Time**: 2-3 hours for working prototype
**Complexity**: Medium (most infrastructure is ready)

---

## Changes Breakdown

### 🔧 Fix 1: Browser Manager WebSocket URL (10 min)
**File**: [qa_agent/utils/browser_manager.py](qa_agent/utils/browser_manager.py)
**Lines Changed**: ~10 lines (add 8 lines)
**Complexity**: Low (copy from test_cdp_simple.py)

**Change**:
```python
# BEFORE (line 34):
cdp_url = f"http://{settings.kernel_cdp_host}:{settings.kernel_cdp_port}"

# AFTER:
import httpx

# Get WebSocket URL from HTTP endpoint
http_url = f"http://{settings.kernel_cdp_host}:{settings.kernel_cdp_port}"
async with httpx.AsyncClient() as client:
    response = await client.get(f"{http_url}/json/version")
    version_data = response.json()
    cdp_url = version_data["webSocketDebuggerUrl"]
```

**Testing**: Run test_cdp_connection.py (should pass)

---

### 🔧 Fix 2: Add INIT Node (15 min)
**New File**: [qa_agent/nodes/init.py](qa_agent/nodes/init.py)
**Lines**: ~40 lines
**Complexity**: Low (straightforward)

**Code**:
```python
"""Initialize browser session at workflow start"""
async def init_node(state: QAAgentState) -> Dict[str, Any]:
    from qa_agent.utils.browser_manager import create_browser_session

    session_id, session = await create_browser_session()

    if state.get("start_url"):
        await session.navigate_to(state["start_url"])

    return {
        "browser_session_id": session_id,
        "current_url": session.current_page.url if session.current_page else None,
    }
```

**Also Update**:
- [qa_agent/workflow.py](qa_agent/workflow.py): Add INIT node to graph (~5 lines)
- [qa_agent/nodes/__init__.py](qa_agent/nodes/__init__.py): Export init_node (~1 line)

---

### 🔧 Fix 3: Update THINK Node (30 min)
**File**: [qa_agent/nodes/think.py](qa_agent/nodes/think.py) (248 lines)
**Lines Changed**: ~50 lines (replace placeholder logic)
**Complexity**: Medium (integrate browser-use properly)

**Major Changes**:
1. Get session from registry (5 lines)
2. Call `session.get_browser_state_summary()` (10 lines)
3. Extract DOM elements for LLM (15 lines)
4. Format prompt with browser state (10 lines)
5. Cache selector_map in state (5 lines)

**Key Addition**:
```python
from qa_agent.utils import get_session

session = get_session(state.browser_session_id)
browser_state = await session.get_browser_state_summary(
    include_screenshot=False,
    include_recent_events=False
)

# Format elements for LLM
selector_map = browser_state.dom_state.selector_map
elements_text = browser_state.dom_state.element_tree
```

**Testing**: Check that DOM is retrieved and formatted

---

### 🔧 Fix 4: Update ACT Node (40 min)
**File**: [qa_agent/nodes/act.py](qa_agent/nodes/act.py) (97 lines)
**Lines Changed**: ~60 lines (replace entire simulation)
**Complexity**: Medium-High (action model conversion)

**Major Changes**:
1. Remove placeholder simulation (~30 lines removed)
2. Get session and init Tools (10 lines)
3. Convert actions to ActionModel (30 lines)
4. Execute via tools.act() (20 lines)

**Key Code**:
```python
from qa_agent.tools.service import Tools
from qa_agent.tools.views import ClickElementAction, InputTextAction, NavigateAction
from qa_agent.agent.views import ActionModel

session = get_session(state.browser_session_id)
tools = Tools(browser_session=session)

for action in planned_actions:
    # Convert dict to ActionModel
    if action["action"] == "click_element":
        action_model = ActionModel(
            click_element=ClickElementAction(index=action["index"])
        )
    # ... other action types

    result = await tools.act(action=action_model, browser_session=session)
    action_results.append(result)
```

**Testing**: Execute simple action (navigate, click)

---

### 🔧 Fix 5: Copy LLM Providers (20 min)
**Files to Copy**:
- `browser_use/llm/openai_service.py` → [qa_agent/llm/openai_service.py](qa_agent/llm/openai_service.py)
- `browser_use/llm/anthropic_service.py` → [qa_agent/llm/anthropic_service.py](qa_agent/llm/anthropic_service.py)

**Changes**: Fix imports (browser_use → qa_agent) (~5 min per file)

**Update**: [qa_agent/llm/__init__.py](qa_agent/llm/__init__.py) to export providers

**Testing**: Import and instantiate LLM

---

### 🔧 Fix 6: Update Workflow Init (15 min)
**File**: [qa_agent/workflow.py](qa_agent/workflow.py) (172 lines)
**Lines Changed**: ~20 lines

**Changes**:
1. Add INIT node to graph
2. Update edges: START → INIT → THINK
3. Pass browser_session_id through state
4. Add cleanup in END node

**Code**:
```python
from qa_agent.nodes import init_node, think_node, act_node, verify_node, report_node

workflow.add_node("init", init_node)
workflow.add_node("think", think_node)
# ... rest

workflow.add_edge(START, "init")
workflow.add_edge("init", "think")
# ... rest
```

---

### 🔧 Fix 7: Integration Test (30 min)
**New File**: [tests/test_integration_basic.py](tests/test_integration_basic.py)
**Lines**: ~80 lines

**Test Flow**:
1. Start workflow with simple task
2. Verify INIT creates session
3. Verify THINK gets DOM
4. Verify ACT executes action
5. Verify session cleanup

**Run**: Simple navigation test with kernel-image

---

## File Change Summary

| File | Status | Lines | Time |
|------|--------|-------|------|
| qa_agent/utils/browser_manager.py | Modify | +8 | 10m |
| qa_agent/nodes/init.py | Create | +40 | 15m |
| qa_agent/nodes/think.py | Modify | ~50 | 30m |
| qa_agent/nodes/act.py | Modify | ~60 | 40m |
| qa_agent/workflow.py | Modify | +20 | 15m |
| qa_agent/llm/openai_service.py | Copy+Fix | +200 | 10m |
| qa_agent/llm/anthropic_service.py | Copy+Fix | +200 | 10m |
| tests/test_integration_basic.py | Create | +80 | 30m |
| **TOTAL** | | **~658** | **160m** |

---

## Timeline Breakdown

### Phase 1: Critical Path (90 min)
1. ✅ Fix browser_manager WS URL (10m)
2. ✅ Add INIT node (15m)
3. ✅ Update THINK node (30m)
4. ✅ Update ACT node (40m)
5. ✅ Update workflow (15m)

**Deliverable**: Basic workflow runs with browser-use Tools

---

### Phase 2: LLM & Testing (70 min)
6. ✅ Copy LLM providers (20m)
7. ✅ Integration test (30m)
8. ✅ Debug & refinement (20m)

**Deliverable**: End-to-end test passes

---

## Risk Factors

### Low Risk (Likely Works)
- ✅ Browser manager WS fix (tested in test_cdp_simple.py)
- ✅ INIT node (straightforward)
- ✅ LLM provider copy (minimal changes)

### Medium Risk (May Need Tweaking)
- ⚠️ THINK node DOM extraction (format might need adjustment)
- ⚠️ ACT node action conversion (ActionModel schema must match)

### Debugging Budget
- Add 30-60 minutes for unexpected issues
- Most likely: ActionModel field name mismatches
- Second likely: DOM selector_map caching issues

---

## Assumptions

1. ✅ All browser-use modules already copied (done)
2. ✅ CDP connection working (verified with test_cdp_simple.py)
3. ✅ Imports all fixed (completed)
4. ⚠️ BrowserSession.start() works with WS URL (needs testing)
5. ⚠️ Tools.act() works with kernel-image (needs testing)

---

## Realistic Estimate

**Best Case**: 2 hours (everything works first try)
**Expected Case**: 2.5-3 hours (minor debugging needed)
**Worst Case**: 4 hours (major ActionModel or DOM issues)

**Confidence**: High (85%)
Most of the infrastructure is ready. The main work is replacing placeholders with real browser-use calls.

---

## Next Action

Start with **Fix 1** (browser_manager WS URL) - it's quick, low-risk, and unblocks testing the full BrowserSession lifecycle. That will reveal any hidden issues early.
