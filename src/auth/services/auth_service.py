"""
认证服务
Authentication Service - Login, Register, Token management
"""

from typing import Optional, Tuple, List
from datetime import datetime, timedelta
import re
from core.db_helper import DBHelper
from core.auth_models import User, Organization, Role, Permission, RefreshToken, TokenBlacklist
from auth.services.password_service import get_password_service
from auth.services.jwt_service import get_jwt_service
from auth.services.audit_service import AuditService
from auth.permissions import RoleType, DEFAULT_ROLE_PERMISSIONS, ROLE_PRIORITY
from core.config_manager import ConfigManager
from infra.logger import get_logger

log = get_logger("AuthService")


class AuthService:
    """认证服务"""

    def __init__(self):
        self.db = DBHelper()
        self.password_service = get_password_service()
        self.jwt_service = get_jwt_service()
        self.max_failed_attempts = ConfigManager.get_int("auth.max_failed_login_attempts", 5)
        self.lockout_minutes = ConfigManager.get_int("auth.account_lockout_minutes", 30)

    def register(
        self,
        email: str,
        password: str,
        full_name: str,
        organization_name: Optional[str] = None,
        organization_slug: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> Tuple[Optional[User], Optional[str]]:
        """
        用户注册

        Args:
            email: 邮箱
            password: 密码
            full_name: 姓名
            organization_name: 组织名称 (新建组织时必填)
            organization_slug: 组织标识 (加入已有组织)
            ip_address: 客户端 IP
            user_agent: User-Agent

        Returns:
            Tuple[Optional[User], Optional[str]]: (用户对象, 错误信息)
        """
        # 验证密码强度
        is_valid, error_msg = self.password_service.validate_password_strength(password)
        if not is_valid:
            return None, error_msg

        if self.password_service.is_common_password(password):
            return None, "密码过于简单，请使用更复杂的密码"

        with self.db.transaction() as session:
            # 查找或创建组织
            organization = None

            if organization_slug:
                # 加入已有组织
                organization = session.query(Organization).filter_by(
                    slug=organization_slug, is_active=True
                ).first()
                if not organization:
                    return None, f"组织 '{organization_slug}' 不存在"
            else:
                # 创建新组织
                if not organization_name:
                    organization_name = f"{full_name}的组织"

                # 生成 slug
                slug = self._generate_slug(organization_name)
                existing = session.query(Organization).filter_by(slug=slug).first()
                if existing:
                    slug = f"{slug}-{datetime.now().strftime('%Y%m%d%H%M%S')}"

                organization = Organization(
                    name=organization_name,
                    slug=slug,
                    is_active=True
                )
                session.add(organization)
                session.flush()

            # 检查邮箱是否已注册
            existing_user = session.query(User).filter_by(
                email=email, organization_id=organization.id
            ).first()
            if existing_user:
                return None, "该邮箱已被注册"

            # 创建用户
            password_hash = self.password_service.hash_password(password)
            user = User(
                email=email,
                password_hash=password_hash,
                full_name=full_name,
                organization_id=organization.id,
                is_active=True,
                is_verified=False
            )
            session.add(user)
            session.flush()

            # 分配默认角色
            default_role = self._get_or_create_default_role(session, organization.id)
            if default_role:
                user.roles.append(default_role)

            # 如果是组织的第一个用户，设为管理员
            user_count = session.query(User).filter_by(organization_id=organization.id).count()
            if user_count == 1:
                admin_role = self._get_or_create_role(session, RoleType.ADMIN, organization.id)
                if admin_role and admin_role not in user.roles:
                    user.roles.append(admin_role)

            # 记录审计日志
            AuditService.log(
                action="user.register",
                user_id=user.id,
                organization_id=organization.id,
                resource_type="User",
                resource_id=str(user.id),
                new_values={"email": email, "full_name": full_name},
                ip_address=ip_address,
                user_agent=user_agent
            )

            return user, None

    def login(
        self,
        email: str,
        password: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> Tuple[Optional[dict], Optional[str]]:
        """
        用户登录

        Args:
            email: 邮箱
            password: 密码
            ip_address: 客户端 IP
            user_agent: User-Agent

        Returns:
            Tuple[Optional[dict], Optional[str]]: (令牌信息, 错误信息)
        """
        with self.db.transaction() as session:
            # 查找用户 (跨组织查找)
            user = session.query(User).filter_by(email=email).first()

            if not user:
                return None, "邮箱或密码错误"

            # 检查账户状态
            if not user.is_active:
                AuditService.log_login(
                    user.id, user.organization_id, ip_address, user_agent,
                    success=False, error_message="账户已禁用"
                )
                return None, "账户已被禁用"

            # 检查账户锁定
            if user.is_locked:
                remaining = (user.locked_until - datetime.utcnow()).seconds // 60
                return None, f"账户已锁定，请 {remaining} 分钟后重试"

            # 验证密码
            if not self.password_service.verify_password(password, user.password_hash):
                # 增加失败次数
                user.failed_login_attempts += 1

                # 检查是否需要锁定
                if user.failed_login_attempts >= self.max_failed_attempts:
                    user.locked_until = datetime.utcnow() + timedelta(minutes=self.lockout_minutes)
                    log.warning(f"Account locked: {email} after {user.failed_login_attempts} failed attempts")

                AuditService.log_login(
                    user.id, user.organization_id, ip_address, user_agent,
                    success=False, error_message="密码错误"
                )
                return None, "邮箱或密码错误"

            # 登录成功，重置失败计数
            user.failed_login_attempts = 0
            user.locked_until = None
            user.last_login_at = datetime.utcnow()

            # 获取用户权限
            roles = [role.name for role in user.roles]
            permissions = self._get_user_permissions(user)

            # 获取组织信息
            org = session.query(Organization).get(user.organization_id)
            org_name = org.name if org else ""

            # 生成令牌
            access_token, access_expires, jti = self.jwt_service.create_access_token(
                user_id=user.id,
                user_uuid=user.uuid,
                organization_id=user.organization_id,
                email=user.email,
                roles=roles,
                permissions=permissions
            )

            refresh_token, refresh_expires, token_hash = self.jwt_service.create_refresh_token(
                user_id=user.id,
                user_uuid=user.uuid
            )

            # 保存刷新令牌
            rt = RefreshToken(
                token_hash=token_hash,
                user_id=user.id,
                device_info=user_agent[:255] if user_agent else None,
                ip_address=ip_address,
                expires_at=refresh_expires
            )
            session.add(rt)

            # 记录审计日志
            AuditService.log_login(user.id, user.organization_id, ip_address, user_agent)

            return {
                "access_token": access_token,
                "refresh_token": refresh_token,
                "token_type": "bearer",
                "expires_in": self.jwt_service.access_token_expire_seconds,
                "user": {
                    "uuid": user.uuid,
                    "email": user.email,
                    "full_name": user.full_name,
                    "organization_id": user.organization_id,
                    "organization_name": org_name,
                    "roles": roles,
                    "permissions": permissions,
                    "is_verified": user.is_verified,
                    "created_at": user.created_at.isoformat()
                }
            }, None

    def refresh_token(
        self,
        refresh_token: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> Tuple[Optional[dict], Optional[str]]:
        """
        刷新访问令牌

        Args:
            refresh_token: 刷新令牌
            ip_address: 客户端 IP
            user_agent: User-Agent

        Returns:
            Tuple[Optional[dict], Optional[str]]: (新令牌信息, 错误信息)
        """
        # 验证刷新令牌
        payload = self.jwt_service.decode_token(refresh_token, expected_type="refresh")
        if not payload:
            return None, "无效或过期的刷新令牌"

        token_hash = self.jwt_service.get_token_hash(refresh_token)

        with self.db.transaction() as session:
            # 查找令牌记录
            rt = session.query(RefreshToken).filter_by(token_hash=token_hash).first()
            if not rt or not rt.is_valid:
                return None, "刷新令牌已失效"

            # 获取用户
            user = session.query(User).get(rt.user_id)
            if not user or not user.is_active:
                return None, "用户不存在或已禁用"

            # 撤销旧令牌 (令牌轮换)
            rt.revoked_at = datetime.utcnow()

            # 获取用户权限
            roles = [role.name for role in user.roles]
            permissions = self._get_user_permissions(user)

            # 获取组织信息
            org = session.query(Organization).get(user.organization_id)
            org_name = org.name if org else ""

            # 生成新令牌
            access_token, access_expires, jti = self.jwt_service.create_access_token(
                user_id=user.id,
                user_uuid=user.uuid,
                organization_id=user.organization_id,
                email=user.email,
                roles=roles,
                permissions=permissions
            )

            new_refresh_token, refresh_expires, new_token_hash = self.jwt_service.create_refresh_token(
                user_id=user.id,
                user_uuid=user.uuid
            )

            # 保存新刷新令牌
            new_rt = RefreshToken(
                token_hash=new_token_hash,
                user_id=user.id,
                device_info=user_agent[:255] if user_agent else None,
                ip_address=ip_address,
                expires_at=refresh_expires
            )
            session.add(new_rt)

            return {
                "access_token": access_token,
                "refresh_token": new_refresh_token,
                "token_type": "bearer",
                "expires_in": self.jwt_service.access_token_expire_seconds,
                "user": {
                    "uuid": user.uuid,
                    "email": user.email,
                    "full_name": user.full_name,
                    "organization_id": user.organization_id,
                    "organization_name": org_name,
                    "roles": roles,
                    "permissions": permissions,
                    "is_verified": user.is_verified,
                    "created_at": user.created_at.isoformat()
                }
            }, None

    def logout(self, jti: str, user_id: int, organization_id: int, ip_address: Optional[str] = None):
        """
        登出 (将访问令牌加入黑名单)

        Args:
            jti: JWT ID
            user_id: 用户 ID
            organization_id: 组织 ID
            ip_address: 客户端 IP
        """
        with self.db.transaction() as session:
            # 将访问令牌加入黑名单
            expires_at = datetime.utcnow() + timedelta(
                minutes=self.jwt_service.access_token_expire_minutes
            )
            blacklist = TokenBlacklist(jti=jti, expires_at=expires_at)
            session.add(blacklist)

        AuditService.log_logout(user_id, organization_id, ip_address)

    def logout_all_devices(self, user_id: int, organization_id: int, ip_address: Optional[str] = None):
        """
        登出所有设备 (撤销所有刷新令牌)

        Args:
            user_id: 用户 ID
            organization_id: 组织 ID
            ip_address: 客户端 IP
        """
        with self.db.transaction() as session:
            session.query(RefreshToken).filter(
                RefreshToken.user_id == user_id,
                RefreshToken.revoked_at.is_(None)
            ).update({"revoked_at": datetime.utcnow()})

        AuditService.log(
            action="user.logout_all",
            user_id=user_id,
            organization_id=organization_id,
            ip_address=ip_address
        )

    def change_password(
        self,
        user_id: int,
        old_password: str,
        new_password: str,
        ip_address: Optional[str] = None
    ) -> Tuple[bool, Optional[str]]:
        """
        修改密码

        Args:
            user_id: 用户 ID
            old_password: 旧密码
            new_password: 新密码
            ip_address: 客户端 IP

        Returns:
            Tuple[bool, Optional[str]]: (是否成功, 错误信息)
        """
        # 验证新密码强度
        is_valid, error_msg = self.password_service.validate_password_strength(new_password)
        if not is_valid:
            return False, error_msg

        with self.db.transaction() as session:
            user = session.query(User).get(user_id)
            if not user:
                return False, "用户不存在"

            # 验证旧密码
            if not self.password_service.verify_password(old_password, user.password_hash):
                return False, "当前密码错误"

            # 更新密码
            user.password_hash = self.password_service.hash_password(new_password)

            # 撤销所有刷新令牌 (强制重新登录)
            session.query(RefreshToken).filter(
                RefreshToken.user_id == user_id,
                RefreshToken.revoked_at.is_(None)
            ).update({"revoked_at": datetime.utcnow()})

            AuditService.log(
                action="user.password_change",
                user_id=user_id,
                organization_id=user.organization_id,
                resource_type="User",
                resource_id=str(user_id),
                ip_address=ip_address
            )

        return True, None

    def _get_user_permissions(self, user: User) -> List[str]:
        """获取用户的所有权限"""
        permissions = set()
        for role in user.roles:
            for perm in role.permissions:
                permissions.add(perm.code)
        return list(permissions)

    def _generate_slug(self, name: str) -> str:
        """生成 URL 友好的 slug"""
        # 移除特殊字符，转换为小写
        slug = re.sub(r'[^\w\s-]', '', name.lower())
        slug = re.sub(r'[\s_]+', '-', slug)
        slug = re.sub(r'-+', '-', slug).strip('-')
        return slug[:100] if slug else "org"

    def _get_or_create_default_role(self, session, organization_id: int) -> Optional[Role]:
        """获取或创建默认角色 (VIEWER)"""
        return self._get_or_create_role(session, RoleType.VIEWER, organization_id)

    def _get_or_create_role(self, session, role_type: RoleType, organization_id: int) -> Optional[Role]:
        """获取或创建指定角色"""
        role = session.query(Role).filter_by(
            name=role_type.value,
            organization_id=organization_id
        ).first()

        if role:
            return role

        # 创建角色
        role = Role(
            name=role_type.value,
            display_name=role_type.value.replace("_", " ").title(),
            organization_id=organization_id,
            is_system_role=True,
            priority=ROLE_PRIORITY.get(role_type, 0)
        )
        session.add(role)
        session.flush()

        # 添加权限
        perm_codes = DEFAULT_ROLE_PERMISSIONS.get(role_type, [])
        for code in perm_codes:
            perm = session.query(Permission).filter_by(code=code).first()
            if not perm:
                # 创建权限
                parts = code.split(":")
                perm = Permission(
                    code=code,
                    resource=parts[0] if len(parts) > 0 else code,
                    action=parts[1] if len(parts) > 1 else "read"
                )
                session.add(perm)
                session.flush()
            role.permissions.append(perm)

        return role


# 单例
_auth_service = None


def get_auth_service() -> AuthService:
    """获取认证服务单例"""
    global _auth_service
    if _auth_service is None:
        _auth_service = AuthService()
    return _auth_service
