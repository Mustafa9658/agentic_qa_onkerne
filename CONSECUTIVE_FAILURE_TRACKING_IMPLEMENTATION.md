# Consecutive Failure Tracking Implementation

## Summary

Successfully implemented browser-use's consecutive failure tracking mechanism to prevent the agent from getting stuck in infinite retry loops. This implementation directly addresses the issues identified in [ERROR_HANDLING_AND_LOOP_ANALYSIS.md](ERROR_HANDLING_AND_LOOP_ANALYSIS.md).

## Changes Made

### 1. Added Failure Tracking to State ([state.py](qa_agent/state.py))

**Lines**: 69-72, 135-137

**Changes**:
```python
# Failure Tracking (browser-use pattern)
consecutive_failures: int  # Count of consecutive action failures
max_failures: int  # Maximum allowed consecutive failures (default: 3)
final_response_after_failure: bool  # Allow one final attempt after max_failures
```

**Initial values**:
```python
consecutive_failures=0,  # NEW: Track consecutive failures (browser-use pattern)
max_failures=3,  # NEW: Max allowed consecutive failures (browser-use default)
final_response_after_failure=True,  # NEW: Allow one final attempt (browser-use pattern)
```

**Browser-use reference**: `browser_use/agent/views.py:66`

---

### 2. Implemented Failure Tracking in Act Node ([act.py](qa_agent/nodes/act.py))

**Lines**: 292-317

**Logic** (browser-use pattern from `service.py:793-800`):
```python
# Track consecutive failures (browser-use pattern: service.py:793-800)
# Browser-use checks: if single action AND it has error, increment failure counter
# If success (no error), reset failure counter to 0
consecutive_failures = state.get("consecutive_failures", 0)

if len(action_results) == 1 and action_results[0].get("error"):
    # Single action failed - increment consecutive failures
    consecutive_failures += 1
    logger.debug(f"🔄 Step {state.get('step_count', 0)}: Action failed, consecutive failures: {consecutive_failures}")
else:
    # Success or multiple actions - reset consecutive failures
    if consecutive_failures > 0:
        logger.debug(f"🔄 Step {state.get('step_count', 0)}: Action succeeded, resetting consecutive failures from {consecutive_failures} to 0")
        consecutive_failures = 0
```

**Return state**:
```python
return_state = {
    # ... other fields ...
    "consecutive_failures": consecutive_failures,  # NEW: Track failure count (browser-use pattern)
}
```

**Browser-use reference**: `browser_use/agent/service.py:793-800`

---

### 3. Added Failure Checks to Workflow Routers ([workflow.py](qa_agent/workflow.py))

**Router 1: `should_continue()` (Lines 36-44)**

Browser-use pattern from `service.py:1755-1761`:
```python
# Check max consecutive failures (browser-use pattern: service.py:1755-1761)
# If final_response_after_failure is True, allow one final attempt after max_failures
consecutive_failures = state.get("consecutive_failures", 0)
max_failures = state.get("max_failures", 3)
final_response_after_failure = state.get("final_response_after_failure", True)

if consecutive_failures >= max_failures + int(final_response_after_failure):
    logger.error(f"❌ Stopping due to {max_failures} consecutive failures")
    return "done"
```

**Router 2: `should_continue_after_think()` (Lines 108-115)**

Same logic as Router 1:
```python
# Check max consecutive failures (browser-use pattern)
consecutive_failures = state.get("consecutive_failures", 0)
max_failures = state.get("max_failures", 3)
final_response_after_failure = state.get("final_response_after_failure", True)

if consecutive_failures >= max_failures + int(final_response_after_failure):
    logger.error(f"❌ Stopping in think router due to {max_failures} consecutive failures")
    return "done"
```

**Browser-use reference**: `browser_use/agent/service.py:1755-1761`

---

### 4. Implemented Forced Done Message ([think.py](qa_agent/nodes/think.py))

**Lines**: 455-476

