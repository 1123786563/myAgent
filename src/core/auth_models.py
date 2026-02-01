"""
认证与权限系统数据库模型
Authentication and Permission System Database Models
"""

from sqlalchemy import (
    Column, Integer, String, DateTime, Boolean, ForeignKey,
    Table, Text, Index, JSON
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from core.db_models import Base
import uuid as uuid_lib


# ============== 关联表 (Many-to-Many) ==============

# 角色-权限关联表
role_permissions = Table(
    'role_permissions',
    Base.metadata,
    Column('role_id', Integer, ForeignKey('roles.id', ondelete='CASCADE'), primary_key=True),
    Column('permission_id', Integer, ForeignKey('permissions.id', ondelete='CASCADE'), primary_key=True)
)

# 用户-角色关联表
user_roles = Table(
    'user_roles',
    Base.metadata,
    Column('user_id', Integer, ForeignKey('users.id', ondelete='CASCADE'), primary_key=True),
    Column('role_id', Integer, ForeignKey('roles.id', ondelete='CASCADE'), primary_key=True)
)


# ============== 组织/租户 ==============

class Organization(Base):
    """组织/租户模型 - 多租户隔离"""
    __tablename__ = 'organizations'

    id = Column(Integer, primary_key=True, autoincrement=True)
    uuid = Column(String(36), unique=True, nullable=False, default=lambda: str(uuid_lib.uuid4()))
    name = Column(String(255), nullable=False)
    slug = Column(String(100), unique=True, nullable=False)  # URL友好标识
    is_active = Column(Boolean, default=True)
    settings = Column(JSON, default={})  # 组织特定配置
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # 关系
    users = relationship("User", back_populates="organization", cascade="all, delete-orphan")

    __table_args__ = (
        Index('ix_organizations_slug', 'slug'),
        Index('ix_organizations_uuid', 'uuid'),
    )


# ============== 用户 ==============

class User(Base):
    """用户账户模型"""
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True, autoincrement=True)
    uuid = Column(String(36), unique=True, nullable=False, default=lambda: str(uuid_lib.uuid4()))
    organization_id = Column(Integer, ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False)

    # 认证字段
    email = Column(String(255), nullable=False)
    password_hash = Column(String(255), nullable=False)

    # 个人信息
    full_name = Column(String(255))
    phone = Column(String(20))
    avatar_url = Column(String(500))

    # 状态字段
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)
    last_login_at = Column(DateTime)
    failed_login_attempts = Column(Integer, default=0)
    locked_until = Column(DateTime)

    # 时间戳
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # 关系
    organization = relationship("Organization", back_populates="users")
    roles = relationship("Role", secondary=user_roles, back_populates="users")
    refresh_tokens = relationship("RefreshToken", back_populates="user", cascade="all, delete-orphan")
    audit_logs = relationship("AuditLog", back_populates="user")

    __table_args__ = (
        Index('ix_users_email_org', 'email', 'organization_id', unique=True),
        Index('ix_users_uuid', 'uuid'),
        Index('ix_users_org_id', 'organization_id'),
    )

    @property
    def is_locked(self) -> bool:
        """检查账户是否被锁定"""
        if self.locked_until is None:
            return False
        from datetime import datetime
        return datetime.utcnow() < self.locked_until


# ============== 角色 ==============

class Role(Base):
    """RBAC 角色模型"""
    __tablename__ = 'roles'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(50), nullable=False)  # SUPER_ADMIN, ADMIN, AUDITOR, ACCOUNTANT, VIEWER
    display_name = Column(String(100))
    description = Column(Text)
    organization_id = Column(Integer, ForeignKey('organizations.id', ondelete='CASCADE'), nullable=True)
    is_system_role = Column(Boolean, default=False)  # 系统角色不可删除
    priority = Column(Integer, default=0)  # 数值越大权限越高
    created_at = Column(DateTime, server_default=func.now())

    # 关系
    permissions = relationship("Permission", secondary=role_permissions, back_populates="roles")
    users = relationship("User", secondary=user_roles, back_populates="roles")

    __table_args__ = (
        Index('ix_roles_name_org', 'name', 'organization_id', unique=True),
    )


