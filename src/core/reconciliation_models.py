from sqlalchemy import (
    Column, Integer, String, DateTime, Numeric, ForeignKey,
    Text, Boolean, JSON, Index, Enum as SQLEnum
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from core.db_models import Base
import enum

class ReconciliationStatus(enum.Enum):
    """对账状态"""
    UNRECONCILED = "UNRECONCILED" # 未对账
    PARTIAL = "PARTIAL"           # 部分对账 (金额不完全匹配)
    MATCHED = "MATCHED"           # 已匹配 (等待确认)
    RECONCILED = "RECONCILED"     # 已对账 (最终确认)
    IGNORED = "IGNORED"           # 已忽略

class MatchMethod(enum.Enum):
    """匹配方式"""
    AUTO_RULE = "AUTO_RULE"       # 规则自动匹配
    AI_SUGGESTION = "AI_SUGGESTION" # AI 推荐
    MANUAL = "MANUAL"             # 人工强制匹配

class BankStatement(Base):
    """
    标准化的银行/第三方支付流水表
    所有外部流水 (支付宝, 微信, 银行) 导入后都转换为此格式
    """
    __tablename__ = 'bank_statements'

    id = Column(Integer, primary_key=True, autoincrement=True)
    organization_id = Column(Integer, ForeignKey('organizations.id'), nullable=False)

    # 来源信息
    source_type = Column(String(50), nullable=False)  # ALIPAY, WECHAT, CMB, ICBC
    account_number = Column(String(100)) # 银行账号或支付宝账号

    # 交易详情
    transaction_date = Column(DateTime, nullable=False)
    amount = Column(Numeric(18, 2), nullable=False) # 正数收入，负数支出
    currency = Column(String(10), default='CNY')

    # 对方信息
    counterparty_name = Column(String(200))
    counterparty_account = Column(String(100))

    # 标识
    external_id = Column(String(100), nullable=False) # 外部流水号 (用于去重)
    reference_code = Column(String(100)) # 业务关联码 (如订单号)

    # 备注
    description = Column(Text)
    raw_data = Column(JSON) # 原始数据备份

    # 对账状态
    status = Column(SQLEnum(ReconciliationStatus), default=ReconciliationStatus.UNRECONCILED)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # 关系
    reconciliation_logs = relationship("ReconciliationLog", back_populates="statement")

    __table_args__ = (
        Index('ix_bank_stmt_org_source_ext', 'organization_id', 'source_type', 'external_id', unique=True),
        Index('ix_bank_stmt_status', 'status'),
        Index('ix_bank_stmt_date', 'transaction_date'),
    )

class ReconciliationRule(Base):
    """
    对账规则配置
    """
    __tablename__ = 'reconciliation_rules'

    id = Column(Integer, primary_key=True, autoincrement=True)
    organization_id = Column(Integer, ForeignKey('organizations.id'), nullable=False)

    name = Column(String(100), nullable=False)
    priority = Column(Integer, default=0) # 优先级，高优先执行

    # 匹配条件 (JSON 存储)
    # {
    #   "amount_tolerance": 0.01,
    #   "date_range_days": 3,
    #   "match_fields": ["order_no", "remark"]
    # }
    conditions = Column(JSON, nullable=False)

    # 自动执行动作
    auto_approve = Column(Boolean, default=False) # 是否自动确认

    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())

class ReconciliationLog(Base):
    """
    对账记录表 (连接 流水 和 系统交易)
    """
    __tablename__ = 'reconciliation_logs'

    id = Column(Integer, primary_key=True, autoincrement=True)
    organization_id = Column(Integer, ForeignKey('organizations.id'), nullable=False)

    # 关联双方
    statement_id = Column(Integer, ForeignKey('bank_statements.id'), nullable=False)
    transaction_id = Column(Integer, ForeignKey('transactions.id'), nullable=True) # 对应的系统交易

    # 匹配详情
    match_method = Column(SQLEnum(MatchMethod), nullable=False)
    score = Column(Numeric(5, 4)) # 匹配置信度 (0.00-1.00)
    match_reason = Column(String(500)) # 匹配原因 (如 "金额一致, 备注包含订单号")

    # 状态
    is_confirmed = Column(Boolean, default=False)
    confirmed_by = Column(Integer, ForeignKey('users.id'))
    confirmed_at = Column(DateTime)

    created_at = Column(DateTime, server_default=func.now())

    # 关系
    statement = relationship("BankStatement", back_populates="reconciliation_logs")
    # transaction = relationship("Transaction") # 需在 db_models 中添加反向关系

    __table_args__ = (
        Index('ix_recon_log_stmt', 'statement_id'),
        Index('ix_recon_log_trans', 'transaction_id'),
    )
