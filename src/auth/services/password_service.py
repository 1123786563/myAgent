"""
密码服务
Password Service - bcrypt hashing
"""

import bcrypt
import re
from typing import Tuple
from core.config_manager import ConfigManager


class PasswordService:
    """密码哈希与验证服务"""

    def __init__(self):
        self.min_length = ConfigManager.get_int("auth.password_min_length", 8)
        self.require_uppercase = ConfigManager.get_bool("auth.password_require_uppercase", True)
        self.require_number = ConfigManager.get_bool("auth.password_require_number", True)
        self.require_special = ConfigManager.get_bool("auth.password_require_special", False)
        self.rounds = ConfigManager.get_int("auth.bcrypt_rounds", 12)

    def hash_password(self, password: str) -> str:
        """
        对密码进行哈希

        Args:
            password: 明文密码

        Returns:
            str: bcrypt 哈希后的密码
        """
        salt = bcrypt.gensalt(rounds=self.rounds)
        hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
        return hashed.decode('utf-8')

    def verify_password(self, password: str, hashed: str) -> bool:
        """
        验证密码是否正确

        Args:
            password: 明文密码
            hashed: 哈希后的密码

        Returns:
            bool: 密码是否匹配
        """
        try:
            return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))
        except Exception:
            return False

    def validate_password_strength(self, password: str) -> Tuple[bool, str]:
        """
        验证密码强度

        Args:
            password: 待验证的密码

        Returns:
            Tuple[bool, str]: (是否通过, 错误消息)
        """
        if len(password) < self.min_length:
            return False, f"密码长度至少 {self.min_length} 个字符"

        if self.require_uppercase and not re.search(r'[A-Z]', password):
            return False, "密码必须包含至少一个大写字母"

        if self.require_number and not re.search(r'\d', password):
            return False, "密码必须包含至少一个数字"

        if self.require_special and not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
            return False, "密码必须包含至少一个特殊字符"

        return True, ""

    def is_common_password(self, password: str) -> bool:
        """检查是否为常见弱密码"""
        common_passwords = {
            'password', '123456', '12345678', 'qwerty', 'abc123',
            'password1', 'admin', 'letmein', 'welcome', 'monkey',
            '1234567890', 'password123', 'iloveyou', '111111'
        }
        return password.lower() in common_passwords


# 单例实例
_password_service = None


def get_password_service() -> PasswordService:
    """获取密码服务单例"""
    global _password_service
    if _password_service is None:
        _password_service = PasswordService()
    return _password_service
