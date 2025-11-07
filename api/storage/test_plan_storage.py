"""
In-Memory Test Plans Storage

Stores test plans in a dictionary during runtime.
"""
import uuid
from datetime import datetime
from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)

# Global storage - maps test_plan_id -> test_plan_dict
_TEST_PLANS: Dict[str, dict] = {}


def create_test_plan(
    name: str,
    description: str,
    url: str,
    website_name: Optional[str] = None
) -> dict:
    """Create a new test plan"""
    test_plan_id = str(uuid.uuid4())
    test_plan = {
        "id": test_plan_id,
        "name": name or description[:50],  # Use description as name if not provided
        "description": description,
        "url": url,
        "website_name": website_name,
        "status": "pending",  # pending, running, completed, failed
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat(),
    }
    _TEST_PLANS[test_plan_id] = test_plan
    logger.info(f"Created test plan: {test_plan_id}")
    return test_plan


def get_test_plan(test_plan_id: str) -> Optional[dict]:
    """Get test plan by ID"""
    return _TEST_PLANS.get(test_plan_id)


def get_all_test_plans() -> List[dict]:
    """Get all test plans"""
    return list(_TEST_PLANS.values())


def update_test_plan(test_plan_id: str, **updates) -> Optional[dict]:
    """Update test plan fields"""
    if test_plan_id not in _TEST_PLANS:
        return None
    
    test_plan = _TEST_PLANS[test_plan_id]
    test_plan.update(updates)
    test_plan["updated_at"] = datetime.utcnow().isoformat()
    return test_plan


def delete_test_plan(test_plan_id: str) -> bool:
    """Delete test plan"""
    if test_plan_id in _TEST_PLANS:
        del _TEST_PLANS[test_plan_id]
        logger.info(f"Deleted test plan: {test_plan_id}")
        return True
    return False

