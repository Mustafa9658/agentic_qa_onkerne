"""
Act Node - Execute planned actions

This node:
1. Receives planned actions from Think node
2. Initializes Tools instance with BrowserSession
3. Executes actions via browser-use Tools
4. Captures action results
5. Persists FileSystem state (LLM decides when to update todo.md via replace_file action)
"""
import asyncio
import logging
from typing import Dict, Any
from qa_agent.state import QAAgentState
from qa_agent.config import settings
from qa_agent.utils.session_registry import get_session
from qa_agent.tools.service import Tools
from typing import TYPE_CHECKING

if TYPE_CHECKING:
	from qa_agent.agent.views import ActionModel

logger = logging.getLogger(__name__)


async def act_node(state: QAAgentState) -> Dict[str, Any]:
	"""
	Act node: Execute planned actions using browser-use Tools

	Args:
		state: Current QA agent state

	Returns:
		Updated state with executed actions and results
	"""
	logger.info(f"Act node - Step {state.get('step_count', 0)}")

	# Get browser session from registry
	browser_session_id = state.get("browser_session_id")
	if not browser_session_id:
		logger.error("No browser_session_id in state")
		return {
			"error": "No browser session ID - INIT node must run first",
			"executed_actions": [],
			"action_results": [],
		}

	session = get_session(browser_session_id)
	if not session:
		logger.error(f"Browser session {browser_session_id} not found in registry")
		return {
			"error": f"Browser session {browser_session_id} not found",
			"executed_actions": [],
			"action_results": [],
		}

	# Get planned actions
	planned_actions = state.get("planned_actions", [])

	print(f"\n{'='*80}")
	print(f"🎭 ACT NODE - Executing Actions via browser-use Tools")
	print(f"{'='*80}")
	print(f"📋 Planned Actions: {len(planned_actions)}")
	print(f"🌐 Browser Session: {browser_session_id[:16]}...")

	if not planned_actions:
		logger.warning("No planned actions to execute")
		print(f"⚠️  No actions to execute\n")
		return {
			"executed_actions": [],
			"action_results": [],
		}

	# CRITICAL: Get tabs BEFORE actions to detect new tabs opened by actions
	# Browser-use pattern: Compare tabs before/after to detect new tabs
	logger.info("📋 Getting tabs BEFORE actions (for new tab detection)...")
	try:
		browser_state_before = await session.get_browser_state_summary(include_screenshot=False, cached=True)
		tabs_before = browser_state_before.tabs if browser_state_before.tabs else []
		previous_tabs = [t.target_id for t in tabs_before]
		initial_tab_count = len(previous_tabs)
		logger.info(f"   Tabs before actions: {initial_tab_count} tabs")
	except Exception as e:
		logger.warning(f"Could not get tabs before actions: {e}")
		previous_tabs = state.get("previous_tabs", [])
		initial_tab_count = len(previous_tabs) if previous_tabs else state.get("tab_count", 1)

	# Initialize Tools instance
	logger.info("Initializing browser-use Tools")
	tools = Tools()
	
	# planned_actions is already list[ActionModel] from think node
	# No conversion needed - LangChain with_structured_output() returns validated Pydantic objects
	# Execute actions sequentially
	executed_actions = []
	action_results = []

	for i, action_model in enumerate(planned_actions, 1):
		# action_model is already ActionModel - get action type from model dump
		action_dump = action_model.model_dump(exclude_unset=True)
		action_type = list(action_dump.keys())[0] if action_dump else "unknown"
		print(f"\n  [{i}/{len(planned_actions)}] Executing: {action_type}")

		try:
			# STEP 1: Capture DOM state BEFORE action (for dynamic verification)
			# This allows us to compare before/after and detect what actually changed
			dom_before = None
			url_before = None
			title_before = None
			errors_before = None
			
			# Only capture state for actions that modify the page
			if action_type in ["click", "input", "select_dropdown", "scroll"]:
				try:
					# Get quick snapshot of current state
					state_before = await session.get_browser_state_summary(include_screenshot=False, cached=True)
					dom_before = len(state_before.dom_state.selector_map) if state_before.dom_state else 0
					url_before = state_before.url
					title_before = state_before.title
					
					# Check for existing errors on page BEFORE action
					cdp_session = await session.get_or_create_cdp_session(focus=True)
					errors_check = await cdp_session.cdp_client.send.Runtime.evaluate(
						params={
							"expression": """
								(function() {
									const errors = [];
									// Look for error messages anywhere on page
									document.querySelectorAll('[class*="error" i], [class*="invalid" i], [role="alert"], .text-danger').forEach(el => {
										const text = el.textContent.trim();
										if (text && text.length < 200 && text.length > 3) {
											errors.push(text);
										}
									});
									return errors;
								})();
							""",
							"returnByValue": True,
						},
						session_id=cdp_session.session_id,
					)
					errors_before = errors_check.get('result', {}).get('value', [])
					logger.debug(f"State before action: {dom_before} elements, URL: {url_before}, Errors: {len(errors_before)}")
				except Exception as e:
					logger.debug(f"Could not capture state before action: {e}")

			# STEP 2: Execute action via browser-use Tools
			# Browser-use extract action requires page_extraction_llm
			# Get LLM instance for extract actions (browser-use pattern)
			page_extraction_llm = None
			if action_type == "extract":
				from qa_agent.llm import get_llm
				page_extraction_llm = get_llm()
				logger.info(f"Extract action detected - providing page_extraction_llm to Tools.act()")
			
			# Get file_system from state (created in think node)
			file_system = None
			if action_type == "extract" or action_type in ["write_file", "read_file", "replace_file"]:
				# File system is needed for extract and file operations
				# CRITICAL: Restore FileSystem from state for todo.md persistence (Phase 1)
				from qa_agent.filesystem.file_system import FileSystem
				from pathlib import Path
				
				# Restore FileSystem from state if it exists
				file_system_state = state.get("file_system_state")
				if file_system_state:
					# Restore existing FileSystem from persisted state
					file_system = FileSystem.from_state(file_system_state)
					logger.debug("Restored FileSystem from state in act_node (todo.md preserved)")
				else:
					# Fallback: Create new FileSystem if state not available
					browser_session_id = state.get("browser_session_id", "unknown")
					file_system_dir = Path("qa_agent_workspace") / f"session_{browser_session_id[:8]}"
					file_system = FileSystem(base_dir=file_system_dir, create_default_files=False)  # Don't recreate files
					logger.debug("Created new FileSystem in act_node (fallback)")

			logger.info(f"Executing {action_type} via Tools.act()")
			result = await tools.act(
				action=action_model,
				browser_session=session,
				page_extraction_llm=page_extraction_llm,  # Required for extract actions
				file_system=file_system,  # Required for extract and file operations
			)

			# Extract all result data (browser-use ActionResult fields)
			success = result.error is None
			extracted_content = result.extracted_content
			error_msg = result.error
			is_done = result.is_done
			long_term_memory = result.long_term_memory
			include_extracted_content_only_once = result.include_extracted_content_only_once
			images = result.images
			metadata = result.metadata
			success_flag = result.success  # May be None for non-done actions

			# STEP 3: DYNAMIC VERIFICATION - Compare before/after state for ALL actions
			# This works for any action type: click, input, dropdown, etc.
			verification_msg = None
			if success and dom_before is not None and action_type in ["click", "input", "select_dropdown", "scroll"]:
				try:
					# Wait briefly for changes to settle
					await asyncio.sleep(0.2)
					
					# Get state AFTER action
					state_after = await session.get_browser_state_summary(include_screenshot=False, cached=False)
					dom_after = len(state_after.dom_state.selector_map) if state_after.dom_state else 0
					url_after = state_after.url
					title_after = state_after.title
					
					# Check for NEW errors that appeared AFTER action
					cdp_session = await session.get_or_create_cdp_session(focus=True)
					errors_check = await cdp_session.cdp_client.send.Runtime.evaluate(
						params={
							"expression": """
								(function() {
									const errors = [];
									// Look for error messages anywhere on page
									document.querySelectorAll('[class*="error" i], [class*="invalid" i], [role="alert"], .text-danger').forEach(el => {
										const text = el.textContent.trim();
										if (text && text.length < 200 && text.length > 3) {
											errors.push(text);
										}
									});
									return errors;
								})();
							""",
							"returnByValue": True,
						},
						session_id=cdp_session.session_id,
					)
					errors_after = errors_check.get('result', {}).get('value', [])
					
					# Find NEW errors (not present before)
					new_errors = [e for e in errors_after if e not in (errors_before or [])]
					
					# Analyze changes
					dom_changed = abs(dom_after - dom_before) > 2  # More than 2 elements changed
					url_changed = url_after != url_before
					title_changed = title_after != title_before
					has_new_errors = len(new_errors) > 0
					
					# Build verification message based on what changed
					changes = []
					if url_changed:
						changes.append(f"Page navigated: {url_before} → {url_after}")
					elif title_changed:
						changes.append(f"Page title changed: '{title_before}' → '{title_after}'")
					elif dom_changed:
						if dom_after > dom_before:
							changes.append(f"New content appeared ({dom_after - dom_before} new elements)")
						elif dom_after < dom_before:
							changes.append(f"Content disappeared ({dom_before - dom_after} fewer elements)")
						else:
							changes.append(f"DOM changed ({dom_after} elements)")
					
					if has_new_errors:
						changes.append(f"⚠️ Error appeared: {new_errors[0]}")
					
					if not changes and not has_new_errors:
						# No significant change detected
						if action_type == "click":
							# EXPLICIT FAILURE MARKER for clicks that don't trigger expected changes
							changes.append("⚠️ CLICK HAD NO EFFECT: No page change detected (button may be disabled, validation may be blocking, or action already completed)")
						elif action_type == "input":
							changes.append("⚠️ No DOM change detected (this may be normal for input)")
					
					if changes:
						verification_msg = " → " + "; ".join(changes)
						logger.info(f"Dynamic verification: {verification_msg}")
				
				except Exception as verify_error:
					logger.debug(f"Dynamic verification failed (non-critical): {verify_error}")
			
			# Enhance extracted_content with verification results
			if verification_msg and extracted_content:
				extracted_content = f"{extracted_content}{verification_msg}"
			elif verification_msg:
				extracted_content = verification_msg

			logger.info(f"Action {action_type} {'succeeded' if success else 'failed'}: {extracted_content or error_msg}")
			print(f"    ✅ {action_type} completed" if success else f"    ❌ {action_type} failed: {error_msg}")

			# FORM FIELD WAITING: Add small delay between form field actions for validation to settle
			# This ensures client-side validation and auto-fill logic completes before next field
			if success and action_type in ["input", "select_dropdown"] and i < len(planned_actions):
				# Check if next action is also a form field (input or dropdown)
				next_action = planned_actions[i] if i < len(planned_actions) else None
				if next_action:
					next_action_dump = next_action.model_dump(exclude_unset=True)
					next_action_type = list(next_action_dump.keys())[0] if next_action_dump else ""
					if next_action_type in ["input", "select_dropdown"]:
						# Next action is also form field - wait for validation/autofill
						logger.debug("⏳ Waiting 0.3s between form fields for validation to settle...")
						await asyncio.sleep(0.3)

			# Store complete result (all browser-use ActionResult fields)
			# Store action as dict for history serialization
			action_results.append({
				"success": success,
				"action": action_dump,  # Store as dict for JSON serialization
				"extracted_content": extracted_content,
				"error": error_msg,
				"is_done": is_done,
				"long_term_memory": long_term_memory,
				"include_extracted_content_only_once": include_extracted_content_only_once,
				"images": images,
				"metadata": metadata,
				"success_flag": success_flag,  # Browser-use success flag (None for regular actions)
			})
			executed_actions.append(action_dump)  # Store as dict for later checks
			
			# NOTE: We used to check for modals here, but removed it because:
			# 1. Browser-use doesn't do hardcoded modal detection (only handles JS dialogs via PopupsWatchdog)
			# 2. The dynamic verification system already detects DOM changes ("New content appeared", etc.)
			# 3. Hardcoded selectors don't work across all websites
			# 4. The LLM naturally sees new interactive elements in the next browser_state
			# Result: Trust the dynamic system - it's more flexible and website-agnostic

		except Exception as e:
			# Browser-use pattern: Tools.act() catches BrowserError, TimeoutError, and general exceptions
			# and returns ActionResult with error field set
			# If we get here, it's an exception during action execution
			logger.error(f"Error executing action {action_type}: {e}", exc_info=True)
			print(f"    ❌ Exception: {str(e)[:100]}")
			action_results.append({
				"success": False,
				"action": action_dump,  # Store as dict for JSON serialization
				"error": str(e),
				"extracted_content": None,
				"is_done": False,
				"long_term_memory": None,
				"include_extracted_content_only_once": False,
				"images": None,
				"metadata": None,
			})

	print(f"\n✅ Executed {len(executed_actions)}/{len(planned_actions)} actions")
	print(f"{'='*80}\n")

	# CRITICAL: Wait for DOM stability after actions (browser-use pattern)
	# This ensures dropdowns, modals, and dynamic content are fully rendered
	# before Think node analyzes the page
	logger.info("⏳ Waiting for DOM stability after actions...")
	from qa_agent.utils.dom_stability import wait_for_dom_stability, clear_cache_if_needed
	
	# Get previous URL before actions for cache clearing
	previous_url = state.get("current_url") or state.get("previous_url")
	
	# Clear cache if actions might have changed the page/DOM
	# Check all executed actions to see if any are page-changing
	# executed_actions contains action dicts (from action_dump)
	page_changing_action_types = ["navigate", "switch", "go_back"]
	dom_changing_action_types = ["click", "input", "scroll"]

	has_page_changing_action = any(
		list(a.keys())[0] in page_changing_action_types if a else False
		for a in executed_actions
	)
	has_dom_changing_action = any(
		list(a.keys())[0] in dom_changing_action_types if a else False
		for a in executed_actions
	)

	if has_page_changing_action or has_dom_changing_action:
		# Clear cache for any action that might change DOM
		action_type = list(executed_actions[-1].keys())[0] if executed_actions and executed_actions[-1] else "unknown"
		await clear_cache_if_needed(session, action_type, previous_url)
	
	# Wait for network idle and DOM stability (browser-use pattern from DOMWatchdog)
	await wait_for_dom_stability(session, max_wait_seconds=3.0)
	
	# CRITICAL: Fetch fresh browser state AFTER actions and DOM stability wait
	# This ensures Think node sees the CURRENT page state (dropdowns, modals, new content)
	# Browser-use pattern: Always get fresh state at start of next step
	logger.info("🔄 Fetching fresh browser state after actions (for Think node)...")
	fresh_browser_state = await session.get_browser_state_summary(
		include_screenshot=False,
		cached=False  # Force fresh state - critical after actions
	)
	
	# Extract key info from fresh state
	current_url = fresh_browser_state.url
	current_title = fresh_browser_state.title
	selector_map = fresh_browser_state.dom_state.selector_map if fresh_browser_state.dom_state else {}
	element_count = len(selector_map)

	logger.info(f"✅ Fresh state retrieved: {current_title[:50]} ({current_url[:60]})")
	logger.info(f"   Interactive elements: {element_count}")
	logger.info(f"   💾 Passing fresh state to Think node - LLM will see CURRENT page structure")

	# FORM STATE DETECTION: Check if we're on a form with incomplete required fields
	# This helps LLM understand "don't proceed until form is complete"
	form_state = {}
	try:
		cdp_session = await session.get_or_create_cdp_session(focus=True)
		form_check = await cdp_session.cdp_client.send.Runtime.evaluate(
			params={
				"expression": """
					(function() {
						const forms = document.querySelectorAll('form');
						const required_empty = [];
						const validation_errors = [];

						forms.forEach(form => {
							// Find required fields that are empty
							form.querySelectorAll('[required], [aria-required="true"]').forEach(field => {
								if (field.offsetParent !== null && (!field.value || field.value.trim() === '')) {
									required_empty.push({
										tag: field.tagName,
										type: field.type || 'text',
										name: field.name || field.id || 'unnamed',
										label: field.labels?.[0]?.textContent?.trim() || field.placeholder || 'unlabeled'
									});
								}
							});

							// Find visible validation errors (multiple detection strategies)
							const errorSelectors = [
								'.error', '.invalid', '.text-danger',  // Common conventions
								'[role="alert"]',  // ARIA standard
								'[class*="error" i]', '[class*="invalid" i]',  // Any class with "error"/"invalid"
								'[class*="validation" i]', '[class*="warning" i]',  // Validation/warning classes
								'.error-message', '.field-error', '.form-error',  // Specific error classes
								'.help-block.error', '.feedback.error',  // Framework patterns
								'[aria-invalid="true"] + *',  // Error message next to invalid field
								'[data-error]', '[data-validation-error]',  // Data attributes
							];

							// Deduplicate errors by text content
							const seenErrors = new Set();
							errorSelectors.forEach(selector => {
								try {
									form.querySelectorAll(selector).forEach(el => {
										// Only visible elements
										if (el.offsetParent !== null) {
											const text = el.textContent.trim();
											// Valid error: 3+ chars, not too long, not already seen
											if (text.length >= 3 && text.length <= 200 && !seenErrors.has(text)) {
												// Filter out false positives (navigation, labels, etc.)
												const lowerText = text.toLowerCase();
												const isFalsePositive =
													lowerText === 'error' ||  // Just the word "error"
													lowerText === 'required' ||  // Just the word "required"
													text.includes('Error:') && text.length < 10;  // Generic "Error:" labels

												if (!isFalsePositive) {
													validation_errors.push(text.substring(0, 100));
													seenErrors.add(text);
												}
											}
										}
									});
								} catch (e) {
									// Ignore invalid selectors
								}
							});
						});

						return {
							has_forms: forms.length > 0,
							required_empty_count: required_empty.length,
							required_empty_fields: required_empty.slice(0, 5),  // First 5 only
							validation_errors: validation_errors.slice(0, 3),  // First 3 only
							form_incomplete: required_empty.length > 0 || validation_errors.length > 0
						};
					})();
				""",
				"returnByValue": True,
			},
			session_id=cdp_session.session_id,
		)
		form_state = form_check.get('result', {}).get('value', {})

		if form_state.get('form_incomplete'):
			logger.warning(f"⚠️ FORM INCOMPLETE DETECTED: {form_state.get('required_empty_count', 0)} required fields empty, {len(form_state.get('validation_errors', []))} validation errors")
	except Exception as e:
		logger.debug(f"Form state detection failed (non-critical): {e}")
		form_state = {"has_forms": False, "form_incomplete": False}
	
	# Check for new tabs opened by actions (e.g., ChatGPT login opens new tab)
	# Browser-use pattern: detect new tabs by comparing before/after tab lists
	new_tab_id = None
	new_tab_url = None
	try:
		# Use fresh state we just fetched
		current_tabs = fresh_browser_state.tabs if fresh_browser_state.tabs else []
		current_tab_ids = [t.target_id for t in current_tabs]
		
		# Use tabs_before we captured at the start of this function
		# previous_tabs and initial_tab_count are already set above
		
		logger.info(f"📋 Comparing tabs: BEFORE={initial_tab_count} tabs, AFTER={len(current_tab_ids)} tabs")
		
		# Check if new tab was opened by comparing tab counts and IDs
		if len(current_tab_ids) > initial_tab_count:
			# Find the new tab (IDs not in previous tabs)
			logger.info(f"New tab detected: {len(current_tab_ids)} tabs (was {initial_tab_count})")
			# Get the current active tab to compare
			current_target_id = session.current_target_id
			
			# Find tabs that are new (not in previous list and not the current tab)
			new_tabs = [t for t in current_tabs if t.target_id not in previous_tabs and t.target_id != current_target_id]
			
			if new_tabs:
				# Get the most recent new tab (last in list)
				new_tab = new_tabs[-1]
				new_tab_id = new_tab.target_id
				new_tab_url = new_tab.url
				logger.info(f"New tab detected: ID={new_tab_id[-4:]}, URL={new_tab_url}")
		else:
			# No new tabs - update previous_tabs for next check
			previous_tabs = current_tab_ids.copy()
	except Exception as e:
		logger.warning(f"Could not detect new tabs: {e}", exc_info=True)
		# Fallback: use fresh state we already fetched
		try:
			current_tabs = fresh_browser_state.tabs if fresh_browser_state.tabs else []
			current_tab_ids = [t.target_id for t in current_tabs]
			previous_tabs = current_tab_ids.copy()
		except:
			current_tab_ids = []
			previous_tabs = []

	# Track consecutive failures (browser-use pattern: service.py:793-800)
	# Logic: If ALL actions failed with errors → increment failures
	#        If ANY action succeeded → reset failures to 0
	# This tracks if LLM is completely stuck vs making some progress
	consecutive_failures = state.get("consecutive_failures", 0)
	
	# CRITICAL: Detect repeated failed actions on same elements (LLM getting stuck in loop)
	# Track last 3 steps of failed actions to detect patterns
	recent_failed_actions = state.get("recent_failed_actions", [])
	
	# Collect current step's failed actions (with indices)
	current_failed = []
	for i, result in enumerate(action_results):
		# Check if action failed (has explicit failure markers or errors)
		extracted = result.get("extracted_content", "")
		error = result.get("error")
		is_failure = error or "⚠️ INPUT FAILED" in extracted or "⚠️ CLICK HAD NO EFFECT" in extracted
		
		if is_failure:
			action_data = result.get("action", {})
			# Extract action type and index for comparison
			action_type = list(action_data.keys())[0] if action_data else "unknown"
			action_params = action_data.get(action_type, {})
			if isinstance(action_params, dict):
				index = action_params.get("index")
				if index is not None:
					current_failed.append({"type": action_type, "index": index})
	
	# Check if current failed actions match recent history (same type + index repeated)
	repeated_failures = []
	for failed in current_failed:
		# Check if this exact action (type + index) failed in last 2 steps
		repeat_count = sum(
			1 for past_step in recent_failed_actions[-2:]  # Last 2 steps
			for past_action in past_step
			if past_action.get("type") == failed["type"] and past_action.get("index") == failed["index"]
		)
		if repeat_count > 0:
			repeated_failures.append(f"{failed['type']} at index {failed['index']}")
	
	# Add explicit warning to action_results if repetition detected
	if repeated_failures:
		logger.warning(f"🔁 Repeated failed actions detected: {repeated_failures}")
		# Prepend warning to first failed action's extracted_content
		for result in action_results:
			extracted = result.get("extracted_content", "")
			if "⚠️" in extracted:  # This is a failed action
				warning = f"🔁 REPEATED FAILURE DETECTED: You tried this exact action before and it failed. Try a DIFFERENT approach (different element index, click to focus first, or alternative strategy).\n{extracted}"
				result["extracted_content"] = warning
				break  # Only add warning once
	
	# Update recent failed actions history (keep last 3 steps)
	if current_failed:
		recent_failed_actions.append(current_failed)
		recent_failed_actions = recent_failed_actions[-3:]  # Keep last 3 steps
	
	# SMART FAILURE TRACKING: Detect validation errors and blocking errors
	# These indicate we're stuck on same form/page even if some actions succeeded
	validation_errors = []
	blocking_errors = []
	successes = []

	for r in action_results:
		extracted = r.get("extracted_content", "")
		error = r.get("error", "")

		# Validation errors: form validation, required fields, invalid input
		# Use comprehensive keyword list to catch different error message formats
		validation_keywords = [
			"invalid", "required", "must be", "must not", "validation", "error appeared",
			"cannot be", "should be", "please enter", "please provide", "please select",
			"format is", "does not match", "incorrect", "not valid", "not allowed",
			"minimum", "maximum", "too short", "too long", "out of range"
		]
		if any(keyword in extracted.lower() or keyword in error.lower() for keyword in validation_keywords):
			validation_errors.append(r)
		# Blocking errors: element not found, action had no effect
		elif any(keyword in extracted or keyword in error
		         for keyword in ["not found", "HAD NO EFFECT", "disabled", "not interactable", "not visible"]):
			blocking_errors.append(r)
		# Success: no error
		elif not error:
			successes.append(r)

	any_success = len(successes) > 0
	all_failed = len(successes) == 0
	has_blocking_issues = len(validation_errors) > 0 or len(blocking_errors) > 0

	# CRITICAL: Partial success WITH blocking issues = we're STUCK, not making progress
	if has_blocking_issues:
		# Even if some actions succeeded, we have validation/blocking errors
		# This means we're stuck on same form/page and need to fix errors
		consecutive_failures += 1
		logger.warning(f"🔄 PARTIAL SUCCESS WITH BLOCKING ISSUES: {len(successes)}/{len(action_results)} succeeded, BUT {len(validation_errors)} validation errors + {len(blocking_errors)} blocking errors")
		logger.warning(f"   → consecutive_failures: {consecutive_failures} (incremented because we're STUCK)")
		# Keep recent_failed_actions for context
	elif all_failed:
		# All actions failed - increment consecutive failures
		consecutive_failures += 1
		logger.debug(f"🔄 Step {state.get('step_count', 0)}: All {len(action_results)} actions failed, consecutive failures: {consecutive_failures}")
	elif any_success:
		# Pure success - no validation/blocking errors
		if consecutive_failures > 0:
			logger.debug(f"🔄 Step {state.get('step_count', 0)}: {len(successes)}/{len(action_results)} actions succeeded cleanly, resetting consecutive failures from {consecutive_failures} to 0")
			consecutive_failures = 0
		# Clear recent failed actions on clean success
		recent_failed_actions = []

	# Update history
	existing_history = state.get("history", [])
	new_history_entry = {
		"step": state.get("step_count", 0),
		"node": "act",
		"executed_actions": executed_actions,
		"action_results": action_results,
		"success_count": sum(1 for r in action_results if r.get("success")),
		"total_count": len(action_results),
		"new_tab_id": new_tab_id,  # Track if new tab was opened
		"consecutive_failures": consecutive_failures,  # Track failure count
		"screenshot_path": None,  # Will be updated after screenshot capture
	}

	# Update previous_tabs for next step comparison
	previous_tabs = current_tab_ids if 'current_tab_ids' in locals() else state.get("previous_tabs", [])
	
	# Check if any executed action was a tab switch - mark it for enhanced LLM context
	# This ensures think node provides context about the new page structure
	just_switched_tab = any(a.get("action") == "switch" for a in executed_actions)

	# SCREENSHOT CAPTURE FOR JUDGE/GIF: Capture screenshot after all actions complete
	# This allows judge evaluation and GIF generation to visualize execution
	screenshot_path = None
	try:
		screenshot_service = state.get("screenshot_service")
		if screenshot_service:
			# Capture screenshot from fresh browser state
			screenshot_b64 = fresh_browser_state.screenshot if hasattr(fresh_browser_state, 'screenshot') and fresh_browser_state.screenshot else None

			# If not in state, get fresh screenshot
			if not screenshot_b64:
				screenshot_state = await session.get_browser_state_summary(include_screenshot=True, cached=False)
				screenshot_b64 = screenshot_state.screenshot

			if screenshot_b64:
				step_number = state.get("step_count", 0)
				screenshot_path = await screenshot_service.store_screenshot(screenshot_b64, step_number)
				logger.debug(f"📸 Screenshot saved: {screenshot_path}")
				# Update history entry with screenshot path
				new_history_entry["screenshot_path"] = screenshot_path
	except Exception as e:
		logger.warning(f"Failed to capture screenshot (non-critical): {e}")

	# Build return state with fresh browser state info
	return_state = {
		"executed_actions": executed_actions,
		"action_results": action_results,
		"history": [new_history_entry],  # operator.add will append to existing (LangGraph reducer pattern)
		"consecutive_failures": consecutive_failures,  # NEW: Track failure count (browser-use pattern)
		"recent_failed_actions": recent_failed_actions,  # Track failed action patterns to detect loops
		"tab_count": len(current_tab_ids) if 'current_tab_ids' in locals() else state.get("tab_count", 1),
		"previous_tabs": previous_tabs,  # Track tabs for next comparison
		"new_tab_id": new_tab_id,  # Pass to next node for tab switching
		"new_tab_url": new_tab_url,  # Pass URL for context
		# CRITICAL: Pass fresh state to Think node (browser-use pattern: backend 1 step ahead)
		"fresh_state_available": True,  # Flag to tell Think node we have fresh state
		"fresh_browser_state_object": fresh_browser_state,  # ← FIX: Pass actual object, not just summary
		"page_changed": has_page_changing_action or (previous_url and current_url != previous_url),
		"current_url": current_url,  # Update current URL
		"browser_state_summary": {  # Store summary for Think node
			"url": current_url,
			"title": current_title,
			"element_count": element_count,
			"tabs": [{"id": t.target_id[-4:], "title": t.title, "url": t.url} for t in current_tabs],
			"screenshot_path": screenshot_path,  # For judge evaluation and GIF generation
		},
		"dom_selector_map": selector_map,  # Cache selector map for Think node
		"previous_url": current_url,  # Track URL for next step comparison
		"previous_element_count": element_count,  # Track element count for change detection
		"form_state": form_state,  # Form completion state for THINK node
		"form_incomplete": form_state.get("form_incomplete", False),  # Flag for incomplete forms
		"validation_errors_count": len(validation_errors),  # Count of validation errors
		"blocking_errors_count": len(blocking_errors),  # Count of blocking errors
	}
	
	# If we explicitly switched tabs, mark it so think node provides enhanced context
	if just_switched_tab:
		return_state["just_switched_tab"] = True
		# Use fresh state we already fetched
		return_state["tab_switch_url"] = current_url
		return_state["tab_switch_title"] = current_title
		logger.info(f"💾 Marked explicit tab switch in state - think node will provide enhanced context")
		logger.info(f"   Switch context: {current_title} ({current_url})")
	
	# CRITICAL: Update todo.md based on successful actions (moved from VERIFY since it's never called)
	# Use LLM to intelligently match successful actions to todo steps
	file_system_state = state.get("file_system_state")
	steps_marked_complete = 0
	
	# Check if we have successful actions and todo.md to update
	# Filter for successful actions only (actions that completed without errors)
	successful_actions = [r for r in action_results if r.get("success") and not r.get("error")]
	logger.info(f"ACT: Found {len(successful_actions)} successful actions out of {len(action_results)} total actions")
	
	if successful_actions and file_system_state:
		try:
			import re
			from qa_agent.filesystem.file_system import FileSystem
			file_system = FileSystem.from_state(file_system_state)
			
			# Get todo.md content
			todo_content = file_system.get_todo_contents()
			if todo_content and todo_content != '[empty todo.md, fill it when applicable]':
				# Parse current todo.md to get steps
				todo_lines = todo_content.split('\n')
				todo_steps = []
				for line in todo_lines:
					line_stripped = line.strip()
					# Handle malformed checkboxes (e.g., "- [x] - [ ]" should become "- [ ]")
					# Remove ALL checkbox patterns until we find the actual step text
					cleaned_line = line_stripped
					while re.match(r'^\s*-\s*\[[xX ]\]\s*', cleaned_line):
						cleaned_line = re.sub(r'^\s*-\s*\[[xX ]\]\s*', '', cleaned_line)
					
					# Check if this is a todo line (has checkbox pattern originally)
					if line_stripped.startswith('- [') and ('[ ]' in line_stripped or '[x]' in line_stripped or '[X]' in line_stripped):
						# Extract step text (after removing all checkbox patterns)
						step_text = cleaned_line.strip()
						if step_text:
							todo_steps.append(step_text)
				
				# Use LLM to intelligently match successful actions to todo steps
				# Only use successful actions (actions that completed without errors)
				if todo_steps and successful_actions:
					from qa_agent.utils.llm_todo_updater import llm_match_actions_to_todo_steps
					from qa_agent.llm import get_llm
					
					# Prepare successful actions with extracted_content for better LLM matching
					# successful_actions are from action_results, which have extracted_content
					# We need to convert them back to action dict format for the LLM matcher
					enriched_actions = []
					for result in successful_actions:
						# result has: {"success": True, "action": {"click": {...}}, "extracted_content": "..."}
						action_dict = result.get("action", {})
						if action_dict:
							enriched_action = action_dict.copy()
							# Add extracted_content for better matching
							if result.get("extracted_content"):
								enriched_action["extracted_content"] = result["extracted_content"]
							enriched_action["success"] = True
							enriched_actions.append(enriched_action)
					
					logger.info(f"ACT: Matching {len(enriched_actions)} actions to {len(todo_steps)} todo steps")
					logger.debug(f"ACT: Todo steps: {todo_steps[:3]}...")  # Log first 3 steps
					
					# Get LLM for todo matching
					todo_llm = get_llm()
					
					# LLM analyzes successful actions and determines which steps are complete
					completed_indices = await llm_match_actions_to_todo_steps(
						executed_actions=enriched_actions,
						todo_steps=todo_steps,
						llm=todo_llm,
					)
					
					logger.info(f"ACT: LLM returned {len(completed_indices)} completed step indices: {completed_indices}")
					
					# Update todo.md content using replace_file_str (browser-use style)
					if completed_indices:
						for step_idx in completed_indices:
							if step_idx < len(todo_steps):
								step_text = todo_steps[step_idx]
								
								# Find the exact line in todo_content (handle whitespace variations and malformed checkboxes)
								for line in todo_lines:
									line_stripped = line.strip()
									
									# Check if this line contains the step text
									# Handle malformed checkboxes: clean the line to extract step text for comparison
									cleaned_line_for_match = line_stripped
									while re.match(r'^\s*-\s*\[[xX ]\]\s*', cleaned_line_for_match):
										cleaned_line_for_match = re.sub(r'^\s*-\s*\[[xX ]\]\s*', '', cleaned_line_for_match)
									
									# Match if step text is in the cleaned line (flexible matching)
									step_text_normalized = step_text.strip().lower()
									cleaned_line_normalized = cleaned_line_for_match.strip().lower()
									
									# Use flexible matching: step text should be contained in line, or vice versa for short steps
									# Also check if key words match (for better semantic matching)
									step_words = set(step_text_normalized.split())
									line_words = set(cleaned_line_normalized.split())
									
									# Match if: step text is substring of line, OR line is substring of step, OR significant word overlap
									matches = (
										step_text_normalized in cleaned_line_normalized or
										cleaned_line_normalized in step_text_normalized or
										(len(step_words) > 0 and len(step_words & line_words) >= min(3, len(step_words) * 0.6))
									)
									
									if matches:
										# Check if line has unchecked checkbox AND not already checked
										has_unchecked = '[ ]' in line_stripped
										has_checked = '[x]' in line_stripped or '[X]' in line_stripped
										
										# Only update if it has unchecked checkbox AND not already fully checked
										if has_unchecked and not (has_checked and not has_unchecked):
											# Use the exact line from file (preserves whitespace)
											old_str = line.rstrip()  # Remove trailing newline but keep leading spaces
											
											# Fix malformed checkboxes: clean up to single - [x] format
											# Extract the actual step text (after all checkbox patterns)
											step_text_only = cleaned_line_for_match.strip()
											
											# Build clean new line: - [x] + step text
											new_str = f'- [x] {step_text_only}'
											
											# Preserve leading whitespace from original line
											leading_spaces = len(line) - len(line.lstrip())
											new_str = ' ' * leading_spaces + new_str
											
											# Use replace_file_str (browser-use method)
											result = await file_system.replace_file_str("todo.md", old_str, new_str)
											if "Successfully" in result:
												steps_marked_complete += 1
												logger.info(f"ACT: Marked todo step as complete (fixed malformed checkbox): {step_text[:50]}")
												break  # Found and updated, move to next step
						
						if steps_marked_complete > 0:
							# Save FileSystem state after todo.md updates
							file_system_state = file_system.get_state()
							logger.info(f"ACT: LLM marked {steps_marked_complete} todo step(s) as complete using replace_file (browser-use style)")
		except Exception as e:
			logger.warning(f"ACT: Failed to update todo.md with LLM: {e}", exc_info=True)
			# Continue - todo.md update is important but don't break workflow
	
	# Persist FileSystem state (always preserve, even if no file operations in this node)
	if file_system_state:
		# Always preserve FileSystem state (carry forward todo.md updates)
		return_state["file_system_state"] = file_system_state
		logger.debug("Preserved FileSystem state in act_node (todo.md preserved)")
	
	# Also persist if file operations were performed (LLM's file operations)
	file_operations_performed = any(
		a.get("action") in ["write_file", "read_file", "replace_file"]
		for a in executed_actions
	)
	
	if file_operations_performed and file_system_state:
		# Update FileSystem state if LLM performed file operations
		from qa_agent.filesystem.file_system import FileSystem
		file_system = FileSystem.from_state(file_system_state)
		file_system_state = file_system.get_state()
		return_state["file_system_state"] = file_system_state
		logger.debug("Updated FileSystem state in act_node (file operations performed)")
	
	return return_state


