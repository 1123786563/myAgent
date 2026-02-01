"""
测试配置和 Fixtures
Test Configuration and Fixtures
"""

import pytest
import os
import sys
from datetime import datetime, date
from decimal import Decimal
from typing import Generator
from unittest.mock import MagicMock, patch

# 添加 src 到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

# 使用内存数据库进行测试
TEST_DATABASE_URL = "sqlite:///:memory:"


@pytest.fixture(scope="session")
def engine():
    """创建测试数据库引擎"""
    engine = create_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool
    )
    return engine


@pytest.fixture(scope="session")
def tables(engine):
    """创建所有表"""
    from core.db_models import Base
    from core.auth_models import Base as AuthBase
    from core.accounting_models import Base as AccountingBase
    from core.invoice_models import Base as InvoiceBase

    # 创建表
    Base.metadata.create_all(engine)
    AuthBase.metadata.create_all(engine)
    AccountingBase.metadata.create_all(engine)
    InvoiceBase.metadata.create_all(engine)

    yield

    # 清理
    Base.metadata.drop_all(engine)


@pytest.fixture
def db_session(engine, tables) -> Generator[Session, None, None]:
    """创建测试数据库会话"""
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def mock_db_helper(db_session):
    """Mock DBHelper"""
    with patch('core.db_helper.DBHelper') as mock:
        instance = MagicMock()
        instance.transaction.return_value.__enter__ = MagicMock(return_value=db_session)
        instance.transaction.return_value.__exit__ = MagicMock(return_value=False)
        mock.return_value = instance
        yield instance


@pytest.fixture
def test_organization(db_session):
    """创建测试组织"""
    from core.auth_models import Organization

    org = Organization(
        name="测试公司",
        code="TEST001",
        tax_id="91110000MA00000X00",
        is_active=True
    )
    db_session.add(org)
    db_session.commit()
    db_session.refresh(org)
    return org


@pytest.fixture
def test_user(db_session, test_organization):
    """创建测试用户"""
    from core.auth_models import User
    import uuid

    user = User(
        uuid=str(uuid.uuid4()),
        organization_id=test_organization.id,
        email="test@example.com",
        password_hash="$2b$12$test_hash",
        full_name="测试用户",
        is_active=True,
        is_verified=True
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def test_accounts(db_session, test_organization):
    """创建测试科目"""
    from core.accounting_models import Account, AccountType, BalanceDirection

    accounts = []
    test_accounts_data = [
        {"code": "1001", "name": "库存现金", "type": AccountType.ASSET, "direction": BalanceDirection.DEBIT},
        {"code": "1002", "name": "银行存款", "type": AccountType.ASSET, "direction": BalanceDirection.DEBIT},
        {"code": "2202", "name": "应付账款", "type": AccountType.LIABILITY, "direction": BalanceDirection.CREDIT},
        {"code": "5001", "name": "主营业务收入", "type": AccountType.REVENUE, "direction": BalanceDirection.CREDIT},
        {"code": "5601", "name": "销售费用", "type": AccountType.EXPENSE, "direction": BalanceDirection.DEBIT},
    ]

    for data in test_accounts_data:
        account = Account(
            organization_id=test_organization.id,
            code=data["code"],
            name=data["name"],
            full_name=data["name"],
            account_type=data["type"],
            balance_direction=data["direction"],
            level=1,
            is_leaf=True,
            is_system=True,
            is_active=True
        )
        db_session.add(account)
        accounts.append(account)

    db_session.commit()
    return accounts


@pytest.fixture
def api_client():
    """创建 API 测试客户端"""
    from api.api_server import app
    return TestClient(app)


@pytest.fixture
def auth_headers(test_user):
    """创建认证头"""
    # 模拟 JWT token
    return {"Authorization": "Bearer test_token"}


# ==================== 常用测试数据 ====================

@pytest.fixture
def sample_voucher_items():
    """示例凭证分录"""
    return [
        {"account_code": "1001", "direction": "DEBIT", "amount": 1000.00, "summary": "收到现金"},
        {"account_code": "5001", "direction": "CREDIT", "amount": 1000.00, "summary": "销售收入"},
    ]


@pytest.fixture
def sample_invoice_data():
    """示例发票数据"""
    return {
        "invoice_code": "1234567890",
        "invoice_number": "12345678",
        "invoice_type": "VAT_NORMAL",
        "direction": "INPUT",
        "invoice_date": date.today().isoformat(),
        "amount_without_tax": 1000.00,
        "tax_amount": 130.00,
        "buyer_name": "测试公司",
        "seller_name": "供应商公司",
        "buyer_tax_id": "91110000MA00000X00",
        "seller_tax_id": "91110000MA00000Y00"
    }
