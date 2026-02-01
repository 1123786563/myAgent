from typing import List, Optional, Dict, Any
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Body
from pydantic import BaseModel
from sqlalchemy import or_

from core.db_helper import DBHelper
from core.workflow_models import (
    WorkflowInstance, WorkflowAction, WorkflowNode, WorkflowStatus, ActionType
)
from auth.middleware.auth_middleware import get_current_user, CurrentUser
from engine.workflow_engine import WorkflowEngine
from infra.logger import get_logger

router = APIRouter(prefix="/workflow", tags=["Workflow"])
log = get_logger("WorkflowAPI")

# --- Schemas ---

class WorkflowSubmitRequest(BaseModel):
    workflow_code: str
    business_type: str
    business_id: str
    comment: Optional[str] = None

class WorkflowActionRequest(BaseModel):
    instance_id: int
    action_type: str  # APPROVE, REJECT
    comment: Optional[str] = None
    payload: Optional[Dict[str, Any]] = None  # 业务数据，用于条件判断

class WorkflowTaskSchema(BaseModel):
    id: int
    business_type: str
    business_id: str
    current_node_name: Optional[str]
    status: str
    submitter_id: Optional[int]
    created_at: datetime

    class Config:
        from_attributes = True

class WorkflowActionSchema(BaseModel):
    id: int
    node_name: Optional[str]
    operator_name: Optional[str] # 需要关联 User 表获取
    action_type: str
    comment: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True

# --- API Endpoints ---

@router.post("/submit", summary="发起审批流程")
async def submit_workflow(
    request: WorkflowSubmitRequest,
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    提交一个新的审批申请
    """
    db = DBHelper()
    engine = WorkflowEngine(db)

    try:
        with db.transaction() as session:
            instance = engine.start_workflow(
                session=session,
                organization_id=current_user.organization_id,
                business_type=request.business_type,
                business_id=request.business_id,
                submitter_id=current_user.user_id,
                workflow_code=request.workflow_code
            )
            return {"message": "Workflow started", "instance_id": instance.id}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        log.error(f"Submit workflow failed: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("/action", summary="处理审批动作")
async def process_workflow_action(
    request: WorkflowActionRequest,
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    审批人执行动作 (同意/拒绝)
    """
    db = DBHelper()
    engine = WorkflowEngine(db)

    try:
        action_enum = ActionType(request.action_type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid action type: {request.action_type}")

    try:
        with db.transaction() as session:
            # 检查实例是否存在且属于该租户
            instance = session.query(WorkflowInstance).filter(
                WorkflowInstance.id == request.instance_id,
                WorkflowInstance.organization_id == current_user.organization_id
            ).first()

            if not instance:
                raise HTTPException(status_code=404, detail="Workflow instance not found")

            # 简单的权限检查：当前节点是否指派给了该用户
            # 注意：实际生产中需要更复杂的检查 (Role, User, Delegations)
            if instance.current_node:
                 node = instance.current_node
                 if node.approver_user_id and node.approver_user_id != current_user.user_id:
                     # 如果指定了具体人，必须匹配
                     raise HTTPException(status_code=403, detail="You are not the assigned approver")

                 # 如果指定了角色，需要检查用户是否有该角色 (简化版：暂时跳过)

            engine.process_action(
                session=session,
                instance_id=request.instance_id,
                operator_id=current_user.user_id,
                action_type=action_enum,
                comment=request.comment,
                payload=request.payload
            )
            return {"message": f"Action {request.action_type} processed"}

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        log.error(f"Process action failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/tasks/pending", response_model=List[WorkflowTaskSchema], summary="我的待办任务")
async def list_pending_tasks(
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    查询当前用户需要处理的审批任务
    """
    db = DBHelper()
    with db.transaction() as session:
        # 查找当前节点是该用户(或者该用户角色)的任务
        # 简化版：只查 approver_user_id 匹配，或者 node_type='USER' 且无特定指定（假设所有人可见）
        query = session.query(WorkflowInstance).join(WorkflowNode, WorkflowInstance.current_node_id == WorkflowNode.id).filter(
            WorkflowInstance.organization_id == current_user.organization_id,
            WorkflowInstance.status == WorkflowStatus.RUNNING,
            or_(
                WorkflowNode.approver_user_id == current_user.user_id,
                # WorkflowNode.approver_role_id.in_(current_user.role_ids) # 需要获取用户角色ID列表
            )
        )

        tasks = query.all()
        # 转换数据以匹配 Schema (处理 lazy loading)
        results = []
        for t in tasks:
            results.append(WorkflowTaskSchema(
                id=t.id,
                business_type=t.business_type,
                business_id=t.business_id,
                current_node_name=t.current_node.name if t.current_node else None,
                status=t.status.value,
                submitter_id=t.submitter_id,
                created_at=t.created_at
            ))
        return results

@router.get("/history/{instance_id}", response_model=List[WorkflowActionSchema], summary="审批历史")
async def get_workflow_history(
    instance_id: int,
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    查看流程的审批记录
    """
    db = DBHelper()
    with db.transaction() as session:
        actions = session.query(WorkflowAction).filter(
            WorkflowAction.instance_id == instance_id
        ).order_by(WorkflowAction.created_at.asc()).all()

        results = []
        for a in actions:
            results.append(WorkflowActionSchema(
                id=a.id,
                node_name=a.node.name if a.node else "Start",
                operator_name=str(a.operator_id), # 暂时用 ID，实际应关联 User 表
                action_type=a.action_type.value,
                comment=a.comment,
                created_at=a.created_at
            ))
        return results
