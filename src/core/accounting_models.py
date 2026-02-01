"""
会计科目体系数据库模型
Chart of Accounts Database Models
"""

from sqlalchemy import (
    Column, Integer, String, DateTime, Boolean, ForeignKey,
    Numeric, Text, Index, Enum as SQLEnum, CheckConstraint
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from core.db_models import Base
import enum


class AccountType(str, enum.Enum):
    """科目类型"""
    ASSET = "ASSET"              # 资产
    LIABILITY = "LIABILITY"      # 负债
    EQUITY = "EQUITY"            # 权益
    REVENUE = "REVENUE"          # 收入
    EXPENSE = "EXPENSE"          # 费用


class BalanceDirection(str, enum.Enum):
    """余额方向"""
    DEBIT = "DEBIT"    # 借方
    CREDIT = "CREDIT"  # 贷方


class AccountCategory(str, enum.Enum):
    """科目分类 (中国会计准则)"""
    # 资产类
    CASH = "CASH"                          # 库存现金
    BANK = "BANK"                          # 银行存款
    RECEIVABLE = "RECEIVABLE"              # 应收账款
    PREPAID = "PREPAID"                    # 预付账款
    INVENTORY = "INVENTORY"                # 存货
    FIXED_ASSET = "FIXED_ASSET"            # 固定资产
    INTANGIBLE = "INTANGIBLE"              # 无形资产
    OTHER_ASSET = "OTHER_ASSET"            # 其他资产

    # 负债类
    PAYABLE = "PAYABLE"                    # 应付账款
    ADVANCE = "ADVANCE"                    # 预收账款
    TAX_PAYABLE = "TAX_PAYABLE"            # 应交税费
    SALARY_PAYABLE = "SALARY_PAYABLE"      # 应付职工薪酬
    OTHER_LIABILITY = "OTHER_LIABILITY"    # 其他负债

    # 权益类
    CAPITAL = "CAPITAL"                    # 实收资本
    RESERVE = "RESERVE"                    # 资本公积/盈余公积
    RETAINED_EARNINGS = "RETAINED_EARNINGS" # 未分配利润

    # 收入类
    MAIN_REVENUE = "MAIN_REVENUE"          # 主营业务收入
    OTHER_REVENUE = "OTHER_REVENUE"        # 其他业务收入
    NON_OPERATING_INCOME = "NON_OPERATING_INCOME"  # 营业外收入

    # 费用类
    MAIN_COST = "MAIN_COST"                # 主营业务成本
    OPERATING_EXPENSE = "OPERATING_EXPENSE" # 销售费用
    ADMIN_EXPENSE = "ADMIN_EXPENSE"        # 管理费用
    FINANCE_EXPENSE = "FINANCE_EXPENSE"    # 财务费用
    RD_EXPENSE = "RD_EXPENSE"              # 研发费用
    TAX_EXPENSE = "TAX_EXPENSE"            # 税金及附加
    NON_OPERATING_EXPENSE = "NON_OPERATING_EXPENSE"  # 营业外支出


class Account(Base):
    """
    会计科目表 (Chart of Accounts)
    支持多级科目结构
    """
    __tablename__ = 'accounts'

    id = Column(Integer, primary_key=True, autoincrement=True)
    organization_id = Column(Integer, ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False)

    # 科目编码 (如: 1001, 1001.01, 1001.01.001)
    code = Column(String(50), nullable=False)
    name = Column(String(100), nullable=False)
    full_name = Column(String(255))  # 完整名称 (包含上级科目)

    # 科目属性
    account_type = Column(SQLEnum(AccountType), nullable=False)
    category = Column(SQLEnum(AccountCategory))
    balance_direction = Column(SQLEnum(BalanceDirection), nullable=False)

    # 层级结构
    level = Column(Integer, default=1)  # 科目级次 (1=一级, 2=二级, ...)
    parent_id = Column(Integer, ForeignKey('accounts.id', ondelete='CASCADE'))
    is_leaf = Column(Boolean, default=True)  # 是否末级科目 (只有末级科目可记账)

    # 辅助核算
    enable_auxiliary = Column(Boolean, default=False)  # 是否启用辅助核算
    auxiliary_types = Column(String(255))  # 辅助核算类型 (如: "CUSTOMER,PROJECT")

    # 状态
    is_active = Column(Boolean, default=True)
    is_system = Column(Boolean, default=False)  # 系统预置科目不可删除

    # 期初余额
    opening_balance = Column(Numeric(18, 2), default=0)
    opening_balance_direction = Column(SQLEnum(BalanceDirection))

    # 描述
    description = Column(Text)

    # 时间戳
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # 关系
    parent = relationship("Account", remote_side=[id], backref="children")
    voucher_items = relationship("VoucherItem", back_populates="account")
    balances = relationship("AccountBalance", back_populates="account")

    __table_args__ = (
        Index('ix_accounts_org_code', 'organization_id', 'code', unique=True),
        Index('ix_accounts_parent', 'parent_id'),
        Index('ix_accounts_type', 'account_type'),
        CheckConstraint('level >= 1 AND level <= 6', name='ck_accounts_level'),
    )


class AccountingPeriod(Base):
    """会计期间"""
    __tablename__ = 'accounting_periods'

    id = Column(Integer, primary_key=True, autoincrement=True)
    organization_id = Column(Integer, ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False)

    year = Column(Integer, nullable=False)
    month = Column(Integer, nullable=False)  # 1-12
    name = Column(String(50))  # 如: "2024年1月"

    start_date = Column(DateTime, nullable=False)
    end_date = Column(DateTime, nullable=False)

    is_closed = Column(Boolean, default=False)  # 是否已结账
    closed_at = Column(DateTime)
    closed_by = Column(Integer, ForeignKey('users.id'))

    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        Index('ix_periods_org_year_month', 'organization_id', 'year', 'month', unique=True),
    )


