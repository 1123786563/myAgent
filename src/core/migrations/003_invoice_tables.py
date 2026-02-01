"""
数据库迁移: 发票模块表
Migration: Invoice Tables
"""

from sqlalchemy import text

MIGRATION_ID = "003_invoice_tables"
DESCRIPTION = "Create invoice management tables"


def upgrade(engine):
    """执行迁移"""
    with engine.connect() as conn:
        # 发票主表
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS invoices (
                id SERIAL PRIMARY KEY,
                organization_id INTEGER NOT NULL REFERENCES organizations(id),
                invoice_code VARCHAR(20) NOT NULL,
                invoice_number VARCHAR(20) NOT NULL,
                invoice_type VARCHAR(30) NOT NULL,
                direction VARCHAR(10) NOT NULL,
                status VARCHAR(20) DEFAULT 'DRAFT',
                invoice_date DATE NOT NULL,
                check_code VARCHAR(50),
                amount_without_tax NUMERIC(18, 2) NOT NULL,
                tax_amount NUMERIC(18, 2) NOT NULL,
                total_amount NUMERIC(18, 2) NOT NULL,
                tax_rate VARCHAR(10),
                buyer_name VARCHAR(200) NOT NULL,
                buyer_tax_id VARCHAR(30),
                buyer_address_phone VARCHAR(200),
                buyer_bank_account VARCHAR(200),
                seller_name VARCHAR(200) NOT NULL,
                seller_tax_id VARCHAR(30),
                seller_address_phone VARCHAR(200),
                seller_bank_account VARCHAR(200),
                remark TEXT,
                machine_code VARCHAR(20),
                verification_result TEXT,
                verified_at TIMESTAMP,
                verified_by INTEGER REFERENCES users(id),
                transaction_id INTEGER,
                voucher_id INTEGER,
                attachment_url VARCHAR(500),
                ocr_raw_data TEXT,
                created_by INTEGER REFERENCES users(id),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(organization_id, invoice_code, invoice_number)
            )
        """))

        # 发票明细行
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS invoice_items (
                id SERIAL PRIMARY KEY,
                invoice_id INTEGER NOT NULL REFERENCES invoices(id) ON DELETE CASCADE,
                seq INTEGER NOT NULL,
                goods_name VARCHAR(200) NOT NULL,
                specification VARCHAR(100),
                unit VARCHAR(20),
                quantity NUMERIC(18, 6),
                unit_price NUMERIC(18, 6),
                amount NUMERIC(18, 2) NOT NULL,
                tax_rate VARCHAR(10),
                tax_amount NUMERIC(18, 2),
                goods_code VARCHAR(30),
                tax_category_code VARCHAR(30)
            )
        """))

        # 发票验证日志
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS invoice_verification_logs (
                id SERIAL PRIMARY KEY,
                invoice_id INTEGER NOT NULL REFERENCES invoices(id),
                organization_id INTEGER NOT NULL REFERENCES organizations(id),
                request_data TEXT,
                response_data TEXT,
                is_valid BOOLEAN,
                error_code VARCHAR(50),
                error_message VARCHAR(500),
                verification_source VARCHAR(50),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_by INTEGER REFERENCES users(id)
            )
        """))

        # 税务申报记录
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS tax_declarations (
                id SERIAL PRIMARY KEY,
                organization_id INTEGER NOT NULL REFERENCES organizations(id),
                tax_period VARCHAR(10) NOT NULL,
                declaration_type VARCHAR(50) NOT NULL,
                input_tax_amount NUMERIC(18, 2) DEFAULT 0,
                input_invoice_count INTEGER DEFAULT 0,
                output_tax_amount NUMERIC(18, 2) DEFAULT 0,
                output_invoice_count INTEGER DEFAULT 0,
                tax_payable NUMERIC(18, 2) DEFAULT 0,
                tax_credit NUMERIC(18, 2) DEFAULT 0,
                status VARCHAR(20) DEFAULT 'DRAFT',
                submitted_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(organization_id, tax_period, declaration_type)
            )
        """))

        # 创建索引
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_invoices_org_date ON invoices(organization_id, invoice_date)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_invoices_status ON invoices(organization_id, status)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_invoices_direction ON invoices(organization_id, direction)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_invoice_items_invoice ON invoice_items(invoice_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_verification_log_invoice ON invoice_verification_logs(invoice_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_tax_declaration_period ON tax_declarations(organization_id, tax_period)"))

        conn.commit()


def downgrade(engine):
    """回滚迁移"""
    with engine.connect() as conn:
        conn.execute(text("DROP TABLE IF EXISTS tax_declarations CASCADE"))
        conn.execute(text("DROP TABLE IF EXISTS invoice_verification_logs CASCADE"))
        conn.execute(text("DROP TABLE IF EXISTS invoice_items CASCADE"))
        conn.execute(text("DROP TABLE IF EXISTS invoices CASCADE"))
        conn.commit()
