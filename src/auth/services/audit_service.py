"""
审计服务
Audit Logging Service
"""

from typing import Optional, Any, Dict
from datetime import datetime
from core.db_helper import DBHelper
from core.auth_models import AuditLog
from infra.trace_context import TraceContext
from infra.logger import get_logger

log = get_logger("AuditService")


class AuditService:
    """审计日志服务"""

    @classmethod
    def log(
        cls,
        action: str,
        user_id: Optional[int] = None,
        organization_id: Optional[int] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        old_values: Optional[Dict[str, Any]] = None,
        new_values: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        status: str = "SUCCESS",
        error_message: Optional[str] = None
    ) -> Optional[int]:
        """
        记录审计日志

        Args:
            action: 操作类型 (如 "user.login", "transaction.approve")
            user_id: 执行操作的用户 ID
            organization_id: 组织 ID
            resource_type: 资源类型 (如 "User", "Transaction")
            resource_id: 资源 ID
            old_values: 变更前的值
            new_values: 变更后的值
            ip_address: 客户端 IP
            user_agent: User-Agent
            status: 结果状态 (SUCCESS, FAILURE, DENIED)
            error_message: 错误信息

        Returns:
            Optional[int]: 审计日志 ID
        """
        try:
            db = DBHelper()
            with db.transaction() as session:
                audit_entry = AuditLog(
                    user_id=user_id,
                    organization_id=organization_id,
                    action=action,
                    resource_type=resource_type,
                    resource_id=str(resource_id) if resource_id else None,
                    old_values=old_values,
                    new_values=new_values,
                    ip_address=ip_address,
                    user_agent=user_agent[:500] if user_agent else None,
                    trace_id=TraceContext.get_trace_id(),
                    status=status,
                    error_message=error_message
                )
                session.add(audit_entry)
                session.flush()
                return audit_entry.id
        except Exception as e:
            log.error(f"Failed to log audit event: {e}")
            return None

    @classmethod
    def log_login(
        cls,
        user_id: int,
        organization_id: int,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        success: bool = True,
        error_message: Optional[str] = None
    ):
        """记录登录事件"""
        cls.log(
            action="user.login",
            user_id=user_id,
            organization_id=organization_id,
            resource_type="User",
            resource_id=str(user_id),
            ip_address=ip_address,
            user_agent=user_agent,
            status="SUCCESS" if success else "FAILURE",
            error_message=error_message
        )

    @classmethod
    def log_logout(
        cls,
        user_id: int,
        organization_id: int,
        ip_address: Optional[str] = None
    ):
        """记录登出事件"""
        cls.log(
            action="user.logout",
            user_id=user_id,
            organization_id=organization_id,
            resource_type="User",
            resource_id=str(user_id),
            ip_address=ip_address
        )

    @classmethod
    def log_access_denied(
        cls,
        user_id: int,
        organization_id: int,
        action: str,
        resource_type: str,
        resource_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ):
        """记录访问被拒绝事件"""
        cls.log(
            action=f"access.denied.{action}",
            user_id=user_id,
            organization_id=organization_id,
            resource_type=resource_type,
            resource_id=resource_id,
            ip_address=ip_address,
            user_agent=user_agent,
            status="DENIED"
        )

    @classmethod
    def log_data_change(
        cls,
        action: str,
        user_id: int,
        organization_id: int,
        resource_type: str,
        resource_id: str,
        old_values: Optional[Dict[str, Any]] = None,
        new_values: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None
    ):
        """记录数据变更事件"""
        cls.log(
            action=action,
            user_id=user_id,
            organization_id=organization_id,
            resource_type=resource_type,
            resource_id=resource_id,
            old_values=old_values,
            new_values=new_values,
            ip_address=ip_address
        )