class Voucher(Base):
    """
    会计凭证 (记账凭证)
    """
    __tablename__ = 'vouchers'

    id = Column(Integer, primary_key=True, autoincrement=True)
    organization_id = Column(Integer, ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False)

    # 凭证字号
    voucher_type = Column(String(10), default='记')  # 记、收、付、转
    voucher_number = Column(Integer, nullable=False)  # 凭证号
    voucher_date = Column(DateTime, nullable=False)  # 凭证日期

    # 期间
    period_id = Column(Integer, ForeignKey('accounting_periods.id'))
    year = Column(Integer)
    month = Column(Integer)

    # 摘要
    summary = Column(String(500))

    # 附件数
    attachment_count = Column(Integer, default=0)

    # 状态
    status = Column(String(20), default='DRAFT')  # DRAFT, PENDING, APPROVED, POSTED, CANCELLED

    # 关联原始交易
    transaction_id = Column(Integer, ForeignKey('transactions.id'))

    # 创建与审核
    created_by = Column(Integer, ForeignKey('users.id'))
    reviewed_by = Column(Integer, ForeignKey('users.id'))
    posted_by = Column(Integer, ForeignKey('users.id'))

    reviewed_at = Column(DateTime)
    posted_at = Column(DateTime)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # 关系
    items = relationship("VoucherItem", back_populates="voucher", cascade="all, delete-orphan")

    __table_args__ = (
        Index('ix_vouchers_org_date', 'organization_id', 'voucher_date'),
        Index('ix_vouchers_org_number', 'organization_id', 'year', 'month', 'voucher_type', 'voucher_number', unique=True),
        Index('ix_vouchers_status', 'status'),
        Index('ix_vouchers_transaction', 'transaction_id'),
    )


class VoucherItem(Base):
    """
    凭证分录 (借贷方明细)
    """
    __tablename__ = 'voucher_items'

    id = Column(Integer, primary_key=True, autoincrement=True)
    voucher_id = Column(Integer, ForeignKey('vouchers.id', ondelete='CASCADE'), nullable=False)
    account_id = Column(Integer, ForeignKey('accounts.id'), nullable=False)

    # 借贷方向
    direction = Column(SQLEnum(BalanceDirection), nullable=False)

    # 金额 (只填借方或贷方)
    amount = Column(Numeric(18, 2), nullable=False)

    # 分录摘要 (可覆盖凭证摘要)
    summary = Column(String(255))

    # 辅助核算
    auxiliary_customer = Column(String(100))  # 客户
    auxiliary_supplier = Column(String(100))  # 供应商
    auxiliary_project = Column(String(100))   # 项目
    auxiliary_department = Column(String(100)) # 部门
    auxiliary_employee = Column(String(100))  # 员工

    # 数量金额核算
    quantity = Column(Numeric(18, 4))
    unit_price = Column(Numeric(18, 4))
    unit = Column(String(20))

    # 外币核算
    currency = Column(String(10), default='CNY')
    exchange_rate = Column(Numeric(18, 6), default=1)
    foreign_amount = Column(Numeric(18, 2))

    # 排序
    seq = Column(Integer, default=0)

    created_at = Column(DateTime, server_default=func.now())

    # 关系
    voucher = relationship("Voucher", back_populates="items")
    account = relationship("Account", back_populates="voucher_items")

    __table_args__ = (
        Index('ix_voucher_items_voucher', 'voucher_id'),
        Index('ix_voucher_items_account', 'account_id'),
        CheckConstraint('amount >= 0', name='ck_voucher_items_amount'),
    )


class AccountBalance(Base):
    """
    科目余额表 (按期间汇总)
    """
    __tablename__ = 'account_balances'

    id = Column(Integer, primary_key=True, autoincrement=True)
    organization_id = Column(Integer, ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False)
    account_id = Column(Integer, ForeignKey('accounts.id', ondelete='CASCADE'), nullable=False)

    year = Column(Integer, nullable=False)
    month = Column(Integer, nullable=False)

    # 期初余额
    opening_debit = Column(Numeric(18, 2), default=0)
    opening_credit = Column(Numeric(18, 2), default=0)

    # 本期发生额
    period_debit = Column(Numeric(18, 2), default=0)
    period_credit = Column(Numeric(18, 2), default=0)

    # 本年累计
    ytd_debit = Column(Numeric(18, 2), default=0)
    ytd_credit = Column(Numeric(18, 2), default=0)

    # 期末余额
    closing_debit = Column(Numeric(18, 2), default=0)
    closing_credit = Column(Numeric(18, 2), default=0)

    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # 关系
    account = relationship("Account", back_populates="balances")

    __table_args__ = (
        Index('ix_balances_org_account_period', 'organization_id', 'account_id', 'year', 'month', unique=True),
    )


class VoucherTemplate(Base):
    """凭证模板 (常用分录模板)"""
    __tablename__ = 'voucher_templates'

    id = Column(Integer, primary_key=True, autoincrement=True)
    organization_id = Column(Integer, ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False)

    name = Column(String(100), nullable=False)
    description = Column(Text)
    voucher_type = Column(String(10), default='记')

    # 模板内容 (JSON 格式的分录模板)
    template_data = Column(Text)  # JSON: [{account_code, direction, amount_formula, summary}, ...]

    is_active = Column(Boolean, default=True)
    usage_count = Column(Integer, default=0)

    created_by = Column(Integer, ForeignKey('users.id'))
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index('ix_templates_org', 'organization_id'),
    )
