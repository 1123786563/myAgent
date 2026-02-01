"""
权限依赖
Permission Dependencies for FastAPI routes
"""

from fastapi import Depends, HTTPException, status, Request
from typing import List
from auth.middleware.auth_middleware import get_current_user, CurrentUser
from infra.logger import get_logger

log = get_logger("AuthDependencies")


def require_permission(permission: str):
    """
    单权限检查依赖工厂

    Usage:
        @router.get("/transactions")
        async def list_transactions(
            user: CurrentUser = Depends(require_permission("transactions:read"))
        ):
            ...
    """
    async def dependency(
        request: Request,
        current_user: CurrentUser = Depends(get_current_user)
    ) -> CurrentUser:
        if not current_user.has_permission(permission):
            log.warning(
                f"Permission denied: user={current_user.user_id}, "
                f"required={permission}, has={current_user.permissions}"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"权限不足: 需要 {permission}"
            )
        return current_user

    return dependency


def require_any_permission(permissions: List[str]):
    """
    任一权限检查依赖: 用户拥有列表中任一权限即可通过

    Usage:
        @router.get("/data")
        async def get_data(
            user: CurrentUser = Depends(require_any_permission(["data:read", "data:manage"]))
        ):
            ...
    """
    async def dependency(
        request: Request,
        current_user: CurrentUser = Depends(get_current_user)
    ) -> CurrentUser:
        if not current_user.has_any_permission(permissions):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"权限不足: 需要以下权限之一 {permissions}"
            )
        return current_user

    return dependency


def require_all_permissions(permissions: List[str]):
    """
    全部权限检查依赖: 用户必须拥有列表中所有权限

    Usage:
        @router.delete("/critical")
        async def delete_critical(
            user: CurrentUser = Depends(require_all_permissions(["data:delete", "audit:approve"]))
        ):
            ...
    """
    async def dependency(
        request: Request,
        current_user: CurrentUser = Depends(get_current_user)
    ) -> CurrentUser:
        if not current_user.has_all_permissions(permissions):
            missing = [p for p in permissions if not current_user.has_permission(p)]
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"权限不足: 缺少 {missing}"
            )
        return current_user

    return dependency


def require_role(role: str):
    """
    角色检查依赖

    Usage:
        @router.get("/admin")
        async def admin_only(user: CurrentUser = Depends(require_role("ADMIN"))):
            ...
    """
    async def dependency(
        current_user: CurrentUser = Depends(get_current_user)
    ) -> CurrentUser:
        if not current_user.has_role(role):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"需要角色: {role}"
            )
        return current_user

    return dependency


def require_super_admin():
    """
    超级管理员检查依赖

    Usage:
        @router.post("/system/config")
        async def update_system_config(user: CurrentUser = Depends(require_super_admin())):
            ...
    """
    async def dependency(
        current_user: CurrentUser = Depends(get_current_user)
    ) -> CurrentUser:
        if not current_user.is_super_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="需要超级管理员权限"
            )
        return current_user

    return dependency


def require_admin():
    """
    管理员检查依赖 (包括 SUPER_ADMIN 和 ADMIN)

    Usage:
        @router.get("/users")
        async def list_users(user: CurrentUser = Depends(require_admin())):
            ...
    """
    async def dependency(
        current_user: CurrentUser = Depends(get_current_user)
    ) -> CurrentUser:
        if not current_user.is_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="需要管理员权限"
            )
        return current_user

    return dependency


def require_same_organization(target_org_id: int = None):
    """
    组织隔离检查: 确保操作在同一组织内
    超级管理员可跨组织访问

    Usage:
        @router.get("/users/{user_id}")
        async def get_user(
            user_id: int,
            org_id: int,  # 从路径或查询获取
            current_user: CurrentUser = Depends(require_same_organization())
        ):
            ...
    """
    async def dependency(
        request: Request,
        current_user: CurrentUser = Depends(get_current_user)
    ) -> CurrentUser:
        # 超级管理员可跨组织
        if current_user.is_super_admin:
            return current_user

        # 从请求中获取目标组织 ID
        org_id = target_org_id
        if org_id is None:
            org_id = request.path_params.get("organization_id")
            if org_id is None:
                org_id = request.query_params.get("organization_id")

        if org_id is not None and int(org_id) != current_user.organization_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="无法访问其他组织的资源"
            )

        return current_user

    return dependency
