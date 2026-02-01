"""
JWT 服务
JWT Token Generation and Validation Service
"""

import jwt
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Tuple
from uuid import uuid4
from core.config_manager import ConfigManager
from infra.logger import get_logger

log = get_logger("JWTService")


class JWTService:
    """JWT 令牌生成与验证服务"""

    def __init__(self):
        self.secret_key = ConfigManager.get("auth.jwt_secret_key", "ledger-alpha-secret-key-change-in-production")
        self.algorithm = ConfigManager.get("auth.jwt_algorithm", "HS256")
        self.access_token_expire_minutes = ConfigManager.get_int("auth.access_token_expire_minutes", 15)
        self.refresh_token_expire_days = ConfigManager.get_int("auth.refresh_token_expire_days", 7)
        self.issuer = ConfigManager.get("auth.jwt_issuer", "ledger-alpha")

    def create_access_token(
        self,
        user_id: int,
        user_uuid: str,
        organization_id: int,
        email: str,
        roles: list,
        permissions: list,
        extra_claims: Optional[Dict[str, Any]] = None
    ) -> Tuple[str, datetime, str]:
        """
        创建 JWT 访问令牌

        Args:
            user_id: 用户 ID
            user_uuid: 用户 UUID
            organization_id: 组织 ID
            email: 用户邮箱
            roles: 用户角色列表
            permissions: 用户权限列表
            extra_claims: 额外的声明

        Returns:
            Tuple[str, datetime, str]: (token, 过期时间, jti)
        """
        now = datetime.utcnow()
        expires_at = now + timedelta(minutes=self.access_token_expire_minutes)
        jti = str(uuid4())

        payload = {
            # 标准声明
            "iss": self.issuer,
            "sub": user_uuid,
            "iat": now,
            "exp": expires_at,
            "jti": jti,

            # 自定义声明
            "user_id": user_id,
            "org_id": organization_id,
            "email": email,
            "roles": roles,
            "permissions": permissions,
            "type": "access"
        }

        if extra_claims:
            payload.update(extra_claims)

        token = jwt.encode(payload, self.secret_key, algorithm=self.algorithm)
        return token, expires_at, jti

    def create_refresh_token(self, user_id: int, user_uuid: str) -> Tuple[str, datetime, str]:
        """
        创建刷新令牌

        Args:
            user_id: 用户 ID
            user_uuid: 用户 UUID

        Returns:
            Tuple[str, datetime, str]: (token, 过期时间, token_hash)
        """
        now = datetime.utcnow()
        expires_at = now + timedelta(days=self.refresh_token_expire_days)

        payload = {
            "iss": self.issuer,
            "sub": user_uuid,
            "iat": now,
            "exp": expires_at,
            "jti": str(uuid4()),
            "user_id": user_id,
            "type": "refresh"
        }

        token = jwt.encode(payload, self.secret_key, algorithm=self.algorithm)
        token_hash = hashlib.sha256(token.encode()).hexdigest()

        return token, expires_at, token_hash

    def decode_token(self, token: str, expected_type: str = "access") -> Optional[Dict[str, Any]]:
        """
        解码并验证 JWT 令牌

        Args:
            token: JWT 令牌
            expected_type: 期望的令牌类型 ("access" 或 "refresh")

        Returns:
            Optional[Dict]: 有效则返回 payload，否则返回 None
        """
        try:
            payload = jwt.decode(
                token,
                self.secret_key,
                algorithms=[self.algorithm],
                issuer=self.issuer
            )

            if payload.get("type") != expected_type:
                log.warning(f"Token type mismatch: expected {expected_type}, got {payload.get('type')}")
                return None

            return payload

        except jwt.ExpiredSignatureError:
            log.debug("Token expired")
            return None
        except jwt.InvalidTokenError as e:
            log.warning(f"Invalid token: {e}")
            return None

    def get_jti(self, token: str) -> Optional[str]:
        """
        从令牌中提取 JTI (不验证签名)

        Args:
            token: JWT 令牌

        Returns:
            Optional[str]: JTI 或 None
        """
        try:
            payload = jwt.decode(token, options={"verify_signature": False})
            return payload.get("jti")
        except Exception:
            return None

    def get_token_hash(self, token: str) -> str:
        """获取令牌的 SHA-256 哈希"""
        return hashlib.sha256(token.encode()).hexdigest()

    @property
    def access_token_expire_seconds(self) -> int:
        """访问令牌过期时间（秒）"""
        return self.access_token_expire_minutes * 60


# 单例实例
_jwt_service = None


def get_jwt_service() -> JWTService:
    """获取 JWT 服务单例"""
    global _jwt_service
    if _jwt_service is None:
        _jwt_service = JWTService()
    return _jwt_service
