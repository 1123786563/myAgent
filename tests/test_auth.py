"""
认证模块单元测试
Authentication Module Unit Tests
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))


class TestPasswordService:
    """密码服务测试"""

    def test_hash_password(self):
        """测试密码哈希"""
        from auth.services.password_service import PasswordService

        password = "TestPassword123!"
        hashed = PasswordService.hash_password(password)

        assert hashed is not None
        assert hashed != password
        assert hashed.startswith("$2b$")

    def test_verify_password_correct(self):
        """测试正确密码验证"""
        from auth.services.password_service import PasswordService

        password = "TestPassword123!"
        hashed = PasswordService.hash_password(password)

        assert PasswordService.verify_password(password, hashed) is True

    def test_verify_password_incorrect(self):
        """测试错误密码验证"""
        from auth.services.password_service import PasswordService

        password = "TestPassword123!"
        wrong_password = "WrongPassword123!"
        hashed = PasswordService.hash_password(password)

        assert PasswordService.verify_password(wrong_password, hashed) is False

    def test_validate_password_strength_valid(self):
        """测试有效密码强度"""
        from auth.services.password_service import PasswordService

        valid_passwords = [
            "Password123!",
            "MySecure@Pass1",
            "Test#Pass2024",
        ]

        for password in valid_passwords:
            is_valid, _ = PasswordService.validate_password_strength(password)
            assert is_valid is True, f"Password should be valid: {password}"

    def test_validate_password_strength_invalid(self):
        """测试无效密码强度"""
        from auth.services.password_service import PasswordService

        invalid_passwords = [
            ("short", "密码长度不足"),
            ("nouppercase123!", "缺少大写字母"),
            ("NOLOWERCASE123!", "缺少小写字母"),
            ("NoNumbers!", "缺少数字"),
        ]

        for password, expected_error in invalid_passwords:
            is_valid, error = PasswordService.validate_password_strength(password)
            assert is_valid is False, f"Password should be invalid: {password}"


class TestJWTService:
    """JWT 服务测试"""

    def test_create_access_token(self):
        """测试创建访问令牌"""
        from auth.services.jwt_service import JWTService

        user_id = 1
        org_id = 1
        roles = ["ADMIN"]
        permissions = ["transactions:read", "transactions:create"]

        token = JWTService.create_access_token(
            user_id=user_id,
            organization_id=org_id,
            roles=roles,
            permissions=permissions
        )

        assert token is not None
        assert isinstance(token, str)
        assert len(token) > 0

    def test_decode_token_valid(self):
        """测试解码有效令牌"""
        from auth.services.jwt_service import JWTService

        user_id = 1
        org_id = 1
        roles = ["ADMIN"]
        permissions = ["transactions:read"]

        token = JWTService.create_access_token(
            user_id=user_id,
            organization_id=org_id,
            roles=roles,
            permissions=permissions
        )

        payload = JWTService.decode_token(token)

        assert payload is not None
        assert payload["sub"] == str(user_id)
        assert payload["org_id"] == org_id
        assert payload["roles"] == roles

    def test_decode_token_invalid(self):
        """测试解码无效令牌"""
        from auth.services.jwt_service import JWTService

        invalid_token = "invalid.token.here"
        payload = JWTService.decode_token(invalid_token)

        assert payload is None

    def test_create_refresh_token(self):
        """测试创建刷新令牌"""
        from auth.services.jwt_service import JWTService

        user_id = 1
        token = JWTService.create_refresh_token(user_id=user_id)

        assert token is not None
        assert isinstance(token, str)

    def test_token_expiration(self):
        """测试令牌过期"""
        from auth.services.jwt_service import JWTService
        import time

        # 创建一个很短的过期时间
        with patch.object(JWTService, 'ACCESS_TOKEN_EXPIRE_MINUTES', 0):
            token = JWTService.create_access_token(
                user_id=1,
                organization_id=1,
                roles=[],
                permissions=[],
                expires_delta=timedelta(seconds=1)
            )

        # 等待过期
        time.sleep(2)

        payload = JWTService.decode_token(token)
        assert payload is None


class TestPermissions:
    """权限测试"""

    def test_role_permissions_mapping(self):
        """测试角色权限映射"""
        from auth.permissions import RolePermissions, SystemRole

        # ADMIN 应该有用户管理权限
        admin_perms = RolePermissions.get_permissions(SystemRole.ADMIN)
        assert "users:read" in admin_perms
        assert "users:create" in admin_perms

        # VIEWER 应该只有只读权限
        viewer_perms = RolePermissions.get_permissions(SystemRole.VIEWER)
        assert "transactions:read" in viewer_perms
        assert "transactions:create" not in viewer_perms

    def test_super_admin_has_all_permissions(self):
        """测试超级管理员拥有所有权限"""
        from auth.permissions import RolePermissions, SystemRole

        super_admin_perms = RolePermissions.get_permissions(SystemRole.SUPER_ADMIN)

        # 超级管理员应该有系统配置权限
        assert "system_config:manage" in super_admin_perms
        assert "audit:read" in super_admin_perms

    def test_privacy_guard_role_mapping(self):
        """测试 PrivacyGuard 角色映射"""
        from auth.permissions import PRIVACY_GUARD_ROLE_MAPPING

        assert PRIVACY_GUARD_ROLE_MAPPING["SUPER_ADMIN"] == "ADMIN"
        assert PRIVACY_GUARD_ROLE_MAPPING["ADMIN"] == "ADMIN"
        assert PRIVACY_GUARD_ROLE_MAPPING["VIEWER"] == "GUEST"
