from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    Numeric,
    DateTime,
    JSON,
    Text,
    Date,
    ForeignKey,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy.sql import func
import os
from dotenv import load_dotenv

# 尝试导入 pgvector，如果失败则使用替代方案
try:
    from pgvector.sqlalchemy import Vector
    VECTOR_AVAILABLE = True
except ImportError:
    VECTOR_AVAILABLE = False
    # 如果 pgvector 不可用，使用 Text 作为替代
    Vector = Text

load_dotenv()

Base = declarative_base()


class TenantMixin:
    tenant_id = Column(String(50), nullable=False, index=True)


class AccountingCategoryEmbedding(TenantMixin, Base):
    """
    [Optimization] Vector store for semantic accounting classification
    """

    __tablename__ = "accounting_category_embeddings"
    id = Column(Integer, primary_key=True, autoincrement=True)
    category = Column(String, nullable=False)
    description = Column(
        Text, nullable=False
    )  # The text used to generate embedding (e.g., "Taxi receipt for travel")
    embedding = Column(Vector(1536))  # OpenAI text-embedding-3-small dimension
    source = Column(String, default="SYSTEM")  # SYSTEM, MANUAL, LEARNING
    created_at = Column(DateTime, server_default=func.now())


# 如果没有 vector 扩展，动态修改表定义
if not VECTOR_AVAILABLE:
    # 将 embedding 列类型改为 Text
    AccountingCategoryEmbedding.embedding.type = Text()
    AccountingCategoryEmbedding.__table__.columns.embedding.type = Text()


class SysConfig(Base):
    __tablename__ = "sys_config"
    key = Column(String, primary_key=True)
    value = Column(String)


class SysStatus(Base):
    __tablename__ = "sys_status"
    service_name = Column(String, primary_key=True)
    last_heartbeat = Column(DateTime)
    status = Column(String)
    metrics = Column(JSON)
    lock_owner = Column(String)


class SystemEvent(Base):
    __tablename__ = "system_events"
    id = Column(Integer, primary_key=True, autoincrement=True)
    event_type = Column(String)
    service_name = Column(String)
    message = Column(Text)
    trace_id = Column(String)
    created_at = Column(DateTime, server_default=func.now())


class Transaction(TenantMixin, Base):
    __tablename__ = "transactions"
    id = Column(Integer, primary_key=True, autoincrement=True)
    status = Column(String)
    amount = Column(Numeric(10, 2))
    vendor = Column(String)
    category = Column(String)
    trace_id = Column(String, unique=True)
    created_at = Column(DateTime, server_default=func.now())
    logical_revert = Column(Integer, default=0)
    prev_hash = Column(Text)
    chain_hash = Column(Text)
    inference_log = Column(JSON)
    group_id = Column(String)
    file_path = Column(Text)
    file_hash = Column(String, index=True)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    tags = relationship("TransactionTag", back_populates="transaction")


class TransactionTag(TenantMixin, Base):
    __tablename__ = "transaction_tags"
    id = Column(Integer, primary_key=True, autoincrement=True)
    transaction_id = Column(Integer, ForeignKey("transactions.id"))
    tag_key = Column(String)
    tag_value = Column(String)
    transaction = relationship("Transaction", back_populates="tags")


class PendingEntry(TenantMixin, Base):
    __tablename__ = "pending_entries"
    id = Column(Integer, primary_key=True, autoincrement=True)
    amount = Column(Numeric(10, 2))
    vendor_keyword = Column(String)
    status = Column(String, default="PENDING")
    created_at = Column(DateTime, server_default=func.now())


class TrialBalance(TenantMixin, Base):
    __tablename__ = "trial_balance"
    account_code = Column(String, primary_key=True)
    debit_total = Column(Numeric(15, 2), default=0)
    credit_total = Column(Numeric(15, 2), default=0)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class ROIMetricsHistory(TenantMixin, Base):
    __tablename__ = "roi_metrics_history"
    report_date = Column(Date, primary_key=True)
    human_hours_saved = Column(Numeric(10, 2))
    token_spend_usd = Column(Numeric(10, 4))
    roi_ratio = Column(Numeric(10, 2))


class KnowledgeBase(TenantMixin, Base):
    __tablename__ = "knowledge_base"
    id = Column(Integer, primary_key=True, autoincrement=True)
    entity_name = Column(String, unique=True)
    category_mapping = Column(String)
    audit_status = Column(String, default="GRAY")
    consecutive_success = Column(Integer, default=0)
    reject_count = Column(Integer, default=0)
    hit_count = Column(Integer, default=0)
    quality_score = Column(Numeric(3, 2), default=1.0)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


# Database configuration
from core.config_manager import ConfigManager

POSTGRES_HOST = ConfigManager.get_str("db.host", "localhost")
POSTGRES_PORT = ConfigManager.get("db.port", 5432)
POSTGRES_USER = ConfigManager.get_str("db.user", "postgres")
POSTGRES_PASSWORD = ConfigManager.get_str("db.password", "postgres")
POSTGRES_DBNAME = ConfigManager.get_str("db.name", "ledger_alpha")

DATABASE_URL = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DBNAME}"

engine = create_engine(DATABASE_URL, pool_size=10, max_overflow=20)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
