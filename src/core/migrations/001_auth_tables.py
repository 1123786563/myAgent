"""
数据库迁移: 认证模块表
Migration: Authentication Tables
"""

from sqlalchemy import text

MIGRATION_ID = "001_auth_tables"
DESCRIPTION = "Create authentication and authorization tables"


def upgrade(engine):
    """执行迁移"""
    with engine.connect() as conn:
        # 组织表
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS organizations (
                id SERIAL PRIMARY KEY,
                name VARCHAR(200) NOT NULL,
                code VARCHAR(50) UNIQUE,
                tax_id VARCHAR(30),
                address TEXT,
                contact_phone VARCHAR(20),
                contact_email VARCHAR(100),
                is_active BOOLEAN DEFAULT TRUE,
                settings JSONB,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))

        # 用户表
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                uuid VARCHAR(36) UNIQUE NOT NULL,
                organization_id INTEGER REFERENCES organizations(id),
                email VARCHAR(255) UNIQUE NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                full_name VARCHAR(100),
                phone VARCHAR(20),
                avatar_url VARCHAR(500),
                is_active BOOLEAN DEFAULT TRUE,
                is_verified BOOLEAN DEFAULT FALSE,
                is_super_admin BOOLEAN DEFAULT FALSE,
                last_login_at TIMESTAMP,
                last_login_ip VARCHAR(45),
                failed_login_attempts INTEGER DEFAULT 0,
                locked_until TIMESTAMP,
                password_changed_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))

        # 角色表
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS roles (
                id SERIAL PRIMARY KEY,
                name VARCHAR(50) UNIQUE NOT NULL,
                display_name VARCHAR(100),
                description TEXT,
                is_system_role BOOLEAN DEFAULT FALSE,
                priority INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))

        # 权限表
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS permissions (
                id SERIAL PRIMARY KEY,
                code VARCHAR(100) UNIQUE NOT NULL,
                name VARCHAR(100),
                description TEXT,
                resource VARCHAR(50),
                action VARCHAR(50),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))

        # 角色-权限关联表
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS role_permissions (
                id SERIAL PRIMARY KEY,
                role_id INTEGER REFERENCES roles(id) ON DELETE CASCADE,
                permission_id INTEGER REFERENCES permissions(id) ON DELETE CASCADE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(role_id, permission_id)
            )
        """))

        # 用户-角色关联表
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS user_roles (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                role_id INTEGER REFERENCES roles(id) ON DELETE CASCADE,
                organization_id INTEGER REFERENCES organizations(id),
                assigned_by INTEGER REFERENCES users(id),
                assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, role_id, organization_id)
            )
        """))

        # 刷新令牌表
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS refresh_tokens (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                token_hash VARCHAR(255) UNIQUE NOT NULL,
                device_info VARCHAR(500),
                ip_address VARCHAR(45),
                expires_at TIMESTAMP NOT NULL,
                is_revoked BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))

        # 令牌黑名单
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS token_blacklist (
                id SERIAL PRIMARY KEY,
                jti VARCHAR(36) UNIQUE NOT NULL,
                token_type VARCHAR(20),
                user_id INTEGER,
                expires_at TIMESTAMP NOT NULL,
                blacklisted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))

        # 审计日志表
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS audit_logs (
                id SERIAL PRIMARY KEY,
                user_id INTEGER,
                organization_id INTEGER,
                action VARCHAR(100) NOT NULL,
                resource_type VARCHAR(50),
                resource_id VARCHAR(100),
                old_values JSONB,
                new_values JSONB,
                ip_address VARCHAR(45),
                user_agent TEXT,
                trace_id VARCHAR(36),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))

        # 创建索引
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_users_org ON users(organization_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_audit_logs_user ON audit_logs(user_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_audit_logs_org ON audit_logs(organization_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_audit_logs_action ON audit_logs(action)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_refresh_tokens_user ON refresh_tokens(user_id)"))

        conn.commit()


def downgrade(engine):
    """回滚迁移"""
    with engine.connect() as conn:
        conn.execute(text("DROP TABLE IF EXISTS audit_logs CASCADE"))
        conn.execute(text("DROP TABLE IF EXISTS token_blacklist CASCADE"))
        conn.execute(text("DROP TABLE IF EXISTS refresh_tokens CASCADE"))
        conn.execute(text("DROP TABLE IF EXISTS user_roles CASCADE"))
        conn.execute(text("DROP TABLE IF EXISTS role_permissions CASCADE"))
        conn.execute(text("DROP TABLE IF EXISTS permissions CASCADE"))
        conn.execute(text("DROP TABLE IF EXISTS roles CASCADE"))
        conn.execute(text("DROP TABLE IF EXISTS users CASCADE"))
        conn.execute(text("DROP TABLE IF EXISTS organizations CASCADE"))
        conn.commit()
