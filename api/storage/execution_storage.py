"""
In-Memory Execution History Storage

Tracks workflow executions linked to test plans.
"""
import uuid
from datetime import datetime
from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)

# Global storage - maps execution_id -> execution_dict
_EXECUTIONS: Dict[str, dict] = {}

# Index: maps test_plan_id -> list of execution_ids
_TEST_PLAN_EXECUTIONS: Dict[str, List[str]] = {}


def create_execution(
    test_plan_id: str,
    status: str = "running"
) -> dict:
    """Create a new execution record"""
    execution_id = str(uuid.uuid4())
    execution = {
        "id": execution_id,
        "test_plan_id": test_plan_id,
        "status": status,  # running, completed, failed
        "step_count": 0,
        "current_step": 0,
        "total_steps": 0,
        "current_action": None,
        "started_at": datetime.utcnow().isoformat(),
        "ended_at": None,
        "workflow_result": None,
        "logs": [],
        "error": None,
    }
    
    _EXECUTIONS[execution_id] = execution
    
    # Add to test plan's execution list
    if test_plan_id not in _TEST_PLAN_EXECUTIONS:
        _TEST_PLAN_EXECUTIONS[test_plan_id] = []
    _TEST_PLAN_EXECUTIONS[test_plan_id].append(execution_id)
    
    logger.info(f"Created execution: {execution_id} for test plan: {test_plan_id}")
    return execution


def get_execution(execution_id: str) -> Optional[dict]:
    """Get execution by ID"""
    return _EXECUTIONS.get(execution_id)


def get_executions_by_test_plan(test_plan_id: str) -> List[dict]:
    """Get all executions for a test plan"""
    execution_ids = _TEST_PLAN_EXECUTIONS.get(test_plan_id, [])
    return [_EXECUTIONS[eid] for eid in execution_ids if eid in _EXECUTIONS]


def update_execution(execution_id: str, **updates) -> Optional[dict]:
    """Update execution fields"""
    if execution_id not in _EXECUTIONS:
        return None
    
    execution = _EXECUTIONS[execution_id]
    execution.update(updates)
    
    # Auto-update ended_at if status changed to completed/failed
    if "status" in updates and updates["status"] in ["completed", "failed"]:
        if execution["ended_at"] is None:
            execution["ended_at"] = datetime.utcnow().isoformat()
    
    return execution


def add_execution_log(execution_id: str, level: str, message: str, step: Optional[int] = None):
    """Add a log entry to execution"""
    if execution_id not in _EXECUTIONS:
        return
    
    log_entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "level": level,  # INFO, WARNING, ERROR
        "message": message,
        "step": step,
    }
    _EXECUTIONS[execution_id]["logs"].append(log_entry)