# ============== 权限 ==============

class Permission(Base):
    """细粒度权限模型"""
    __tablename__ = 'permissions'

    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(100), unique=True, nullable=False)  # 如: "transactions:read", "users:manage"
    resource = Column(String(50), nullable=False)  # 如: "transactions", "users", "reports"
    action = Column(String(50), nullable=False)  # 如: "read", "write", "delete", "manage"
    description = Column(Text)
    created_at = Column(DateTime, server_default=func.now())

    # 关系
    roles = relationship("Role", secondary=role_permissions, back_populates="permissions")

    __table_args__ = (
        Index('ix_permissions_resource_action', 'resource', 'action'),
        Index('ix_permissions_code', 'code'),
    )


# ============== 刷新令牌 ==============

class RefreshToken(Base):
    """刷新令牌存储 - 用于 JWT 轮换"""
    __tablename__ = 'refresh_tokens'

    id = Column(Integer, primary_key=True, autoincrement=True)
    token_hash = Column(String(64), unique=True, nullable=False)  # SHA-256 哈希
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    device_info = Column(String(255))  # User-Agent 或设备标识
    ip_address = Column(String(45))  # IPv4 或 IPv6
    expires_at = Column(DateTime, nullable=False)
    revoked_at = Column(DateTime)  # NULL 表示有效
    created_at = Column(DateTime, server_default=func.now())

    # 关系
    user = relationship("User", back_populates="refresh_tokens")

    __table_args__ = (
        Index('ix_refresh_tokens_user_id', 'user_id'),
        Index('ix_refresh_tokens_expires', 'expires_at'),
        Index('ix_refresh_tokens_hash', 'token_hash'),
    )

    @property
    def is_valid(self) -> bool:
        """检查令牌是否有效"""
        from datetime import datetime
        if self.revoked_at is not None:
            return False
        return datetime.utcnow() < self.expires_at


# ============== 令牌黑名单 ==============

class TokenBlacklist(Base):
    """令牌黑名单 - 用于登出"""
    __tablename__ = 'token_blacklist'

    id = Column(Integer, primary_key=True, autoincrement=True)
    jti = Column(String(36), unique=True, nullable=False)  # JWT ID
    expires_at = Column(DateTime, nullable=False)  # 用于清理过期记录
    blacklisted_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        Index('ix_token_blacklist_jti', 'jti'),
        Index('ix_token_blacklist_expires', 'expires_at'),
    )


# ============== 审计日志 ==============

class AuditLog(Base):
    """审计日志 - 完整的操作追踪"""
    __tablename__ = 'audit_logs'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    organization_id = Column(Integer, ForeignKey('organizations.id', ondelete='SET NULL'), nullable=True)

    # 操作详情
    action = Column(String(100), nullable=False)  # 如: "user.login", "transaction.approve"
    resource_type = Column(String(50))  # 如: "User", "Transaction"
    resource_id = Column(String(100))  # 受影响资源的 ID

    # 请求上下文
    ip_address = Column(String(45))
    user_agent = Column(String(500))
    trace_id = Column(String(36))

    # 变更追踪
    old_values = Column(JSON)  # 更新前的状态
    new_values = Column(JSON)  # 更新后的状态

    # 结果
    status = Column(String(20), default='SUCCESS')  # SUCCESS, FAILURE, DENIED
    error_message = Column(Text)

    created_at = Column(DateTime, server_default=func.now())

    # 关系
    user = relationship("User", back_populates="audit_logs")

    __table_args__ = (
        Index('ix_audit_logs_user_id', 'user_id'),
        Index('ix_audit_logs_org_id', 'organization_id'),
        Index('ix_audit_logs_action', 'action'),
        Index('ix_audit_logs_created', 'created_at'),
        Index('ix_audit_logs_trace', 'trace_id'),
        Index('ix_audit_logs_resource', 'resource_type', 'resource_id'),
    )
