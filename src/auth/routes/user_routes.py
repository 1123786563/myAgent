"""
用户管理路由
User Management Routes
"""

from fastapi import APIRouter, HTTPException, status, Depends, Query
from typing import Optional, List
from auth.schemas import (
    UserListItem,
    UserDetailResponse,
    UserCreateRequest,
    UserUpdateRequest,
    RoleResponse,
    PaginatedResponse,
    MessageResponse,
)
from auth.dependencies import require_permission, require_admin
from auth.middleware.auth_middleware import CurrentUser
from auth.services.password_service import get_password_service
from auth.services.audit_service import AuditService
from core.db_helper import DBHelper
from core.auth_models import User, Role, Organization
from infra.logger import get_logger

log = get_logger("UserRoutes")
router = APIRouter(prefix="/users", tags=["用户管理"])


@router.get("/", response_model=PaginatedResponse)
async def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: Optional[str] = None,
    role: Optional[str] = None,
    is_active: Optional[bool] = None,
    current_user: CurrentUser = Depends(require_permission("users:read"))
):
    """
    获取用户列表

    - 支持分页
    - 支持按邮箱/姓名搜索
    - 支持按角色筛选
    """
    db = DBHelper()
    with db.transaction() as session:
        query = session.query(User).filter(User.organization_id == current_user.organization_id)

        # 搜索
        if search:
            search_pattern = f"%{search}%"
            query = query.filter(
                (User.email.ilike(search_pattern)) |
                (User.full_name.ilike(search_pattern))
            )

        # 角色筛选
        if role:
            query = query.join(User.roles).filter(Role.name == role)

        # 状态筛选
        if is_active is not None:
            query = query.filter(User.is_active == is_active)

        # 总数
        total = query.count()

        # 分页
        offset = (page - 1) * page_size
        users = query.order_by(User.created_at.desc()).offset(offset).limit(page_size).all()

        items = []
        for user in users:
            items.append(UserListItem(
                uuid=user.uuid,
                email=user.email,
                full_name=user.full_name,
                roles=[r.name for r in user.roles],
                is_active=user.is_active,
                is_verified=user.is_verified,
                last_login_at=user.last_login_at,
                created_at=user.created_at
            ))

        return PaginatedResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            pages=(total + page_size - 1) // page_size
        )


@router.post("/", response_model=UserDetailResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    request_data: UserCreateRequest,
    current_user: CurrentUser = Depends(require_permission("users:create"))
):
    """
    创建新用户

    - 在当前组织内创建用户
    - 可指定初始角色
    """
    password_service = get_password_service()

    # 验证密码强度
    is_valid, error = password_service.validate_password_strength(request_data.password)
    if not is_valid:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error)

    db = DBHelper()
    with db.transaction() as session:
        # 检查邮箱是否已存在
        existing = session.query(User).filter_by(
            email=request_data.email,
            organization_id=current_user.organization_id
        ).first()
        if existing:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="该邮箱已被注册")

        # 创建用户
        user = User(
            email=request_data.email,
            password_hash=password_service.hash_password(request_data.password),
            full_name=request_data.full_name,
            phone=request_data.phone,
            organization_id=current_user.organization_id,
            is_active=True,
            is_verified=False
        )
        session.add(user)
        session.flush()

        # 分配角色
        if request_data.role_ids:
            roles = session.query(Role).filter(
                Role.id.in_(request_data.role_ids),
                (Role.organization_id == current_user.organization_id) | (Role.organization_id.is_(None))
            ).all()
            user.roles = roles

        # 审计日志
        AuditService.log_data_change(
            action="user.create",
            user_id=current_user.user_id,
            organization_id=current_user.organization_id,
            resource_type="User",
            resource_id=str(user.id),
            new_values={"email": user.email, "full_name": user.full_name}
        )

        return _build_user_detail(user)


@router.get("/{user_uuid}", response_model=UserDetailResponse)
async def get_user(
    user_uuid: str,
    current_user: CurrentUser = Depends(require_permission("users:read"))
):
    """
    获取用户详情
    """
    db = DBHelper()
    with db.transaction() as session:
        user = session.query(User).filter_by(uuid=user_uuid).first()

        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")

        # 检查组织隔离
        if user.organization_id != current_user.organization_id and not current_user.is_super_admin:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权访问其他组织的用户")

        return _build_user_detail(user)