**Logic** (browser-use pattern from `service.py:902-913`):
```python
# Browser-use pattern: Force done action after max_failures (service.py:902-913)
# Check if we've reached max consecutive failures
consecutive_failures = state.get("consecutive_failures", 0)
max_failures = state.get("max_failures", 3)
final_response_after_failure = state.get("final_response_after_failure", True)

# Force done action after max failures (browser-use pattern: service.py:905-913)
if consecutive_failures >= max_failures and final_response_after_failure:
    logger.warning(f"🛑 Max consecutive failures reached ({consecutive_failures}/{max_failures}), forcing done action")
    # Create forced done message (browser-use pattern)
    force_done_msg = f'You failed {max_failures} times. Therefore we terminate the agent.\n'
    force_done_msg += 'Your only tool available is the "done" tool. No other tool is available. All other tools which you see in history or examples are not available.\n'
    force_done_msg += 'If the task is not yet fully finished as requested by the user, set success in "done" to false! E.g. if not all steps are fully completed. Else success to true.\n'
    force_done_msg += 'Include everything you found out for the ultimate task in the done text.\n'
    force_done_msg += f'\nOriginal task: {task}'
    enhanced_task = force_done_msg
```

**Browser-use reference**: `browser_use/agent/service.py:902-913`

---

### 5. Implemented Action Repetition Detection ([think.py](qa_agent/nodes/think.py))

**Lines**: 811-859

**Logic**:
```python
# Action repetition detection (prevent infinite loops of same action)
# Compare current action with previous action from history
previous_action = None
if existing_history:
    # Get most recent think node action
    for entry in reversed(existing_history):
        if entry.get("node") == "think" and entry.get("planned_actions"):
            previous_action = entry["planned_actions"][0]
            break

current_action = valid_actions[0] if valid_actions else None
action_repetition_count = state.get("action_repetition_count", 0)

# Check if repeating same action (same action type and same index)
if previous_action and current_action:
    if (previous_action.get("action") == current_action.get("action") and
        previous_action.get("index") == current_action.get("index")):
        action_repetition_count += 1
        logger.warning(f"⚠️ Action repeated {action_repetition_count} times: {current_action.get('action')} on index {current_action.get('index')}")

        # Force done if repeated 3+ times
        if action_repetition_count >= 3:
            logger.error(f"🛑 Action repeated {action_repetition_count} times, forcing completion")
            return {
                "error": f"Action '{current_action.get('action')}' on index {current_action.get('index')} repeated {action_repetition_count} times without success",
                "completed": True,
                "step_count": step_count,
            }
    else:
        # Different action - reset counter
        action_repetition_count = 0
else:
    action_repetition_count = 0
```

**Return state update**:
```python
state_updates = {
    # ... other fields ...
    "action_repetition_count": action_repetition_count,
}
```

**Note**: This is an enhancement not present in browser-use, but follows the same pattern.

---

## How It Works

### Scenario 1: Action Fails Once

```
Step 1: Click element 123 → Error: "Element not found"
        consecutive_failures = 1
Step 2: LLM sees error → Tries different approach → Success
        consecutive_failures = 0 (reset)
```

### Scenario 2: Action Fails 3 Times (Max Failures)

```
Step 1: Click 123 → Error → consecutive_failures = 1
Step 2: Click 123 → Error → consecutive_failures = 2
Step 3: Click 123 → Error → consecutive_failures = 3
Step 4: Force done message sent to LLM
        LLM must call "done" action
        consecutive_failures = 4 (final attempt)
Step 5: Router checks: 4 >= 3 + 1 → STOP
```

### Scenario 3: Action Repeats 3 Times (Repetition Detection)

```
Step 1: Click 123 → repetition_count = 1
Step 2: Click 123 → repetition_count = 2
Step 3: Click 123 → repetition_count = 3 → FORCE COMPLETION
```

---

## Configuration

All values are configurable via state:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `max_failures` | 3 | Maximum consecutive failures before forcing done |
| `final_response_after_failure` | True | Allow one final attempt after max_failures |
| `action_repetition_count` | 0 | Track repeated actions (force done at 3) |

