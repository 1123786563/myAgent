"""
数据库迁移: 对账与工作流模块
Migration: Reconciliation and Workflow Tables
"""

from sqlalchemy import text

MIGRATION_ID = "005_reconciliation_and_workflow"
DESCRIPTION = "Create tables for Reconciliation Engine and Approval Workflow"


def upgrade(engine):
    """执行迁移"""
    with engine.connect() as conn:
        # ==========================================
        # 1. 对账模块 (Reconciliation)
        # ==========================================

        # 银行流水表
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS bank_statements (
                id SERIAL PRIMARY KEY,
                organization_id INTEGER REFERENCES organizations(id),
                source_type VARCHAR(50) NOT NULL,
                account_number VARCHAR(100),
                transaction_date TIMESTAMP NOT NULL,
                amount NUMERIC(18, 2) NOT NULL,
                currency VARCHAR(10) DEFAULT 'CNY',
                counterparty_name VARCHAR(200),
                counterparty_account VARCHAR(100),
                external_id VARCHAR(100) NOT NULL,
                reference_code VARCHAR(100),
                description TEXT,
                raw_data JSONB,
                status VARCHAR(20) DEFAULT 'UNRECONCILED',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_bank_stmt_org_source_ext ON bank_statements(organization_id, source_type, external_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_bank_stmt_status ON bank_statements(status)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_bank_stmt_date ON bank_statements(transaction_date)"))

        # 对账规则表
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS reconciliation_rules (
                id SERIAL PRIMARY KEY,
                organization_id INTEGER REFERENCES organizations(id),
                name VARCHAR(100) NOT NULL,
                priority INTEGER DEFAULT 0,
                conditions JSONB NOT NULL,
                auto_approve BOOLEAN DEFAULT FALSE,
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))

        # 对账日志表
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS reconciliation_logs (
                id SERIAL PRIMARY KEY,
                organization_id INTEGER REFERENCES organizations(id),
                statement_id INTEGER REFERENCES bank_statements(id),
                transaction_id INTEGER REFERENCES transactions(id),
                match_method VARCHAR(20) NOT NULL,
                score NUMERIC(5, 4),
                match_reason VARCHAR(500),
                is_confirmed BOOLEAN DEFAULT FALSE,
                confirmed_by INTEGER REFERENCES users(id),
                confirmed_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_recon_log_stmt ON reconciliation_logs(statement_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_recon_log_trans ON reconciliation_logs(transaction_id)"))

        # ==========================================
        # 2. 工作流模块 (Workflow)
        # ==========================================

        # 流程定义表
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS workflow_definitions (
                id SERIAL PRIMARY KEY,
                organization_id INTEGER REFERENCES organizations(id),
                name VARCHAR(100) NOT NULL,
                code VARCHAR(50) NOT NULL,
                description TEXT,
                version INTEGER DEFAULT 1,
                is_active BOOLEAN DEFAULT TRUE,
                config JSONB,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_wf_def_org_code ON workflow_definitions(organization_id, code)"))

        # 流程节点表
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS workflow_nodes (
                id SERIAL PRIMARY KEY,
                definition_id INTEGER REFERENCES workflow_definitions(id) ON DELETE CASCADE,
                name VARCHAR(50) NOT NULL,
                node_type VARCHAR(20) DEFAULT 'USER',
                approver_role_id INTEGER REFERENCES roles(id),
                approver_user_id INTEGER REFERENCES users(id),
                next_node_id INTEGER REFERENCES workflow_nodes(id),
                transition_rules JSONB
            )
        """))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_wf_node_def ON workflow_nodes(definition_id)"))

        # 流程实例表
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS workflow_instances (
                id SERIAL PRIMARY KEY,
                organization_id INTEGER REFERENCES organizations(id),
                definition_id INTEGER REFERENCES workflow_definitions(id),
                business_type VARCHAR(50) NOT NULL,
                business_id VARCHAR(50) NOT NULL,
                current_node_id INTEGER REFERENCES workflow_nodes(id),
                status VARCHAR(20) DEFAULT 'RUNNING',
                submitter_id INTEGER REFERENCES users(id),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_wf_inst_biz ON workflow_instances(organization_id, business_type, business_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_wf_inst_submitter ON workflow_instances(submitter_id)"))

        # 审批动作历史表
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS workflow_actions (
                id SERIAL PRIMARY KEY,
                instance_id INTEGER REFERENCES workflow_instances(id) ON DELETE CASCADE,
                node_id INTEGER REFERENCES workflow_nodes(id),
                operator_id INTEGER REFERENCES users(id),
                action_type VARCHAR(20) NOT NULL,
                comment TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))

        conn.commit()


def downgrade(engine):
    """回滚迁移"""
    with engine.connect() as conn:
        # Drop Workflow tables
        conn.execute(text("DROP TABLE IF EXISTS workflow_actions CASCADE"))
        conn.execute(text("DROP TABLE IF EXISTS workflow_instances CASCADE"))
        conn.execute(text("DROP TABLE IF EXISTS workflow_nodes CASCADE"))
        conn.execute(text("DROP TABLE IF EXISTS workflow_definitions CASCADE"))

        # Drop Reconciliation tables
        conn.execute(text("DROP TABLE IF EXISTS reconciliation_logs CASCADE"))
        conn.execute(text("DROP TABLE IF EXISTS reconciliation_rules CASCADE"))
        conn.execute(text("DROP TABLE IF EXISTS bank_statements CASCADE"))

        conn.commit()
