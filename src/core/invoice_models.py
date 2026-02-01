"""
发票管理数据模型
Invoice Management Models - VAT Invoice, Invoice Verification
"""

from sqlalchemy import (
    Column, Integer, String, Text, Boolean, DateTime, Date,
    Numeric, ForeignKey, Enum as SQLEnum, Index, UniqueConstraint
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from datetime import datetime
from decimal import Decimal
import enum
from core.db_models import Base


class InvoiceType(enum.Enum):
    """发票类型"""
    VAT_SPECIAL = "VAT_SPECIAL"           # 增值税专用发票
    VAT_NORMAL = "VAT_NORMAL"             # 增值税普通发票
    VAT_ELECTRONIC = "VAT_ELECTRONIC"     # 增值税电子发票
    VAT_ROLL = "VAT_ROLL"                 # 增值税卷票
    MOTOR_VEHICLE = "MOTOR_VEHICLE"       # 机动车销售发票
    TOLL = "TOLL"                         # 通行费发票
    OTHER = "OTHER"                       # 其他发票


class InvoiceDirection(enum.Enum):
    """发票方向"""
    INPUT = "INPUT"     # 进项发票 (采购)
    OUTPUT = "OUTPUT"   # 销项发票 (销售)


class InvoiceStatus(enum.Enum):
    """发票状态"""
    DRAFT = "DRAFT"           # 草稿
    PENDING = "PENDING"       # 待验证
    VERIFIED = "VERIFIED"     # 已验证
    MATCHED = "MATCHED"       # 已匹配交易
    POSTED = "POSTED"         # 已入账
    VOIDED = "VOIDED"         # 已作废
    REJECTED = "REJECTED"     # 验证失败


class TaxRate(enum.Enum):
    """税率"""
    RATE_0 = "0"        # 0%
    RATE_1 = "1"        # 1%
    RATE_3 = "3"        # 3%
    RATE_5 = "5"        # 5%
    RATE_6 = "6"        # 6%
    RATE_9 = "9"        # 9%
    RATE_13 = "13"      # 13%
    EXEMPT = "EXEMPT"   # 免税


class Invoice(Base):
    """发票主表"""
    __tablename__ = "invoices"

    id = Column(Integer, primary_key=True, autoincrement=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)

    # 发票基本信息
    invoice_code = Column(String(20), nullable=False, comment="发票代码")
    invoice_number = Column(String(20), nullable=False, comment="发票号码")
    invoice_type = Column(SQLEnum(InvoiceType), nullable=False, comment="发票类型")
    direction = Column(SQLEnum(InvoiceDirection), nullable=False, comment="进项/销项")
    status = Column(SQLEnum(InvoiceStatus), default=InvoiceStatus.DRAFT, comment="状态")

    # 日期信息
    invoice_date = Column(Date, nullable=False, comment="开票日期")
    check_code = Column(String(50), comment="校验码 (后6位)")

    # 金额信息
    amount_without_tax = Column(Numeric(18, 2), nullable=False, comment="不含税金额")
    tax_amount = Column(Numeric(18, 2), nullable=False, comment="税额")
    total_amount = Column(Numeric(18, 2), nullable=False, comment="价税合计")
    tax_rate = Column(SQLEnum(TaxRate), comment="税率")

    # 购买方信息 (进项发票时为本公司)
    buyer_name = Column(String(200), nullable=False, comment="购买方名称")
    buyer_tax_id = Column(String(30), comment="购买方税号")
    buyer_address_phone = Column(String(200), comment="购买方地址电话")
    buyer_bank_account = Column(String(200), comment="购买方开户行及账号")

    # 销售方信息 (销项发票时为本公司)
    seller_name = Column(String(200), nullable=False, comment="销售方名称")
    seller_tax_id = Column(String(30), comment="销售方税号")
    seller_address_phone = Column(String(200), comment="销售方地址电话")
    seller_bank_account = Column(String(200), comment="销售方开户行及账号")

    # 备注
    remark = Column(Text, comment="备注")
    machine_code = Column(String(20), comment="机器编号")

    # 验证信息
    verification_result = Column(Text, comment="验证结果 (JSON)")
    verified_at = Column(DateTime, comment="验证时间")
    verified_by = Column(Integer, ForeignKey("users.id"), comment="验证人")

    # 关联信息
    transaction_id = Column(Integer, ForeignKey("transactions.id"), comment="关联交易")
    voucher_id = Column(Integer, ForeignKey("vouchers.id"), comment="关联凭证")

    # 附件
    attachment_url = Column(String(500), comment="发票图片/PDF URL")
    ocr_raw_data = Column(Text, comment="OCR 识别原始数据 (JSON)")

    # 审计字段
    created_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # 关系
    items = relationship("InvoiceItem", back_populates="invoice", cascade="all, delete-orphan")
    organization = relationship("Organization")

    __table_args__ = (
        UniqueConstraint("organization_id", "invoice_code", "invoice_number", name="uq_invoice_code_number"),
        Index("idx_invoice_org_date", "organization_id", "invoice_date"),
        Index("idx_invoice_status", "organization_id", "status"),
        Index("idx_invoice_direction", "organization_id", "direction"),
    )


class InvoiceItem(Base):
    """发票明细行"""
    __tablename__ = "invoice_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id"), nullable=False)

    seq = Column(Integer, nullable=False, comment="行号")
    goods_name = Column(String(200), nullable=False, comment="货物或服务名称")
    specification = Column(String(100), comment="规格型号")
    unit = Column(String(20), comment="单位")
    quantity = Column(Numeric(18, 6), comment="数量")
    unit_price = Column(Numeric(18, 6), comment="单价")
    amount = Column(Numeric(18, 2), nullable=False, comment="金额")
    tax_rate = Column(SQLEnum(TaxRate), comment="税率")
    tax_amount = Column(Numeric(18, 2), comment="税额")

    # 商品分类编码 (税收分类编码)
    goods_code = Column(String(30), comment="商品编码")
    tax_category_code = Column(String(30), comment="税收分类编码")

    # 关系
    invoice = relationship("Invoice", back_populates="items")

    __table_args__ = (
        Index("idx_invoice_item_invoice", "invoice_id"),
    )


