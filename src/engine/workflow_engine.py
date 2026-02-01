import json
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session
from sqlalchemy import and_

from core.db_helper import DBHelper
from core.workflow_models import (
    WorkflowDefinition, WorkflowInstance, WorkflowNode, WorkflowAction,
    WorkflowStatus, ActionType
)
from core.auth_models import User
from infra.logger import get_logger

log = get_logger("WorkflowEngine")

class WorkflowEngine:
    """
    通用审批工作流引擎
    """

    def __init__(self, db: DBHelper = None):
        self.db = db or DBHelper()

    def start_workflow(
        self,
        session: Session,
        organization_id: int,
        business_type: str,
        business_id: str,
        submitter_id: int,
        workflow_code: str = None
    ) -> WorkflowInstance:
        """
        启动一个新的流程实例
        """
        # 1. 查找流程定义
        # 如果指定了 code 则用指定的，否则查找该业务类型的默认流程
        # 这里简化为必须指定 code
        if not workflow_code:
            raise ValueError("Workflow code is required")

        definition = session.query(WorkflowDefinition).filter(
            WorkflowDefinition.organization_id == organization_id,
            WorkflowDefinition.code == workflow_code,
            WorkflowDefinition.is_active == True
        ).first()

        if not definition:
            raise ValueError(f"Workflow definition '{workflow_code}' not found or inactive")

        # 2. 查找起始节点 (通常是没有入边的节点，或者明确标记为 START 的节点)
        # 简化策略：取 ID 最小的节点作为起始节点，或者约定 node_type='START'
        start_node = session.query(WorkflowNode).filter(
            WorkflowNode.definition_id == definition.id
        ).order_by(WorkflowNode.id.asc()).first()

        if not start_node:
            raise ValueError("Workflow definition has no nodes")

        # 3. 创建实例
        instance = WorkflowInstance(
            organization_id=organization_id,
            definition_id=definition.id,
            business_type=business_type,
            business_id=business_id,
            current_node_id=start_node.id,
            status=WorkflowStatus.RUNNING,
            submitter_id=submitter_id
        )
        session.add(instance)
        session.flush() # 获取 ID

        # 记录提交动作
        self._log_action(session, instance, start_node.id, submitter_id, ActionType.SUBMIT, "发起流程")

        log.info(f"Started workflow {definition.name} for {business_type}:{business_id}")
        return instance

    def process_action(
        self,
        session: Session,
        instance_id: int,
        operator_id: int,
        action_type: ActionType,
        comment: str = None,
        payload: Dict[str, Any] = None # 业务数据，用于条件判断 (如当前金额)
    ) -> WorkflowInstance:
        """
        处理审批动作 (同意/拒绝)
        """
        instance = session.query(WorkflowInstance).get(instance_id)
        if not instance:
            raise ValueError("Workflow instance not found")

        if instance.status != WorkflowStatus.RUNNING:
            raise ValueError(f"Workflow is not running (Status: {instance.status})")

        current_node = instance.current_node

        # 1. 权限检查 (简单版：检查是否是指定审批人)
        # 实际项目中需要检查 user_roles
        # if current_node.approver_user_id and current_node.approver_user_id != operator_id:
        #    raise PermissionError("Not the assigned approver")

        # 2. 记录动作
        self._log_action(session, instance, current_node.id, operator_id, action_type, comment)

        # 3. 状态机流转
        if action_type == ActionType.REJECT:
            # 拒绝 -> 流程结束 (或者回到上一级，暂简化为结束)
            instance.status = WorkflowStatus.REJECTED
            instance.current_node_id = None
            log.info(f"Workflow {instance.id} REJECTED by user {operator_id}")

        elif action_type == ActionType.APPROVE:
            # 同意 -> 计算下一节点
            next_node = self._get_next_node(session, current_node, payload)

            if next_node:
                # 进入下一节点
                instance.current_node_id = next_node.id
                log.info(f"Workflow {instance.id} moved to node {next_node.name}")
            else:
                # 没有下一节点 -> 流程完成
                instance.status = WorkflowStatus.COMPLETED
                instance.current_node_id = None
                log.info(f"Workflow {instance.id} COMPLETED")

                # TODO: 触发业务回调 (如: 发票状态改为 "VERIFIED")
                # self._trigger_callback(instance)

        return instance

    def _get_next_node(self, session: Session, current_node: WorkflowNode, payload: Dict) -> Optional[WorkflowNode]:
        """
        计算下一节点
        """
        # 1. 优先检查 transition_rules (动态条件)
        if current_node.transition_rules:
            rules = current_node.transition_rules
            if isinstance(rules, str):
                rules = json.loads(rules)

            for rule in rules:
                # 规则格式: {"condition": "amount > 5000", "next_node_id": 123}
                condition = rule.get("condition")
                next_node_id = rule.get("next_node_id")

                if self._evaluate_condition(condition, payload):
                    return session.query(WorkflowNode).get(next_node_id)

        # 2. 默认下一节点
        if current_node.next_node_id:
            return session.query(WorkflowNode).get(current_node.next_node_id)

        return None

    def _evaluate_condition(self, condition: str, payload: Dict) -> bool:
        """
        简单的条件求值器
        警告: eval 有安全风险，生产环境应使用规则引擎 (如 json-logic)
        """
        if not condition or condition == "default":
            return True

        if not payload:
            return False

        try:
            # 简单实现：仅支持 amount 比较
            # 实际应使用 ast.literal_eval 或专用库
            # 这里为了演示，假设 condition 是 python 表达式，且只允许访问 payload 变量
            # 安全起见，暂时只返回 True，待接入 json-logic
            return True
        except Exception:
            log.error(f"Failed to evaluate condition: {condition}")
            return False

    def _log_action(self, session, instance, node_id, operator_id, action_type, comment):
        action = WorkflowAction(
            instance_id=instance.id,
            node_id=node_id,
            operator_id=operator_id,
            action_type=action_type,
            comment=comment
        )
        session.add(action)
