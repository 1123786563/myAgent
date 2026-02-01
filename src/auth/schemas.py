"""
Pydantic 请求/响应模型
Request/Response Schemas for Auth API
"""

from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import Optional, List, Dict, Any
from datetime import datetime


# ============== 认证相关 ==============

class UserRegisterRequest(BaseModel):
    """用户注册请求"""
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    full_name: str = Field(..., min_length=1, max_length=255)
    organization_name: Optional[str] = Field(None, max_length=255)
    organization_slug: Optional[str] = Field(None, max_length=100)


class UserLoginRequest(BaseModel):
    """用户登录请求"""
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    """令牌响应"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # 秒
    user: "UserProfileResponse"


class RefreshTokenRequest(BaseModel):
    """刷新令牌请求"""
    refresh_token: str


class PasswordChangeRequest(BaseModel):
    """修改密码请求"""
    old_password: str
    new_password: str = Field(..., min_length=8, max_length=128)


class PasswordResetRequest(BaseModel):
    """密码重置请求"""
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    """密码重置确认"""
    token: str
    new_password: str = Field(..., min_length=8, max_length=128)


# ============== 用户相关 ==============

class UserProfileResponse(BaseModel):
    """用户资料响应"""
    uuid: str
    email: str
    full_name: Optional[str] = None
    phone: Optional[str] = None
    avatar_url: Optional[str] = None
    organization_id: int
    organization_name: str
    roles: List[str]
    permissions: List[str]
    is_verified: bool
    created_at: datetime

    class Config:
        from_attributes = True


class UserProfileUpdate(BaseModel):
    """用户资料更新"""
    full_name: Optional[str] = Field(None, max_length=255)
    phone: Optional[str] = Field(None, max_length=20)
    avatar_url: Optional[str] = Field(None, max_length=500)


class UserListItem(BaseModel):
    """用户列表项"""
    uuid: str
    email: str
    full_name: Optional[str] = None
    roles: List[str]
    is_active: bool
    is_verified: bool
    last_login_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True


class UserCreateRequest(BaseModel):
    """创建用户请求 (管理员)"""
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    full_name: str = Field(..., min_length=1, max_length=255)
    phone: Optional[str] = Field(None, max_length=20)
    role_ids: List[int] = []


class UserUpdateRequest(BaseModel):
    """更新用户请求 (管理员)"""
    full_name: Optional[str] = Field(None, max_length=255)
    phone: Optional[str] = Field(None, max_length=20)
    is_active: Optional[bool] = None
    role_ids: Optional[List[int]] = None


class UserDetailResponse(BaseModel):
    """用户详情响应"""
    uuid: str
    email: str
    full_name: Optional[str] = None
    phone: Optional[str] = None
    avatar_url: Optional[str] = None
    is_active: bool
    is_verified: bool
    last_login_at: Optional[datetime] = None
    failed_login_attempts: int
    locked_until: Optional[datetime] = None
    roles: List["RoleResponse"]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ============== 角色相关 ==============

class RoleResponse(BaseModel):
    """角色响应"""
    id: int
    name: str
    display_name: Optional[str] = None
    description: Optional[str] = None
    is_system_role: bool
    priority: int
    permissions: List[str]

    class Config:
        from_attributes = True


class RoleCreateRequest(BaseModel):
    """创建角色请求"""
    name: str = Field(..., min_length=1, max_length=50)
    display_name: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = None
    permission_codes: List[str] = []


class RoleUpdateRequest(BaseModel):
    """更新角色请求"""
    display_name: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = None
    permission_codes: Optional[List[str]] = None


class PermissionResponse(BaseModel):
    """权限响应"""
    id: int
    code: str
    resource: str
    action: str
    description: Optional[str] = None

    class Config:
        from_attributes = True


# ============== 组织相关 ==============

class OrganizationResponse(BaseModel):
    """组织响应"""
    id: int
    uuid: str
    name: str
    slug: str
    is_active: bool
    settings: Dict[str, Any] = {}
    created_at: datetime

    class Config:
        from_attributes = True


class OrganizationUpdateRequest(BaseModel):
    """更新组织请求"""
    name: Optional[str] = Field(None, max_length=255)
    settings: Optional[Dict[str, Any]] = None


# ============== 通用响应 ==============

class PaginatedResponse(BaseModel):
    """分页响应"""
    items: List[Any]
    total: int
    page: int
    page_size: int
    pages: int


class MessageResponse(BaseModel):
    """消息响应"""
    message: str
    success: bool = True


# 解决循环引用
TokenResponse.model_rebuild()
UserDetailResponse.model_rebuild()
