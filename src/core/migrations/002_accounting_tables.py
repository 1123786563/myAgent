"""
数据库迁移: 会计模块表
Migration: Accounting Tables
"""

from sqlalchemy import text

MIGRATION_ID = "002_accounting_tables"
DESCRIPTION = "Create accounting tables (accounts, vouchers, balances)"


def upgrade(engine):
    """执行迁移"""
    with engine.connect() as conn:
        # 会计科目表
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS accounts (
                id SERIAL PRIMARY KEY,
                organization_id INTEGER NOT NULL REFERENCES organizations(id),
                code VARCHAR(50) NOT NULL,
                name VARCHAR(100) NOT NULL,
                full_name VARCHAR(500),
                account_type VARCHAR(20) NOT NULL,
                category VARCHAR(50),
                balance_direction VARCHAR(10) NOT NULL,
                level INTEGER DEFAULT 1,
                parent_id INTEGER REFERENCES accounts(id),
                is_leaf BOOLEAN DEFAULT TRUE,
                is_system BOOLEAN DEFAULT FALSE,
                is_active BOOLEAN DEFAULT TRUE,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(organization_id, code)
            )
        """))

        # 会计期间表
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS accounting_periods (
                id SERIAL PRIMARY KEY,
                organization_id INTEGER NOT NULL REFERENCES organizations(id),
                year INTEGER NOT NULL,
                month INTEGER NOT NULL,
                start_date DATE NOT NULL,
                end_date DATE NOT NULL,
                status VARCHAR(20) DEFAULT 'OPEN',
                closed_at TIMESTAMP,
                closed_by INTEGER REFERENCES users(id),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(organization_id, year, month)
            )
        """))

        # 凭证主表
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS vouchers (
                id SERIAL PRIMARY KEY,
                organization_id INTEGER NOT NULL REFERENCES organizations(id),
                voucher_type VARCHAR(10) DEFAULT '记',
                voucher_number INTEGER NOT NULL,
                voucher_date DATE NOT NULL,
                year INTEGER NOT NULL,
                month INTEGER NOT NULL,
                summary TEXT,
                status VARCHAR(20) DEFAULT 'DRAFT',
                transaction_id INTEGER,
                attachment_count INTEGER DEFAULT 0,
                created_by INTEGER REFERENCES users(id),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                reviewed_by INTEGER REFERENCES users(id),
                reviewed_at TIMESTAMP,
                posted_by INTEGER REFERENCES users(id),
                posted_at TIMESTAMP,
                UNIQUE(organization_id, year, month, voucher_type, voucher_number)
            )
        """))

        # 凭证分录表
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS voucher_items (
                id SERIAL PRIMARY KEY,
                voucher_id INTEGER NOT NULL REFERENCES vouchers(id) ON DELETE CASCADE,
                account_id INTEGER NOT NULL REFERENCES accounts(id),
                direction VARCHAR(10) NOT NULL,
                amount NUMERIC(18, 2) NOT NULL,
                summary TEXT,
                auxiliary_customer VARCHAR(100),
                auxiliary_supplier VARCHAR(100),
                auxiliary_project VARCHAR(100),
                auxiliary_department VARCHAR(100),
                seq INTEGER DEFAULT 0
            )
        """))

        # 科目余额表
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS account_balances (
                id SERIAL PRIMARY KEY,
                organization_id INTEGER NOT NULL REFERENCES organizations(id),
                account_id INTEGER NOT NULL REFERENCES accounts(id),
                year INTEGER NOT NULL,
                month INTEGER NOT NULL,
                opening_debit NUMERIC(18, 2) DEFAULT 0,
                opening_credit NUMERIC(18, 2) DEFAULT 0,
                period_debit NUMERIC(18, 2) DEFAULT 0,
                period_credit NUMERIC(18, 2) DEFAULT 0,
                ytd_debit NUMERIC(18, 2) DEFAULT 0,
                ytd_credit NUMERIC(18, 2) DEFAULT 0,
                closing_debit NUMERIC(18, 2) DEFAULT 0,
                closing_credit NUMERIC(18, 2) DEFAULT 0,
                UNIQUE(organization_id, account_id, year, month)
            )
        """))

        # 凭证模板表
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS voucher_templates (
                id SERIAL PRIMARY KEY,
                organization_id INTEGER NOT NULL REFERENCES organizations(id),
                name VARCHAR(100) NOT NULL,
                description TEXT,
                template_data JSONB NOT NULL,
                is_active BOOLEAN DEFAULT TRUE,
                created_by INTEGER REFERENCES users(id),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))

        # 创建索引
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_accounts_org ON accounts(organization_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_accounts_code ON accounts(organization_id, code)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_vouchers_org_date ON vouchers(organization_id, voucher_date)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_vouchers_status ON vouchers(organization_id, status)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_voucher_items_voucher ON voucher_items(voucher_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_account_balances_period ON account_balances(organization_id, year, month)"))

        conn.commit()


def downgrade(engine):
    """回滚迁移"""
    with engine.connect() as conn:
        conn.execute(text("DROP TABLE IF EXISTS voucher_templates CASCADE"))
        conn.execute(text("DROP TABLE IF EXISTS account_balances CASCADE"))
        conn.execute(text("DROP TABLE IF EXISTS voucher_items CASCADE"))
        conn.execute(text("DROP TABLE IF EXISTS vouchers CASCADE"))
        conn.execute(text("DROP TABLE IF EXISTS accounting_periods CASCADE"))
        conn.execute(text("DROP TABLE IF EXISTS accounts CASCADE"))
        conn.commit()
