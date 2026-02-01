from sqlalchemy import (
    Column, Integer, String, DateTime, ForeignKey,
    Text, Boolean, JSON, Index, Enum as SQLEnum
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from core.db_models import Base
import enum

class WorkflowStatus(enum.Enum):
    """流程状态"""
    DRAFT = "DRAFT"           # 草稿
    RUNNING = "RUNNING"       # 进行中
    COMPLETED = "COMPLETED"   # 已完成 (通过)
    REJECTED = "REJECTED"     # 已拒绝 (终止)
    CANCELLED = "CANCELLED"   # 已取消

class ActionType(enum.Enum):
    """审批动作类型"""
    SUBMIT = "SUBMIT"         # 提交
    APPROVE = "APPROVE"       # 同意
    REJECT = "REJECT"         # 拒绝
    RETURN = "RETURN"         # 退回 (到上一级)
    TRANSFER = "TRANSFER"     # 转交
    COMMENT = "COMMENT"       # 仅评论

class WorkflowDefinition(Base):
    """
    流程定义表 (如: 报销审批流 V1)
    """
    __tablename__ = 'workflow_definitions'

    id = Column(Integer, primary_key=True, autoincrement=True)
    organization_id = Column(Integer, ForeignKey('organizations.id'), nullable=False)

    name = Column(String(100), nullable=False)
    code = Column(String(50), nullable=False) # 业务编码, 如 EXPENSE_FLOW
    description = Column(Text)

    # 版本控制
    version = Column(Integer, default=1)
    is_active = Column(Boolean, default=True)

    # 流程配置 (全局配置)
    config = Column(JSON) # { "allow_revoke": true }

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # 关系
    nodes = relationship("WorkflowNode", back_populates="definition", cascade="all, delete-orphan")

    __table_args__ = (
        Index('ix_wf_def_org_code', 'organization_id', 'code'),
    )

class WorkflowNode(Base):
    """
    流程节点表
    """
    __tablename__ = 'workflow_nodes'

    id = Column(Integer, primary_key=True, autoincrement=True)
    definition_id = Column(Integer, ForeignKey('workflow_definitions.id'), nullable=False)

    name = Column(String(50), nullable=False) # 节点名称: "经理审批"
    node_type = Column(String(20), default="USER") # USER, SYSTEM, START, END

    # 审批人配置
    approver_role_id = Column(Integer, ForeignKey('roles.id')) # 按角色
    approver_user_id = Column(Integer, ForeignKey('users.id')) # 指定人

    # 逻辑配置
    next_node_id = Column(Integer, ForeignKey('workflow_nodes.id')) # 默认下一节点 (简单线性流程)

    # 复杂流转条件 (JSON)
    # [
    #   {"condition": "amount > 5000", "next_node_code": "CEO_APPROVAL"},
    #   {"condition": "default", "next_node_code": "FINANCE_REVIEW"}
    # ]
    transition_rules = Column(JSON)

    __table_args__ = (
        Index('ix_wf_node_def', 'definition_id'),
    )

    # 关系
    definition = relationship("WorkflowDefinition", back_populates="nodes")

class WorkflowInstance(Base):
    """
    流程实例 (具体的审批单)
    """
    __tablename__ = 'workflow_instances'

    id = Column(Integer, primary_key=True, autoincrement=True)
    organization_id = Column(Integer, ForeignKey('organizations.id'), nullable=False)

    definition_id = Column(Integer, ForeignKey('workflow_definitions.id'), nullable=False)

    # 关联业务对象
    business_type = Column(String(50), nullable=False) # INVOICE, REIMBURSEMENT
    business_id = Column(String(50), nullable=False)

    # 当前状态
    current_node_id = Column(Integer, ForeignKey('workflow_nodes.id'))
    status = Column(SQLEnum(WorkflowStatus), default=WorkflowStatus.RUNNING)

    # 发起人
    submitter_id = Column(Integer, ForeignKey('users.id'))

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # 关系
    actions = relationship("WorkflowAction", back_populates="instance")
    definition = relationship("WorkflowDefinition")
    current_node = relationship("WorkflowNode", foreign_keys=[current_node_id])

    __table_args__ = (
        Index('ix_wf_inst_biz', 'organization_id', 'business_type', 'business_id'),
        Index('ix_wf_inst_submitter', 'submitter_id'),
    )

class WorkflowAction(Base):
    """
    审批动作历史 (审计轨迹)
    """
    __tablename__ = 'workflow_actions'

    id = Column(Integer, primary_key=True, autoincrement=True)
    instance_id = Column(Integer, ForeignKey('workflow_instances.id'), nullable=False)

    node_id = Column(Integer, ForeignKey('workflow_nodes.id')) # 在哪个节点操作的
    operator_id = Column(Integer, ForeignKey('users.id')) # 操作人

    action_type = Column(SQLEnum(ActionType), nullable=False)
    comment = Column(Text) # 审批意见

    created_at = Column(DateTime, server_default=func.now())

    # 关系
    instance = relationship("WorkflowInstance", back_populates="actions")
    node = relationship("WorkflowNode")
