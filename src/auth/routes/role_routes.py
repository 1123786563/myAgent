"""
角色管理路由
Role Management Routes
"""

from fastapi import APIRouter, HTTPException, status, Depends
from typing import List
from auth.schemas import (
    RoleResponse,
    RoleCreateRequest,
    RoleUpdateRequest,
    PermissionResponse,
    MessageResponse,
)
from auth.dependencies import require_permission, require_admin
from auth.middleware.auth_middleware import CurrentUser
from auth.permissions import get_all_permissions
from auth.services.audit_service import AuditService
from core.db_helper import DBHelper
from core.auth_models import Role, Permission
from infra.logger import get_logger

log = get_logger("RoleRoutes")
router = APIRouter(prefix="/roles", tags=["角色管理"])


@router.get("/", response_model=List[RoleResponse])
async def list_roles(
    current_user: CurrentUser = Depends(require_permission("roles:read"))
):
    """
    获取角色列表

    - 返回当前组织的所有角色
    - 包含系统预置角色
    """
    db = DBHelper()
    with db.transaction() as session:
        roles = session.query(Role).filter(
            (Role.organization_id == current_user.organization_id) |
            (Role.organization_id.is_(None))
        ).order_by(Role.priority.desc()).all()

        return [RoleResponse(
            id=role.id,
            name=role.name,
            display_name=role.display_name,
            description=role.description,
            is_system_role=role.is_system_role,
            priority=role.priority,
            permissions=[p.code for p in role.permissions]
        ) for role in roles]


@router.post("/", response_model=RoleResponse, status_code=status.HTTP_201_CREATED)
async def create_role(
    request_data: RoleCreateRequest,
    current_user: CurrentUser = Depends(require_permission("roles:manage"))
):
    """
    创建自定义角色
    """
    db = DBHelper()
    with db.transaction() as session:
        # 检查名称是否已存在
        existing = session.query(Role).filter_by(
            name=request_data.name,
            organization_id=current_user.organization_id
        ).first()
        if existing:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="角色名称已存在")

        # 创建角色
        role = Role(
            name=request_data.name,
            display_name=request_data.display_name or request_data.name,
            description=request_data.description,
            organization_id=current_user.organization_id,
            is_system_role=False,
            priority=0
        )
        session.add(role)
        session.flush()

        # 添加权限
        if request_data.permission_codes:
            permissions = session.query(Permission).filter(
                Permission.code.in_(request_data.permission_codes)
            ).all()
            role.permissions = permissions

        # 审计日志
        AuditService.log_data_change(
            action="role.create",
            user_id=current_user.user_id,
            organization_id=current_user.organization_id,
            resource_type="Role",
            resource_id=str(role.id),
            new_values={"name": role.name, "permissions": request_data.permission_codes}
        )

        return RoleResponse(
            id=role.id,
            name=role.name,
            display_name=role.display_name,
            description=role.description,
            is_system_role=role.is_system_role,
            priority=role.priority,
            permissions=[p.code for p in role.permissions]
        )


@router.get("/{role_id}", response_model=RoleResponse)
async def get_role(
    role_id: int,
    current_user: CurrentUser = Depends(require_permission("roles:read"))
):
    """
    获取角色详情
    """
    db = DBHelper()
    with db.transaction() as session:
        role = session.query(Role).get(role_id)

        if not role:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="角色不存在")

        # 检查访问权限
        if role.organization_id and role.organization_id != current_user.organization_id:
            if not current_user.is_super_admin:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权访问其他组织的角色")

        return RoleResponse(
            id=role.id,
            name=role.name,
            display_name=role.display_name,
            description=role.description,
            is_system_role=role.is_system_role,
            priority=role.priority,
            permissions=[p.code for p in role.permissions]
        )