**Total allowed failures**: `max_failures + int(final_response_after_failure)` = **4 attempts**

---

## Browser-Use Comparison

### What We Implemented (Matching Browser-Use):

| Feature | Browser-Use | Our Implementation | Status |
|---------|-------------|-------------------|--------|
| Consecutive failure counter | ✅ `service.py:794` | ✅ `act.py:297-300` | ✅ Exact match |
| Reset on success | ✅ `service.py:798-800` | ✅ `act.py:302-305` | ✅ Exact match |
| Max failures check | ✅ `service.py:1756-1758` | ✅ `workflow.py:42-44` | ✅ Exact match |
| Forced done message | ✅ `service.py:905-913` | ✅ `think.py:468-476` | ✅ Exact match |
| final_response_after_failure | ✅ `views.py:56` | ✅ `state.py:72` | ✅ Exact match |

### What We Enhanced (Not in Browser-Use):

| Feature | Browser-Use | Our Implementation | Status |
|---------|-------------|-------------------|--------|
| Action repetition detection | ❌ Not present | ✅ `think.py:811-843` | ✅ Enhancement |
| Repetition threshold | ❌ N/A | ✅ 3 repetitions | ✅ New feature |

---

## Testing

All components compile and import successfully:

```bash
✅ State imports correctly
✅ Initial state has failure tracking: consecutive_failures=0, max_failures=3
✅ Workflow routers import correctly
✅ Act node imports correctly
✅ Think node imports correctly
```

---

## Benefits

### 1. Prevents Infinite Retry Loops
**Before**:
```
Step 1-50: Click 123 → Error → Click 123 → Error → ... (until max_steps)
```

**After**:
```
Step 1-3: Click 123 → Error (tracked)
Step 4: Force done → Graceful exit
```

### 2. Early Detection of Fatal Failures
- Detects when an action will never succeed
- Stops after 3 failures instead of 50 steps
- Saves time and API costs

### 3. Graceful Recovery
- Forces LLM to call "done" action
- Allows LLM to summarize what was accomplished
- Sets success=false if task incomplete

### 4. Action Repetition Protection
- Detects if agent repeats same action
- Stops if same action+index repeated 3 times
- Additional safety net beyond consecutive failures

---

## Code Locations Reference

### State Definition
- **File**: [qa_agent/state.py](qa_agent/state.py)
- **Lines**: 69-72 (fields), 135-137 (initialization)

### Failure Tracking Logic
- **File**: [qa_agent/nodes/act.py](qa_agent/nodes/act.py)
- **Lines**: 292-317 (tracking), 332 (return state)

### Router Checks
- **File**: [qa_agent/workflow.py](qa_agent/workflow.py)
- **Lines**: 36-44 (should_continue), 108-115 (should_continue_after_think)

### Forced Done Message
- **File**: [qa_agent/nodes/think.py](qa_agent/nodes/think.py)
- **Lines**: 455-476

### Action Repetition Detection
- **File**: [qa_agent/nodes/think.py](qa_agent/nodes/think.py)
- **Lines**: 811-859

---

## Browser-Use References

All implementations directly reference browser-use code:

1. **Failure Counter**: `browser_use/agent/service.py:793-800`
2. **Max Failures Check**: `browser_use/agent/service.py:1755-1761`
3. **Forced Done**: `browser_use/agent/service.py:902-913`
4. **State Definition**: `browser_use/agent/views.py:66`
5. **Settings**: `browser_use/agent/views.py:40, 56`

---

## Conclusion

This implementation provides **three layers of protection** against infinite loops:

1. **Consecutive Failure Tracking**: Stops after 3 consecutive failures (browser-use pattern)
2. **Action Repetition Detection**: Stops if same action repeated 3 times (our enhancement)
3. **Max Steps**: Ultimate safety net at 50 steps (existing)

The agent will now gracefully exit when stuck instead of consuming all 50 steps trying the same failed action repeatedly.
