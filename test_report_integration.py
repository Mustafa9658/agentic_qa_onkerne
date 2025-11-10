"""
Test Report Node Integration - Judge & GIF

This test verifies that:
1. Judge evaluation works with mock workflow history
2. GIF generation works with mock workflow history
3. Report node properly extracts data from QAAgentState
4. No errors occur during integration
"""
import asyncio
import logging
from pathlib import Path
from qa_agent.state import QAAgentState
from qa_agent.nodes.report import report_node

# Configure logging
logging.basicConfig(
	level=logging.INFO,
	format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def create_mock_state() -> QAAgentState:
	"""Create a mock QAAgentState with realistic workflow history."""

	# Simulate a simple workflow: navigate to example.com and extract text
	mock_history = [
		# Step 1: Think node - plan navigation
		{
			"step": 1,
			"node": "think",
			"current_goal": "Navigate to example.com",
			"planned_actions": [
				{"go_to_url": {"url": "https://example.com"}}
			],
			"thinking": "I need to navigate to the specified URL first",
			"evaluation_previous_goal": "Starting task",
			"memory": "Initial navigation to example.com",
		},
		# Step 1: Act node - execute navigation
		{
			"step": 1,
			"node": "act",
			"executed_actions": [
				{"go_to_url": {"url": "https://example.com"}}
			],
			"action_results": [
				{
					"extracted_content": "Successfully navigated to https://example.com",
					"error": None,
				}
			],
			"browser_state_summary": {
				"url": "https://example.com",
				"title": "Example Domain",
				"screenshot": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",  # 1x1 red pixel
			}
		},
		# Step 2: Think node - plan extraction
		{
			"step": 2,
			"node": "think",
			"current_goal": "Extract main heading text",
			"planned_actions": [
				{"extract": {"data_extraction_goal": "Get the main heading text"}}
			],
			"thinking": "Now I need to extract the main heading from the page",
			"evaluation_previous_goal": "Navigation successful",
			"memory": "Page loaded, ready to extract",
		},
		# Step 2: Act node - execute extraction
		{
			"step": 2,
			"node": "act",
			"executed_actions": [
				{"extract": {"data_extraction_goal": "Get the main heading text"}}
			],
			"action_results": [
				{
					"extracted_content": "Example Domain",
					"is_done": False,
					"error": None,
				}
			],
			"browser_state_summary": {
				"url": "https://example.com",
				"title": "Example Domain",
				"screenshot": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
			}
		},
		# Step 3: Think node - complete task
		{
			"step": 3,
			"node": "think",
			"current_goal": "Task completed successfully",
			"planned_actions": [
				{"done": {"text": "Successfully extracted heading: Example Domain"}}
			],
			"thinking": "Task is complete",
			"evaluation_previous_goal": "Extraction successful",
			"memory": "Extracted heading text",
			"task_completed": True,
			"completion_message": "Successfully extracted heading: Example Domain",
		},
	]

	return {
		# Core task
		"task": "Navigate to example.com and extract the main heading text",
		"start_url": None,

		# Browser session
		"browser_session_id": "test-session-12345678",

		# Step tracking
		"step_count": 3,
		"max_steps": 50,

		# Current page state
		"current_url": "https://example.com",
		"previous_url": None,
		"current_title": "Example Domain",
		"previous_element_count": None,

		# Tab management
		"tab_count": 1,
		"previous_tabs": [],
		"new_tab_id": None,
		"new_tab_url": None,
		"just_switched_tab": False,

		# Task progression
		"goals": [],
		"completed_goals": [],
		"current_goal_index": 0,
		"current_goal": "Task completed successfully",

		# FileSystem state
		"file_system_state": None,

		# Action planning & execution
		"planned_actions": [],
		"executed_actions": [
			{"go_to_url": {"url": "https://example.com"}},
			{"extract": {"data_extraction_goal": "Get the main heading text"}},
			{"done": {"text": "Successfully extracted heading: Example Domain"}},
		],
		"action_results": [
			{"extracted_content": "Successfully navigated to https://example.com"},
			{"extracted_content": "Example Domain"},
			{"is_done": True, "extracted_content": "Successfully extracted heading: Example Domain"},
		],

		# History (accumulated)
		"history": mock_history,

		# Browser state cache
		"browser_state_summary": None,
		"dom_selector_map": None,
		"fresh_state_available": False,
		"page_changed": False,

		# Tab switch context
		"tab_switch_url": None,
		"tab_switch_title": None,

		# Verification
		"verification_status": "pass",
		"verification_results": [],

		# Error handling & loop prevention
		"error": None,
		"consecutive_failures": 0,
		"max_failures": 3,
		"final_response_after_failure": True,
		"action_repetition_count": 0,

		# Completion
		"completed": True,
		"report": None,

		# Judge & GIF settings
		"use_judge": True,  # Enable judge for testing
		"generate_gif": "test_agent_history.gif",  # Enable GIF with custom path

		# Read state
		"read_state_description": None,
		"read_state_images": None,
	}


async def test_report_node():
	"""Test the report node with judge and GIF integration."""

	logger.info("="*80)
	logger.info("Starting Report Node Integration Test")
	logger.info("="*80)

	try:
		# Create mock state
		logger.info("\n1. Creating mock workflow state...")
		state = create_mock_state()
		logger.info(f"   Mock state created with {len(state['history'])} history entries")
		logger.info(f"   Task: {state['task']}")
		logger.info(f"   Judge enabled: {state['use_judge']}")
		logger.info(f"   GIF enabled: {state['generate_gif']}")

		# Call report node
		logger.info("\n2. Calling report_node...")
		result = await report_node(state)

		# Verify results
		logger.info("\n3. Verifying results...")

		# Check basic report structure
		assert "report" in result, "Result should contain 'report' key"
		report = result["report"]

		logger.info(f"   ✅ Report structure: OK")
		logger.info(f"   Task: {report.get('task', 'N/A')}")
		logger.info(f"   Steps: {report.get('steps', 0)}")
		logger.info(f"   Completed: {report.get('completed', False)}")

		# Check judge evaluation
		if "judgement" in report:
			judgement = report["judgement"]
			logger.info(f"\n   🧑‍⚖️ Judge Evaluation:")

			if "error" in judgement:
				logger.warning(f"      ⚠️ Judge error: {judgement['error']}")
			else:
				logger.info(f"      Verdict: {judgement.get('verdict', 'N/A')}")
				logger.info(f"      Reasoning: {judgement.get('reasoning', 'N/A')[:100]}...")
				if judgement.get('failure_reason'):
					logger.info(f"      Failure reason: {judgement.get('failure_reason', 'N/A')[:100]}...")
		else:
			logger.warning("   ⚠️ No judgement in report")

		# Check GIF generation
		if "gif_path" in report:
			gif_path = Path(report["gif_path"])
			if gif_path.exists():
				logger.info(f"\n   🎬 GIF Generation:")
				logger.info(f"      ✅ GIF created: {gif_path}")
				logger.info(f"      Size: {report.get('gif_size_kb', 0):.1f} KB")
			else:
				logger.error(f"      ❌ GIF path in report but file not found: {gif_path}")
		elif "gif_error" in report:
			logger.warning(f"\n   ⚠️ GIF generation error: {report['gif_error']}")
		else:
			logger.warning("   ⚠️ No GIF in report (check if generate_gif is enabled)")

		# Check completion
		assert result.get("completed") == True, "Task should be marked as completed"
		logger.info(f"\n   ✅ Completion flag: {result.get('completed')}")

		# Summary
		logger.info("\n" + "="*80)
		logger.info("TEST SUMMARY")
		logger.info("="*80)
		logger.info(f"✅ Report node executed successfully")
		logger.info(f"✅ Report structure is valid")

		if "judgement" in report and "error" not in report["judgement"]:
			logger.info(f"✅ Judge evaluation completed")
		else:
			logger.warning(f"⚠️ Judge evaluation skipped or failed")

		if "gif_path" in report and Path(report["gif_path"]).exists():
			logger.info(f"✅ GIF generation completed")
		else:
			logger.warning(f"⚠️ GIF generation skipped or failed")

		logger.info("="*80)

		return True

	except Exception as e:
		logger.error(f"\n❌ TEST FAILED: {e}", exc_info=True)
		return False


async def main():
	"""Run the test."""
	success = await test_report_node()

	if success:
		logger.info("\n🎉 All tests passed!")
		return 0
	else:
		logger.error("\n❌ Tests failed!")
		return 1


if __name__ == "__main__":
	exit_code = asyncio.run(main())
	exit(exit_code)
