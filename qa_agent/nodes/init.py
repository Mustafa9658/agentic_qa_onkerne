"""
INIT Node: Initialize browser session at workflow start

This node creates the BrowserSession connected to kernel-image CDP
and prepares it for use by THINK and ACT nodes.
"""
import logging
import re
from typing import Any, Dict, Optional

from qa_agent.state import QAAgentState
from qa_agent.utils.browser_manager import create_browser_session

logger = logging.getLogger(__name__)


def _extract_url_from_task(task: str) -> Optional[str]:
	"""Extract URL from task string using browser-use pattern matching.
	
	Args:
		task: Task string that may contain a URL
		
	Returns:
		Extracted URL if exactly one found, None otherwise
	"""
	# Remove email addresses from task before looking for URLs
	task_without_emails = re.sub(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', '', task)

	# Look for common URL patterns (browser-use pattern)
	patterns = [
		r'https?://[^\s<>"\']+',  # Full URLs with http/https
		r'(?:www\.)?[a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]+)*\.[a-zA-Z]{2,}(?:/[^\s<>"\']*)?',  # Domain names with subdomains and optional paths
	]

	# File extensions that should be excluded from URL detection
	excluded_extensions = {
		'pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx', 'odt', 'ods', 'odp',
		'txt', 'md', 'csv', 'json', 'xml', 'yaml', 'yml',
		'zip', 'rar', '7z', 'tar', 'gz', 'bz2', 'xz',
		'jpg', 'jpeg', 'png', 'gif', 'bmp', 'svg', 'webp', 'ico',
		'mp3', 'mp4', 'avi', 'mkv', 'mov', 'wav', 'flac', 'ogg',
		'py', 'js', 'css', 'java', 'cpp',
		'bib', 'bibtex', 'tex', 'latex', 'cls', 'sty',
		'exe', 'msi', 'dmg', 'pkg', 'deb', 'rpm', 'iso',
	}

	excluded_words = {'never', 'dont', 'not', "don't"}

	found_urls = []
	for pattern in patterns:
		matches = re.finditer(pattern, task_without_emails)
		for match in matches:
			url = match.group(0)
			original_position = match.start()

			# Remove trailing punctuation that's not part of URLs
			url = re.sub(r'[.,;:!?()\[\]]+$', '', url)

			# Check if URL ends with a file extension that should be excluded
			url_lower = url.lower()
			should_exclude = False
			for ext in excluded_extensions:
				if f'.{ext}' in url_lower:
					should_exclude = True
					break

			if should_exclude:
				logger.debug(f'Excluding URL with file extension from auto-navigation: {url}')
				continue

			# If in the 20 characters before the url position is a word in excluded_words skip
			context_start = max(0, original_position - 20)
			context_text = task_without_emails[context_start:original_position]
			if any(word.lower() in context_text.lower() for word in excluded_words):
				logger.debug(
					f'Excluding URL with word in excluded words from auto-navigation: {url} (context: "{context_text.strip()}")'
				)
				continue

			# Add https:// if missing
			if not url.startswith(('http://', 'https://')):
				url = 'https://' + url

			found_urls.append(url)

	unique_urls = list(set(found_urls))
	# If multiple URLs found, skip auto-navigation to avoid ambiguity
	if len(unique_urls) > 1:
		logger.debug(f'Multiple URLs found ({len(unique_urls)}), skipping auto-navigation to avoid ambiguity')
		return None

	# If exactly one URL found, return it
	if len(unique_urls) == 1:
		return unique_urls[0]

	return None


async def init_node(state: QAAgentState) -> Dict[str, Any]:
	"""Initialize browser session for the workflow.

	Args:
		state: Current workflow state (may contain start_url or task with URL)

	Returns:
		Dict with browser_session_id and current_url
	"""
	logger.info("INIT: Starting browser session initialization")

	# Get start URL from state if provided, otherwise extract from task (browser-use pattern)
	start_url = state.get("start_url")
	if not start_url:
		task = state.get("task", "")
		if task:
			extracted_url = _extract_url_from_task(task)
			if extracted_url:
				start_url = extracted_url
				logger.info(f"INIT: Extracted URL from task: {start_url}")

	# Create browser session (this connects to kernel-image CDP)
	logger.info(f"INIT: Creating browser session{' with start_url=' + start_url if start_url else ''}")
	session_id, session = await create_browser_session(start_url=start_url)

	logger.info(f"INIT: Browser session created successfully: {session_id}")

	# Get current URL after navigation
	current_url = None
	if start_url:
		try:
			current_url = await session.get_current_page_url()
			logger.info(f"INIT: Navigated to {current_url}")
		except Exception as e:
			logger.warning(f"INIT: Could not get current page URL: {e}")
			current_url = start_url  # Fallback to requested URL

	# Initialize tab tracking for new tab detection (browser-use pattern)
	tab_count = 1  # Start with 1 tab
	previous_tabs = []  # Track tab IDs for comparison
	try:
		browser_state = await session.get_browser_state_summary(include_screenshot=False)
		if browser_state.tabs:
			tab_count = len(browser_state.tabs)
			previous_tabs = [t.target_id for t in browser_state.tabs]  # Track initial tabs
			logger.info(f"INIT: Initial tabs: {tab_count} tabs detected")
	except Exception as e:
		logger.debug(f"Could not get initial tab count: {e}")

	return {
		"browser_session_id": session_id,
		"current_url": current_url,
		"tab_count": tab_count,  # Track tab count for new tab detection
		"previous_tabs": previous_tabs,  # Track tab IDs for comparison after actions
	}
