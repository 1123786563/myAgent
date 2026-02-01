"""
角色与权限定义
Role and Permission Definitions
"""

from enum import Enum
from typing import Dict, List, Set


class RoleType(str, Enum):
    """系统预置角色类型"""
    SUPER_ADMIN = "SUPER_ADMIN"  # 平台超级管理员
    ADMIN = "ADMIN"              # 组织管理员
    AUDITOR = "AUDITOR"          # 审计员
    ACCOUNTANT = "ACCOUNTANT"    # 会计
    VIEWER = "VIEWER"            # 只读用户


class Resource(str, Enum):
    """资源类型"""
    USERS = "users"
    ROLES = "roles"
    ORGANIZATIONS = "organizations"
    TRANSACTIONS = "transactions"
    REPORTS = "reports"
    KNOWLEDGE_BASE = "knowledge_base"
    SYSTEM_CONFIG = "system_config"
    AUDIT_LOGS = "audit_logs"


class Action(str, Enum):
    """操作类型"""
    CREATE = "create"
    READ = "read"
    UPDATE = "update"
    DELETE = "delete"
    APPROVE = "approve"
    EXPORT = "export"
    MANAGE = "manage"  # 完全控制


# 权限编码格式: "{resource}:{action}"
DEFAULT_ROLE_PERMISSIONS: Dict[RoleType, List[str]] = {
    RoleType.SUPER_ADMIN: [
        # 全部权限
        "users:manage", "roles:manage", "organizations:manage",
        "transactions:manage", "reports:manage", "knowledge_base:manage",
        "system_config:manage", "audit_logs:read"
    ],
    RoleType.ADMIN: [
        # 组织级管理员
        "users:create", "users:read", "users:update", "users:delete",
        "roles:read", "roles:update",
        "transactions:manage", "reports:manage",
        "knowledge_base:manage", "audit_logs:read"
    ],
    RoleType.AUDITOR: [
        # 审计与审批
        "users:read",
        "transactions:read", "transactions:approve",
        "reports:read", "reports:export",
        "knowledge_base:read",
        "audit_logs:read"
    ],
    RoleType.ACCOUNTANT: [
        # 交易处理
        "transactions:create", "transactions:read", "transactions:update",
        "reports:read",
        "knowledge_base:read", "knowledge_base:update"
    ],
    RoleType.VIEWER: [
        # 只读
        "transactions:read",
        "reports:read",
        "knowledge_base:read"
    ]
}


# 角色优先级 (数值越大权限越高)
ROLE_PRIORITY: Dict[RoleType, int] = {
    RoleType.SUPER_ADMIN: 100,
    RoleType.ADMIN: 80,
    RoleType.AUDITOR: 60,
    RoleType.ACCOUNTANT: 40,
    RoleType.VIEWER: 20,
}


# 与 PrivacyGuard 角色的映射关系
PRIVACY_GUARD_ROLE_MAPPING: Dict[RoleType, str] = {
    RoleType.SUPER_ADMIN: "ADMIN",
    RoleType.ADMIN: "ADMIN",
    RoleType.AUDITOR: "AUDITOR",
    RoleType.ACCOUNTANT: "ACCOUNTANT",
    RoleType.VIEWER: "GUEST"
}


def has_permission(user_permissions: Set[str], required: str) -> bool:
    """
    检查用户是否拥有指定权限

    Args:
        user_permissions: 用户拥有的权限集合
        required: 需要的权限 (如 "transactions:read")

    Returns:
        bool: 是否拥有权限
    """
    if not required:
        return True

    # 精确匹配
    if required in user_permissions:
        return True

    # 检查 manage 权限 (包含所有操作)
    resource = required.split(":")[0]
    if f"{resource}:manage" in user_permissions:
        return True

    return False


def get_all_permissions() -> List[Dict[str, str]]:
    """获取所有预定义权限"""
    permissions = []
    for resource in Resource:
        for action in Action:
            code = f"{resource.value}:{action.value}"
            permissions.append({
                "code": code,
                "resource": resource.value,
                "action": action.value,
                "description": f"{action.value.capitalize()} {resource.value}"
            })
    return permissions


def get_highest_role(roles: List[str]) -> str:
    """从角色列表中获取最高优先级的角色"""
    if not roles:
        return RoleType.VIEWER.value

    highest = RoleType.VIEWER
    highest_priority = 0

    for role_name in roles:
        try:
            role = RoleType(role_name)
            if ROLE_PRIORITY.get(role, 0) > highest_priority:
                highest = role
                highest_priority = ROLE_PRIORITY[role]
        except ValueError:
            continue

    return highest.value