class InvoiceVerificationLog(Base):
    """发票验证日志"""
    __tablename__ = "invoice_verification_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id"), nullable=False)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)

    # 验证请求
    request_data = Column(Text, comment="验证请求数据 (JSON)")
    response_data = Column(Text, comment="验证响应数据 (JSON)")

    # 验证结果
    is_valid = Column(Boolean, comment="是否有效")
    error_code = Column(String(50), comment="错误代码")
    error_message = Column(String(500), comment="错误信息")

    # 验证来源
    verification_source = Column(String(50), comment="验证来源: TAX_BUREAU/THIRD_PARTY")

    created_at = Column(DateTime, default=func.now())
    created_by = Column(Integer, ForeignKey("users.id"))

    __table_args__ = (
        Index("idx_verification_log_invoice", "invoice_id"),
    )


class TaxDeclaration(Base):
    """税务申报记录"""
    __tablename__ = "tax_declarations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)

    # 申报期间
    tax_period = Column(String(10), nullable=False, comment="税款所属期 (YYYY-MM)")
    declaration_type = Column(String(50), nullable=False, comment="申报类型: VAT/INCOME_TAX/...")

    # 进项税
    input_tax_amount = Column(Numeric(18, 2), default=Decimal('0'), comment="进项税额")
    input_invoice_count = Column(Integer, default=0, comment="进项发票数量")

    # 销项税
    output_tax_amount = Column(Numeric(18, 2), default=Decimal('0'), comment="销项税额")
    output_invoice_count = Column(Integer, default=0, comment="销项发票数量")

    # 应纳税额
    tax_payable = Column(Numeric(18, 2), default=Decimal('0'), comment="应纳税额")
    tax_credit = Column(Numeric(18, 2), default=Decimal('0'), comment="留抵税额")

    # 状态
    status = Column(String(20), default="DRAFT", comment="DRAFT/SUBMITTED/CONFIRMED")
    submitted_at = Column(DateTime, comment="申报时间")

    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("organization_id", "tax_period", "declaration_type", name="uq_tax_declaration"),
        Index("idx_tax_declaration_period", "organization_id", "tax_period"),
    )
