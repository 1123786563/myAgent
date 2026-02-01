"""
认证路由
Authentication Routes - Login, Register, Token management
"""

from fastapi import APIRouter, HTTPException, status, Request, Depends
from auth.schemas import (
    UserRegisterRequest,
    UserLoginRequest,
    TokenResponse,
    RefreshTokenRequest,
    PasswordChangeRequest,
    UserProfileResponse,
    UserProfileUpdate,
    MessageResponse,
)
from auth.services.auth_service import get_auth_service
from auth.middleware.auth_middleware import get_current_user, CurrentUser
from core.db_helper import DBHelper
from core.auth_models import User, Organization
from infra.logger import get_logger

log = get_logger("AuthRoutes")
router = APIRouter(prefix="/auth", tags=["认证"])


def _get_client_info(request: Request) -> tuple:
    """获取客户端信息"""
    ip = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    if not ip:
        ip = request.headers.get("x-real-ip", request.client.host if request.client else None)
    user_agent = request.headers.get("user-agent")
    return ip, user_agent


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(request_data: UserRegisterRequest, request: Request):
    """
    用户注册

    - 创建新用户账户
    - 如未指定组织，自动创建新组织
    - 第一个用户自动成为组织管理员
    """
    ip, user_agent = _get_client_info(request)
    auth_service = get_auth_service()

    user, error = auth_service.register(
        email=request_data.email,
        password=request_data.password,
        full_name=request_data.full_name,
        organization_name=request_data.organization_name,
        organization_slug=request_data.organization_slug,
        ip_address=ip,
        user_agent=user_agent
    )

    if error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error)

    # 注册成功后自动登录
    token_data, error = auth_service.login(
        email=request_data.email,
        password=request_data.password,
        ip_address=ip,
        user_agent=user_agent
    )

    if error:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="注册成功但登录失败")

    return token_data


@router.post("/login", response_model=TokenResponse)
async def login(request_data: UserLoginRequest, request: Request):
    """
    用户登录

    - 验证邮箱和密码
    - 返回 JWT 访问令牌和刷新令牌
    - 连续失败 5 次将锁定账户 30 分钟
    """
    ip, user_agent = _get_client_info(request)
    auth_service = get_auth_service()

    token_data, error = auth_service.login(
        email=request_data.email,
        password=request_data.password,
        ip_address=ip,
        user_agent=user_agent
    )

    if error:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=error)

    return token_data


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(request_data: RefreshTokenRequest, request: Request):
    """
    刷新访问令牌

    - 使用刷新令牌获取新的访问令牌
    - 实现令牌轮换，旧刷新令牌将失效
    """
    ip, user_agent = _get_client_info(request)
    auth_service = get_auth_service()

    token_data, error = auth_service.refresh_token(
        refresh_token=request_data.refresh_token,
        ip_address=ip,
        user_agent=user_agent
    )

    if error:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=error)

    return token_data


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request, current_user: CurrentUser = Depends(get_current_user)):
    """
    登出

    - 将当前访问令牌加入黑名单
    """
    ip, _ = _get_client_info(request)
    auth_service = get_auth_service()

    auth_service.logout(
        jti=current_user.jti,
        user_id=current_user.user_id,
        organization_id=current_user.organization_id,
        ip_address=ip
    )


@router.post("/logout-all", status_code=status.HTTP_204_NO_CONTENT)
async def logout_all_devices(request: Request, current_user: CurrentUser = Depends(get_current_user)):
    """
    登出所有设备

    - 撤销所有刷新令牌
    - 所有设备需重新登录
    """
    ip, _ = _get_client_info(request)
    auth_service = get_auth_service()

    auth_service.logout_all_devices(
        user_id=current_user.user_id,
        organization_id=current_user.organization_id,
        ip_address=ip
    )


@router.get("/me", response_model=UserProfileResponse)
async def get_current_user_profile(current_user: CurrentUser = Depends(get_current_user)):
    """
    获取当前用户信息
    """
    db = DBHelper()
    with db.transaction() as session:
        user = session.query(User).get(current_user.user_id)
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")

        org = session.query(Organization).get(user.organization_id)

        return UserProfileResponse(
            uuid=user.uuid,
            email=user.email,
            full_name=user.full_name,
            phone=user.phone,
            avatar_url=user.avatar_url,
            organization_id=user.organization_id,
            organization_name=org.name if org else "",
            roles=[role.name for role in user.roles],
            permissions=list(current_user.permissions),
            is_verified=user.is_verified,
            created_at=user.created_at
        )


@router.put("/me", response_model=UserProfileResponse)
async def update_profile(
    update_data: UserProfileUpdate,
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    更新当前用户资料
    """
    db = DBHelper()
    with db.transaction() as session:
        user = session.query(User).get(current_user.user_id)
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")

        if update_data.full_name is not None:
            user.full_name = update_data.full_name
        if update_data.phone is not None:
            user.phone = update_data.phone
        if update_data.avatar_url is not None:
            user.avatar_url = update_data.avatar_url

        org = session.query(Organization).get(user.organization_id)

        return UserProfileResponse(
            uuid=user.uuid,
            email=user.email,
            full_name=user.full_name,
            phone=user.phone,
            avatar_url=user.avatar_url,
            organization_id=user.organization_id,
            organization_name=org.name if org else "",
            roles=[role.name for role in user.roles],
            permissions=list(current_user.permissions),
            is_verified=user.is_verified,
            created_at=user.created_at
        )


@router.put("/me/password", response_model=MessageResponse)
async def change_password(
    request_data: PasswordChangeRequest,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    修改密码

    - 需要验证当前密码
    - 修改后所有设备需重新登录
    """
    ip, _ = _get_client_info(request)
    auth_service = get_auth_service()

    success, error = auth_service.change_password(
        user_id=current_user.user_id,
        old_password=request_data.old_password,
        new_password=request_data.new_password,
        ip_address=ip
    )

    if not success:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error)

    return MessageResponse(message="密码修改成功，请重新登录")
