"""
认证中间件
Authentication Middleware - JWT extraction and user context
"""

from fastapi import Request, HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional, Set, List
from core.db_helper import DBHelper
from auth.services.jwt_service import get_jwt_service
from auth.permissions import PRIVACY_GUARD_ROLE_MAPPING, RoleType
from infra.logger import get_logger

log = get_logger("AuthMiddleware")
security = HTTPBearer(auto_error=False)


class CurrentUser:
    """当前认证用户上下文对象"""

    def __init__(
        self,
        user_id: int,
        user_uuid: str,
        organization_id: int,
        email: str,
        roles: List[str],
        permissions: Set[str],
        jti: str
    ):
        self.user_id = user_id
        self.user_uuid = user_uuid
        self.organization_id = organization_id
        self.email = email
        self.roles = roles
        self.permissions = permissions
        self.jti = jti  # 用于登出时加入黑名单

    def has_permission(self, permission: str) -> bool:
        """检查用户是否拥有指定权限"""
        if permission in self.permissions:
            return True
        # 检查 manage 权限 (包含该资源的所有操作)
        resource = permission.split(":")[0]
        return f"{resource}:manage" in self.permissions

    def has_any_permission(self, permissions: List[str]) -> bool:
        """检查用户是否拥有任一权限"""
        return any(self.has_permission(p) for p in permissions)

    def has_all_permissions(self, permissions: List[str]) -> bool:
        """检查用户是否拥有所有权限"""
        return all(self.has_permission(p) for p in permissions)

    def has_role(self, role: str) -> bool:
        """检查用户是否拥有指定角色"""
        return role in self.roles

    @property
    def is_super_admin(self) -> bool:
        """是否为超级管理员"""
        return "SUPER_ADMIN" in self.roles

    @property
    def is_admin(self) -> bool:
        """是否为管理员 (包括超级管理员)"""
        return "SUPER_ADMIN" in self.roles or "ADMIN" in self.roles

    @property
    def privacy_guard_role(self) -> str:
        """获取 PrivacyGuard 兼容的角色"""
        for role in self.roles:
            try:
                role_type = RoleType(role)
                if role_type in PRIVACY_GUARD_ROLE_MAPPING:
                    return PRIVACY_GUARD_ROLE_MAPPING[role_type]
            except ValueError:
                continue
        return "GUEST"


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> CurrentUser:
    """
    FastAPI 依赖: 从 JWT 提取并验证当前用户

    Raises:
        HTTPException: 401 未认证或令牌无效
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未提供认证凭据",
            headers={"WWW-Authenticate": "Bearer"}
        )

    token = credentials.credentials
    jwt_service = get_jwt_service()
    payload = jwt_service.decode_token(token, expected_type="access")

    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效或过期的令牌",
            headers={"WWW-Authenticate": "Bearer"}
        )

    # 检查令牌是否在黑名单中
    jti = payload.get("jti")
    db = DBHelper()

    from core.auth_models import TokenBlacklist, User

    with db.transaction() as session:
        blacklisted = session.query(TokenBlacklist).filter_by(jti=jti).first()
        if blacklisted:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="令牌已被撤销"
            )

        # 验证用户仍然存在且处于活动状态
        user = session.query(User).filter_by(id=payload["user_id"]).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="用户不存在"
            )
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="用户账户已被禁用"
            )
        if user.is_locked:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="用户账户已被锁定"
            )

        email = user.email

    return CurrentUser(
        user_id=payload["user_id"],
        user_uuid=payload["sub"],
        organization_id=payload["org_id"],
        email=email,
        roles=payload.get("roles", []),
        permissions=set(payload.get("permissions", [])),
        jti=jti
    )


async def get_current_user_optional(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> Optional[CurrentUser]:
    """
    可选认证依赖: 未认证时返回 None 而非抛出异常
    用于同时支持认证和匿名访问的端点
    """
    if not credentials:
        return None
    try:
        return await get_current_user(request, credentials)
    except HTTPException:
        return None
