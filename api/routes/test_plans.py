"""
Test Plans API Routes

Uses in-memory storage for test plans and execution history.
Wraps existing workflow execution without modifying core logic.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List
import asyncio
import logging

from api.storage.test_plan_storage import (
    create_test_plan,
    get_test_plan,
    get_all_test_plans,
    update_test_plan,
    delete_test_plan,
)
from api.storage.execution_storage import (
    create_execution,
    update_execution,
    add_execution_log,
    get_executions_by_test_plan,
)
from api.services.websocket_manager import websocket_manager
from api.routes.workflow import get_workflow
from qa_agent.state import create_initial_state
from qa_agent.config import settings

logger = logging.getLogger(__name__)
router = APIRouter()


class TestPlanRequest(BaseModel):
    """Request model for creating a test plan"""
    description: str = Field(..., description="Test description or instruction")
    url: str = Field(..., description="Initial URL to navigate to")
    website_name: Optional[str] = Field(default=None, description="Optional website name")
    max_steps: Optional[int] = Field(default=50, ge=1, le=200, description="Maximum steps allowed")


class TestPlanResponse(BaseModel):
    """Response model for test plan"""
    id: str
    name: str
    description: str
    url: str
    website_name: Optional[str]
    status: str
    created_at: str


@router.get("/tests/test-plans", response_model=dict)
async def list_test_plans():
    """Get all test plans"""
    test_plans = get_all_test_plans()
    return {"test_plans": test_plans}


@router.post("/tests/test-plans", response_model=TestPlanResponse)
async def create_test_plan_endpoint(request: TestPlanRequest):
    """
    Create a new test plan and start execution
    
    This endpoint:
    1. Creates a test plan in memory storage
    2. Creates an execution record
    3. Starts workflow execution in background (non-blocking)
    4. Returns immediately with test plan info
    """
    try:
        # 1. Create test plan in storage
        test_plan = create_test_plan(
            name=request.description[:50] if len(request.description) > 50 else request.description,
            description=request.description,
            url=request.url,
            website_name=request.website_name,
        )
        
        # 2. Create execution record
        execution = create_execution(
            test_plan_id=test_plan["id"],
            status="running"
        )
        
        # 3. Update test plan status
        update_test_plan(test_plan["id"], status="running")
        
        # 4. Broadcast via WebSocket
        await websocket_manager.broadcast({
            "type": "test_plan_created",
            "test_id": execution["id"],
            "test_plan_id": test_plan["id"],
            "timestamp": execution["started_at"],
            "data": {
                "name": test_plan["name"],
                "status": "running"
            }
        })
        
        # 5. Start workflow execution in background (NON-BLOCKING)
        # This wraps the existing workflow without modifying it
        asyncio.create_task(
            run_workflow_async(
                execution_id=execution["id"],
                test_plan_id=test_plan["id"],
                task=request.description,
                start_url=request.url,
                max_steps=request.max_steps or 50
            )
        )
        
        return test_plan
        
    except Exception as e:
        logger.error(f"Error creating test plan: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tests/test-plans/{test_plan_id}", response_model=dict)
async def get_test_plan_endpoint(test_plan_id: str):
    """Get test plan details with execution history"""
    test_plan = get_test_plan(test_plan_id)
    if not test_plan:
        raise HTTPException(status_code=404, detail="Test plan not found")
    
    # Get execution history
    executions = get_executions_by_test_plan(test_plan_id)
    
    return {
        "test_plan": test_plan,
        "executions": executions
    }


@router.delete("/tests/test-plans/{test_plan_id}")
async def delete_test_plan_endpoint(test_plan_id: str):
    """Delete a test plan"""
    if delete_test_plan(test_plan_id):
        return {"message": "Test plan deleted successfully"}
    else:
        raise HTTPException(status_code=404, detail="Test plan not found")


async def run_workflow_async(
    execution_id: str,
    test_plan_id: str,
    task: str,
    start_url: str,
    max_steps: int = 50
):
    """
    Run workflow asynchronously and track progress
    
    This function wraps the existing workflow execution without modifying it.
    It tracks progress and broadcasts updates via WebSocket.
    """
    try:
        # Broadcast start
        await websocket_manager.broadcast({
            "type": "test_update",
            "test_id": execution_id,
            "data": {
                "status": "running",
                "message": "Workflow started"
            }
        })
        
        add_execution_log(execution_id, "INFO", f"Starting workflow execution with max_steps={max_steps}")
        
        # Create initial state (EXISTING FUNCTION - NO CHANGES)
        initial_state = create_initial_state(
            task=task,
            start_url=start_url,
            max_steps=max_steps,
        )
        
        # Get workflow (EXISTING FUNCTION - NO CHANGES)
        workflow = get_workflow()
        
        # Run workflow (EXISTING FUNCTION - NO CHANGES)
        # This is the core workflow execution - we don't modify it
        result = await workflow.ainvoke(
            initial_state,
            config={"recursion_limit": 200}
        )
        
        # Extract results
        completed = result.get("completed", False)
        step_count = result.get("step_count", 0)
        error = result.get("error")
        
        # Update execution with result
        update_execution(
            execution_id,
            status="completed" if completed else "failed",
            step_count=step_count,
            current_step=step_count,
            total_steps=max_steps,
            workflow_result=result,
            error=error,
        )
        
        # Update test plan status
        update_test_plan(
            test_plan_id,
            status="completed" if completed else "failed"
        )
        
        # Add completion log
        if completed:
            add_execution_log(execution_id, "INFO", f"Workflow completed successfully in {step_count} steps")
        else:
            add_execution_log(execution_id, "ERROR", f"Workflow failed: {error or 'Unknown error'}")
        
        # Broadcast completion
        await websocket_manager.broadcast({
            "type": "test_update",
            "test_id": execution_id,
            "data": {
                "status": "completed" if completed else "failed",
                "message": "Workflow completed" if completed else f"Workflow failed: {error or 'Unknown error'}",
                "step_count": step_count
            }
        })
        
    except Exception as e:
        logger.error(f"Error in workflow execution: {e}")
        update_execution(execution_id, status="failed", error=str(e))
        update_test_plan(test_plan_id, status="failed")
        add_execution_log(execution_id, "ERROR", f"Execution error: {str(e)}")
        
        await websocket_manager.broadcast({
            "type": "test_update",
            "test_id": execution_id,
            "data": {
                "status": "failed",
                "message": f"Execution error: {str(e)}"
            }
        })