@router.put("/{role_id}", response_model=RoleResponse)
async def update_role(
    role_id: int,
    request_data: RoleUpdateRequest,
    current_user: CurrentUser = Depends(require_permission("roles:manage"))
):
    """
    更新角色信息
    """
    db = DBHelper()
    with db.transaction() as session:
        role = session.query(Role).get(role_id)

        if not role:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="角色不存在")

        # 系统角色不可修改名称
        if role.is_system_role:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="系统角色不可修改")

        # 检查组织隔离
        if role.organization_id and role.organization_id != current_user.organization_id:
            if not current_user.is_super_admin:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权修改其他组织的角色")

        old_values = {"display_name": role.display_name, "permissions": [p.code for p in role.permissions]}

        # 更新字段
        if request_data.display_name is not None:
            role.display_name = request_data.display_name
        if request_data.description is not None:
            role.description = request_data.description

        # 更新权限
        if request_data.permission_codes is not None:
            permissions = session.query(Permission).filter(
                Permission.code.in_(request_data.permission_codes)
            ).all()
            role.permissions = permissions

        # 审计日志
        AuditService.log_data_change(
            action="role.update",
            user_id=current_user.user_id,
            organization_id=current_user.organization_id,
            resource_type="Role",
            resource_id=str(role.id),
            old_values=old_values,
            new_values={"display_name": role.display_name, "permissions": request_data.permission_codes}
        )

        return RoleResponse(
            id=role.id,
            name=role.name,
            display_name=role.display_name,
            description=role.description,
            is_system_role=role.is_system_role,
            priority=role.priority,
            permissions=[p.code for p in role.permissions]
        )


@router.delete("/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_role(
    role_id: int,
    current_user: CurrentUser = Depends(require_permission("roles:manage"))
):
    """
    删除角色

    - 系统角色不可删除
    - 正在使用的角色不可删除
    """
    db = DBHelper()
    with db.transaction() as session:
        role = session.query(Role).get(role_id)

        if not role:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="角色不存在")

        if role.is_system_role:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="系统角色不可删除")

        # 检查组织隔离
        if role.organization_id and role.organization_id != current_user.organization_id:
            if not current_user.is_super_admin:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权删除其他组织的角色")

        # 检查是否有用户正在使用
        if role.users:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="该角色正在被使用，无法删除")

        session.delete(role)

        # 审计日志
        AuditService.log_data_change(
            action="role.delete",
            user_id=current_user.user_id,
            organization_id=current_user.organization_id,
            resource_type="Role",
            resource_id=str(role_id)
        )


@router.put("/{role_id}/permissions", response_model=RoleResponse)
async def update_role_permissions(
    role_id: int,
    permission_codes: List[str],
    current_user: CurrentUser = Depends(require_permission("roles:manage"))
):
    """
    更新角色权限
    """
    db = DBHelper()
    with db.transaction() as session:
        role = session.query(Role).get(role_id)

        if not role:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="角色不存在")

        # 检查组织隔离
        if role.organization_id and role.organization_id != current_user.organization_id:
            if not current_user.is_super_admin:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权修改其他组织的角色")

        old_perms = [p.code for p in role.permissions]

        # 更新权限
        permissions = session.query(Permission).filter(
            Permission.code.in_(permission_codes)
        ).all()
        role.permissions = permissions

        # 审计日志
        AuditService.log_data_change(
            action="role.permissions_update",
            user_id=current_user.user_id,
            organization_id=current_user.organization_id,
            resource_type="Role",
            resource_id=str(role.id),
            old_values={"permissions": old_perms},
            new_values={"permissions": permission_codes}
        )

        return RoleResponse(
            id=role.id,
            name=role.name,
            display_name=role.display_name,
            description=role.description,
            is_system_role=role.is_system_role,
            priority=role.priority,
            permissions=[p.code for p in role.permissions]
        )


@router.get("/permissions/all", response_model=List[PermissionResponse])
async def list_all_permissions(
    current_user: CurrentUser = Depends(require_permission("roles:read"))
):
    """
    获取所有可用权限
    """
    db = DBHelper()
    with db.transaction() as session:
        permissions = session.query(Permission).order_by(Permission.resource, Permission.action).all()

        if not permissions:
            # 如果数据库中没有权限，返回预定义的权限列表
            predefined = get_all_permissions()
            return [PermissionResponse(
                id=i,
                code=p["code"],
                resource=p["resource"],
                action=p["action"],
                description=p["description"]
            ) for i, p in enumerate(predefined, 1)]

        return [PermissionResponse(
            id=perm.id,
            code=perm.code,
            resource=perm.resource,
            action=perm.action,
            description=perm.description
        ) for perm in permissions]