@router.put("/{user_uuid}", response_model=UserDetailResponse)
async def update_user(
    user_uuid: str,
    request_data: UserUpdateRequest,
    current_user: CurrentUser = Depends(require_permission("users:update"))
):
    """
    更新用户信息
    """
    db = DBHelper()
    with db.transaction() as session:
        user = session.query(User).filter_by(uuid=user_uuid).first()

        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")

        # 检查组织隔离
        if user.organization_id != current_user.organization_id and not current_user.is_super_admin:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权修改其他组织的用户")

        old_values = {"full_name": user.full_name, "is_active": user.is_active}

        # 更新字段
        if request_data.full_name is not None:
            user.full_name = request_data.full_name
        if request_data.phone is not None:
            user.phone = request_data.phone
        if request_data.is_active is not None:
            user.is_active = request_data.is_active

        # 更新角色
        if request_data.role_ids is not None:
            roles = session.query(Role).filter(
                Role.id.in_(request_data.role_ids),
                (Role.organization_id == current_user.organization_id) | (Role.organization_id.is_(None))
            ).all()
            user.roles = roles

        # 审计日志
        AuditService.log_data_change(
            action="user.update",
            user_id=current_user.user_id,
            organization_id=current_user.organization_id,
            resource_type="User",
            resource_id=str(user.id),
            old_values=old_values,
            new_values={"full_name": user.full_name, "is_active": user.is_active}
        )

        return _build_user_detail(user)


@router.delete("/{user_uuid}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_uuid: str,
    current_user: CurrentUser = Depends(require_permission("users:delete"))
):
    """
    停用用户 (软删除)
    """
    db = DBHelper()
    with db.transaction() as session:
        user = session.query(User).filter_by(uuid=user_uuid).first()

        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")

        # 不能删除自己
        if user.id == current_user.user_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不能删除自己的账户")

        # 检查组织隔离
        if user.organization_id != current_user.organization_id and not current_user.is_super_admin:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权删除其他组织的用户")

        user.is_active = False

        # 审计日志
        AuditService.log_data_change(
            action="user.delete",
            user_id=current_user.user_id,
            organization_id=current_user.organization_id,
            resource_type="User",
            resource_id=str(user.id)
        )


@router.put("/{user_uuid}/roles", response_model=UserDetailResponse)
async def assign_roles(
    user_uuid: str,
    role_ids: List[int],
    current_user: CurrentUser = Depends(require_permission("roles:update"))
):
    """
    分配用户角色
    """
    db = DBHelper()
    with db.transaction() as session:
        user = session.query(User).filter_by(uuid=user_uuid).first()

        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")

        # 检查组织隔离
        if user.organization_id != current_user.organization_id and not current_user.is_super_admin:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权修改其他组织的用户")

        old_roles = [r.name for r in user.roles]

        # 获取角色
        roles = session.query(Role).filter(
            Role.id.in_(role_ids),
            (Role.organization_id == current_user.organization_id) | (Role.organization_id.is_(None))
        ).all()
        user.roles = roles

        # 审计日志
        AuditService.log_data_change(
            action="user.roles_assign",
            user_id=current_user.user_id,
            organization_id=current_user.organization_id,
            resource_type="User",
            resource_id=str(user.id),
            old_values={"roles": old_roles},
            new_values={"roles": [r.name for r in roles]}
        )

        return _build_user_detail(user)


def _build_user_detail(user: User) -> UserDetailResponse:
    """构建用户详情响应"""
    return UserDetailResponse(
        uuid=user.uuid,
        email=user.email,
        full_name=user.full_name,
        phone=user.phone,
        avatar_url=user.avatar_url,
        is_active=user.is_active,
        is_verified=user.is_verified,
        last_login_at=user.last_login_at,
        failed_login_attempts=user.failed_login_attempts,
        locked_until=user.locked_until,
        roles=[RoleResponse(
            id=r.id,
            name=r.name,
            display_name=r.display_name,
            description=r.description,
            is_system_role=r.is_system_role,
            priority=r.priority,
            permissions=[p.code for p in r.permissions]
        ) for r in user.roles],
        created_at=user.created_at,
        updated_at=user.updated_at
    )
