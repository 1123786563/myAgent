"""
数据库迁移: 添加多租户字段
Migration: Add tenant fields (organization_id) to core tables
"""

from sqlalchemy import text

MIGRATION_ID = "004_tenant_fields"
DESCRIPTION = "Add organization_id to core business tables for multi-tenancy"


def upgrade(engine):
    """执行迁移"""
    with engine.connect() as conn:
        # 1. Transactions 表
        # 先检查列是否存在以避免重复添加
        result = conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='transactions' AND column_name='organization_id'"))
        if not result.fetchone():
            conn.execute(text("ALTER TABLE transactions ADD COLUMN organization_id INTEGER"))
            conn.execute(text("CREATE INDEX idx_transactions_org_id ON transactions(organization_id)"))
            # 暂时不添加外键约束，以免影响现有数据，或者可以设置为 nullable
            # conn.execute(text("ALTER TABLE transactions ADD CONSTRAINT fk_transactions_org FOREIGN KEY (organization_id) REFERENCES organizations(id)"))

        # 2. PendingEntry 表
        result = conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='pending_entries' AND column_name='organization_id'"))
        if not result.fetchone():
            conn.execute(text("ALTER TABLE pending_entries ADD COLUMN organization_id INTEGER"))
            conn.execute(text("CREATE INDEX idx_pending_entries_org_id ON pending_entries(organization_id)"))

        # 3. TrialBalance 表
        # 注意：TrialBalance 的主键目前只有 account_code，需要改为 (organization_id, account_code)
        result = conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='trial_balance' AND column_name='organization_id'"))
        if not result.fetchone():
            conn.execute(text("ALTER TABLE trial_balance ADD COLUMN organization_id INTEGER"))
            # 由于主键变更比较复杂，这里先仅添加列和索引，逻辑主键由应用层保证或在后续专门的迁移中处理复合主键
            conn.execute(text("CREATE INDEX idx_trial_balance_org_id ON trial_balance(organization_id)"))

        # 4. System Events (可选，用于按租户过滤系统事件)
        result = conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='system_events' AND column_name='organization_id'"))
        if not result.fetchone():
            conn.execute(text("ALTER TABLE system_events ADD COLUMN organization_id INTEGER"))
            conn.execute(text("CREATE INDEX idx_system_events_org_id ON system_events(organization_id)"))

        # 5. SysConfig (可选，支持租户级配置)
        result = conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='sys_config' AND column_name='organization_id'"))
        if not result.fetchone():
            conn.execute(text("ALTER TABLE sys_config ADD COLUMN organization_id INTEGER"))
            conn.execute(text("CREATE INDEX idx_sys_config_org_id ON sys_config(organization_id)"))

        conn.commit()


def downgrade(engine):
    """回滚迁移"""
    with engine.connect() as conn:
        conn.execute(text("ALTER TABLE sys_config DROP COLUMN IF EXISTS organization_id"))
        conn.execute(text("ALTER TABLE system_events DROP COLUMN IF EXISTS organization_id"))
        conn.execute(text("ALTER TABLE trial_balance DROP COLUMN IF EXISTS organization_id"))
        conn.execute(text("ALTER TABLE pending_entries DROP COLUMN IF EXISTS organization_id"))
        conn.execute(text("ALTER TABLE transactions DROP COLUMN IF EXISTS organization_id"))
        conn.commit()
