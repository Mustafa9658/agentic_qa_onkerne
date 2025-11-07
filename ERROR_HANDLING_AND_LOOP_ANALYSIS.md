# Error Handling and Loop Termination Analysis

## Executive Summary

After deep analysis of the QA agent codebase, here are the findings:

### ✅ What We're Doing RIGHT:

1. **Error Feedback to LLM**: ✅ IMPLEMENTED CORRECTLY
2. **Loop Termination**: ✅ MAX_STEPS PROTECTION EXISTS
3. **Currency Format Detection**: ✅ WELL-DESIGNED ENHANCEMENT

### ❌ What We're Missing:

1. **Step Repetition Detection**: ❌ NOT IMPLEMENTED
2. **Consecutive Failure Tracking**: ❌ NOT IMPLEMENTED (browser-use has this)
3. **Action Similarity Detection**: ❌ NOT IMPLEMENTED

---

## 1. Error Feedback to LLM

### ✅ STATUS: CORRECTLY IMPLEMENTED

**Location**: [think.py:378-393](qa_agent/nodes/think.py#L378-L393)

**How it works**:
```python
for result in results:
    error = result.get("error")

    # Build action_results text (browser-use pattern)
    if long_term_memory:
        action_results_text += f'{long_term_memory}\n'
    elif extracted_content and not include_only_once:
        action_results_text += f'{extracted_content}\n'

    if error:
        error_text = error[:200] + '......' + error[-100:] if len(error) > 200 else error
        action_results_text += f'Error: {error_text}\n'

if action_results_text:
    step_content_parts.append(f'Result\n{action_results_text.strip()}')
```

**Error Flow**:
1. **Step N**: Action fails → `ActionResult.error = "Element not found at index 123"`
2. **Step N+1**: `think_node()` extracts error from `action_results` in state
3. **Step N+1**: Error is added to `agent_history_description` under "Result" section
4. **Step N+1**: LLM receives the error in its context and can adjust strategy

**Example Error Message to LLM**:
```
<step_5>
evaluation: Previous action attempted to click element 123
memory: Trying to click login button
next_goal: Navigate to login page
Result
Error: Element at index 123 not found in DOM. Available indices: 1-50
</step_5>
```

**Verification Failed Errors** (Lines 398-422):
- When verify node detects failures, it adds detailed failure reasons
- Includes retry guidance: "⚠️ RETRY: The previous action failed. Please review the CURRENT <browser_state> above..."
- LLM is explicitly told to use CURRENT element indices, not stale ones

**VERDICT**: ✅ **We ARE sending errors to LLM correctly**

---

## 2. Loop Termination

### ✅ STATUS: MAX_STEPS PROTECTION EXISTS

**Location**: [workflow.py:36-42](qa_agent/workflow.py#L36-L42) and [workflow.py:98-104](qa_agent/workflow.py#L98-L104)

**How it works**:

#### Router Function 1: `should_continue()` (after verify)
```python
def should_continue(state: QAAgentState) -> Literal["continue", "retry", "done"]:
    # Check if completed or error
    if state.get("completed"):
        return "done"

    if state.get("error"):
        return "done"

    # Check max steps (infinite loop prevention)
    step_count = state.get("step_count", 0)
    max_steps = state.get("max_steps", settings.max_steps)

    if step_count >= max_steps:
        logger.warning(f"Max steps reached: {step_count}/{max_steps}")
        return "done"
```

#### Router Function 2: `should_continue_after_think()` (after think)
```python
def should_continue_after_think(state: QAAgentState) -> Literal["continue", "done", "replan"]:
    if state.get("completed"):
        return "done"

    if state.get("error"):
        return "done"

    # Infinite loop prevention
    step_count = state.get("step_count", 0)
    max_steps = state.get("max_steps", settings.max_steps)

    if step_count >= max_steps:
        logger.warning(f"Max steps reached in think router: {step_count}/{max_steps}")
        return "done"
```

**Configuration**:
- Default `max_steps = 50` (from `config.py`)
- Set via `QA_AGENT_MAX_STEPS` environment variable

**Loop Flow**:
```
START → INIT → PLAN → THINK → ACT → THINK → ACT → ... (max 50 iterations) → REPORT
                       ↑___________________________|
```

**VERDICT**: ✅ **Max steps protection exists**

---

## 3. What's MISSING: Step Repetition Detection

### ❌ STATUS: NOT IMPLEMENTED

**Problem**: The agent can get stuck repeating the same failed action over and over until max_steps is reached.

**Example Scenario**:
```
Step 1: Click element 123 → Error: Element not found
Step 2: Click element 123 → Error: Element not found
Step 3: Click element 123 → Error: Element not found
...
Step 50: Click element 123 → Error: Element not found → MAX_STEPS reached
```

**Browser-use has this** in `service.py:1755-1761`:
```python
# Track consecutive failures
self.state.consecutive_failures += 1

# Check if max failures reached
if self.state.consecutive_failures >= self.max_failures + (1 if self.final_response_after_failure else 0):
    logger.warning(f'Max consecutive failures reached: {self.state.consecutive_failures}')
    break
```

**Browser-use configuration**:
- `max_failures = 3` (default)
- `final_response_after_failure = True` (allows one final attempt to call "done")
- Total allowed failures: 4

**What we need to add**:

1. **Consecutive Failure Counter**:
   - Track consecutive failures in state
   - Reset counter on success
   - Increment on failure

2. **Max Failures Check**:
   - Check if `consecutive_failures >= max_failures`
   - Force "done" action if max reached

3. **Action Similarity Detection** (optional but recommended):
   - Compare current action with previous action
   - Detect if agent is repeating the same action
   - Force "done" if repeating more than N times

---

## 4. Comparison with Browser-Use

### Browser-Use Implementation

**Location**: `browser-use/browser_use/agent/service.py`

**Key Features**:

1. **Consecutive Failure Tracking** (lines 1741-1761):
```python
# Check if action succeeded
if result.is_done:
    # Success - reset failure counter
    self.state.consecutive_failures = 0
else:
    # Failure - increment counter
    self.state.consecutive_failures += 1

# Check max failures
if self.state.consecutive_failures >= max_failures_threshold:
    logger.warning('Max consecutive failures reached')
    # Force done action
    break
```

2. **Forced Done After Failure** (lines 902-913):
```python
def _force_done_after_failure(self):
    """Add message restricting LLM to only 'done' action after max failures"""
    msg = UserMessage(
        content='You have reached the maximum number of consecutive failures. '
                'You must now call the done() action to complete the task. '
                'Summarize what you accomplished and what failed.'
    )
    self.message_manager.add_message(msg)
```

3. **Error Propagation** (lines 213-219):
```python
def _update_agent_history_description(self):
    """Extract error from ActionResult and add to history"""
    if action_result.error:
        history_entry += f'Result\nError: {action_result.error}\n'
```

### Our Implementation

**What we have**:
- ✅ Error propagation to LLM (think.py:378-393)
- ✅ Max steps protection (workflow.py:36-42)
- ✅ Verification failure details (think.py:398-422)
- ✅ Goal-based progress tracking (think.py:242-295)

**What we're missing**:
- ❌ Consecutive failure counter
- ❌ Max failures threshold
- ❌ Forced "done" after max failures
- ❌ Action repetition detection

---

## 5. Recommended Fixes

### Priority 1: Add Consecutive Failure Tracking

**Where**: Add to `qa_agent/state.py`
```python
class QAAgentState(TypedDict):
    # ... existing fields ...
    consecutive_failures: int  # Track consecutive failures
    max_failures: int  # Maximum allowed consecutive failures (default: 3)
```

**Where**: Update `qa_agent/nodes/act.py` (after action execution)
```python
# After executing action (around line 160)
if result.error:
    # Increment failure counter
    consecutive_failures = state.get("consecutive_failures", 0) + 1
else:
    # Reset failure counter on success
    consecutive_failures = 0

return {
    "consecutive_failures": consecutive_failures,
    # ... other fields ...
}
```

**Where**: Update `qa_agent/workflow.py` (in router functions)
```python
def should_continue_after_think(state: QAAgentState) -> Literal["continue", "done", "replan"]:
    # ... existing checks ...

    # Check consecutive failures
    consecutive_failures = state.get("consecutive_failures", 0)
    max_failures = state.get("max_failures", 3)

    if consecutive_failures >= max_failures:
        logger.warning(f"Max consecutive failures reached: {consecutive_failures}/{max_failures}")
        return "done"

    # ... rest of function ...
```

### Priority 2: Add Action Repetition Detection

**Where**: Add to `qa_agent/nodes/think.py`
```python
# Before returning state (around line 770)
previous_action = state.get("previous_action")
current_action = valid_actions[0] if valid_actions else None

# Check if repeating same action
if previous_action and current_action:
    if (previous_action.get("action") == current_action.get("action") and
        previous_action.get("index") == current_action.get("index")):
        repetition_count = state.get("action_repetition_count", 0) + 1

        if repetition_count >= 3:
            logger.warning(f"Action repeated {repetition_count} times, forcing done")
            return {
                "error": f"Action repeated {repetition_count} times without success",
                "completed": True,
            }
    else:
        repetition_count = 0
else:
    repetition_count = 0

return {
    "previous_action": current_action,
    "action_repetition_count": repetition_count,
    # ... other fields ...
}
```

### Priority 3: Add Forced Done Message

**Where**: Update `qa_agent/nodes/think.py` (in prompt building)
```python
# Around line 459, before creating agent_message_prompt
consecutive_failures = state.get("consecutive_failures", 0)
max_failures = state.get("max_failures", 3)

if consecutive_failures >= max_failures:
    # Force LLM to call done action
    enhanced_task = (
        f"⚠️ MAXIMUM FAILURES REACHED ({consecutive_failures}/{max_failures})\n\n"
        f"You must now call the done() action to complete the task.\n"
        f"Summarize what you accomplished and what failed.\n\n"
        f"Original task: {task}"
    )
else:
    enhanced_task = task
```

---

## 6. Currency Format Implementation Review

### ✅ STATUS: WELL-DESIGNED

**Location**: [dom/serializer/serializer.py:1073-1142](qa_agent/dom/serializer/serializer.py#L1073-L1142)

**What it does**:
1. Detects currency from multiple sources (placeholder, aria-label, sibling elements)
2. Adds `currency_format=PKR` attribute to the input field
3. Updates placeholder with currency hint: `placeholder="Price per month (PKR)"`
4. Protected from duplicate removal

**Why it's good**:
- Follows same pattern as date/time format detection
- Multiple detection sources (robust)
- Explicit format communication to LLM
- Backward compatible (only adds info, doesn't break anything)

**VERDICT**: ✅ **Well-implemented enhancement**

---

## 7. Summary

### Current State

| Feature | Status | Notes |
|---------|--------|-------|
| Error feedback to LLM | ✅ Working | Errors sent in agent_history_description |
| Max steps protection | ✅ Working | Default 50 steps, configurable |
| Verification failure details | ✅ Working | Includes retry guidance |
| Currency format detection | ✅ Working | Custom enhancement, not in browser-use |
| **Consecutive failure tracking** | ❌ Missing | Browser-use has this |
| **Action repetition detection** | ❌ Missing | Would prevent stuck loops |
| **Forced done after failures** | ❌ Missing | Browser-use forces graceful exit |

### Why Agent Gets Stuck

**Scenario**: Agent tries "Click element 123" repeatedly even though it fails every time.

**Current behavior**:
1. Step 1: Click 123 → Error sent to LLM
2. Step 2: LLM sees error, tries Click 123 again → Error sent to LLM
3. Step 3: LLM sees error, tries Click 123 again → Error sent to LLM
4. ... repeats until max_steps (50) reached

**Why LLM repeats**:
- LLM sees the error but doesn't know it's a "fatal" failure
- No explicit signal that "this action will never work"
- No forced intervention after N consecutive failures
- No detection that "you're repeating the same action"

**What browser-use does differently**:
1. Tracks consecutive failures
2. After 3 failures, forces "done" action
3. Adds explicit message: "You must now call done() to complete the task"
4. Graceful exit instead of max_steps timeout

### Recommendations

**Immediate** (Priority 1):
1. Add consecutive failure tracking (3-failure threshold)
2. Force "done" action after max failures
3. Add explicit "max failures reached" message to LLM

**Short-term** (Priority 2):
1. Add action repetition detection (detect same action repeated 3+ times)
2. Add retry budget per action type (e.g., click action gets 2 retries, then give up)

**Long-term** (Priority 3):
1. Add intelligent retry strategies (e.g., wait for DOM to stabilize before retry)
2. Add action similarity detection (detect similar but not identical actions)
3. Add goal-based failure tracking (track failures per goal, not just overall)

---

## 8. Code Locations Reference

### Error Handling
- **Error extraction**: [think.py:378-393](qa_agent/nodes/think.py#L378-L393)
- **Verification failures**: [think.py:398-422](qa_agent/nodes/think.py#L398-L422)
- **Error storage**: [act.py:148-173](qa_agent/nodes/act.py#L148-L173)

### Loop Termination
- **Router after verify**: [workflow.py:16-78](qa_agent/workflow.py#L16-L78)
- **Router after think**: [workflow.py:81-123](qa_agent/workflow.py#L81-L123)
- **Max steps config**: [config.py](qa_agent/config.py)

### Goal Tracking
- **Goal tracking logic**: [think.py:242-295](qa_agent/nodes/think.py#L242-L295)
- **Goal-based task updates**: [think.py:289-295](qa_agent/nodes/think.py#L289-L295)

### Currency Format
- **Detection logic**: [dom/serializer/serializer.py:1073-1142](qa_agent/dom/serializer/serializer.py#L1073-L1142)
- **Configuration**: [dom/views.py:55](qa_agent/dom/views.py#L55)

---

## Conclusion

**The Good**:
- Error feedback to LLM is working correctly
- Max steps protection prevents infinite loops (at 50 steps)
- Currency format detection is a well-designed enhancement

**The Gap**:
- Missing consecutive failure tracking (browser-use has max_failures=3)
- Missing action repetition detection
- Agent can get stuck repeating failed actions until max_steps

**The Fix**:
- Add consecutive failure counter (3 failures = done)
- Add forced "done" message after max failures
- Add action repetition detection (same action 3 times = done)
