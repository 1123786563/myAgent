import time
import json
from typing import Optional
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.background import BackgroundTask

from core.db_helper import DBHelper
from core.auth_models import AuditLog
from infra.logger import get_logger

log = get_logger("AuditMiddleware")

class AuditMiddleware(BaseHTTPMiddleware):
    """
    [Audit] 审计日志中间件
    自动记录修改类请求(POST, PUT, DELETE)和关键操作的操作日志
    """

    def __init__(self, app, exclude_paths: list = None):
        super().__init__(app)
        self.exclude_paths = exclude_paths or ["/health", "/metrics", "/docs", "/openapi.json"]

    async def dispatch(self, request: Request, call_next):
        start_time = time.time()

        # 1. 执行请求
        try:
            response = await call_next(request)
        except Exception as e:
            # 异常情况下也记录日志
            process_time = (time.time() - start_time) * 1000
            self._record_audit_log_background(request, 500, process_time, error=str(e))
            raise e

        # 2. 判断是否需要记录
        # 只记录修改操作，或者明确标记为敏感的 GET 操作（如导出）
        should_log = request.method in ["POST", "PUT", "DELETE", "PATCH"]

        # 排除路径
        if any(request.url.path.startswith(p) for p in self.exclude_paths):
            should_log = False

        # 包含特定 GET 操作
        if request.method == "GET" and ("export" in request.url.path or "download" in request.url.path):
            should_log = True

        if should_log:
            process_time = (time.time() - start_time) * 1000

            # 使用 BackgroundTask 在响应发送后异步写入数据库，不阻塞主线程
            response.background = BackgroundTask(
                self._record_audit_log,
                request=request,
                status_code=response.status_code,
                process_time=process_time
            )

        return response

    async def _record_audit_log(self, request: Request, status_code: int, process_time: float, error: str = None):
        """记录审计日志的具体实现"""
        try:
            # 获取用户上下文
            # 注意：这依赖于 AuthMiddleware 已经运行并将 user 信息放入 request.state 或 request.user
            user_id = None
            organization_id = None

            if hasattr(request, "state") and hasattr(request.state, "user"):
                user = request.state.user
                if user:
                    user_id = user.user_id
                    organization_id = user.organization_id

            # 如果没有找到用户（可能是登录接口本身），尝试从其他地方获取，或者留空

            # 构造资源类型和ID (简单的从 URL 推断)
            # /api/v1/users/123 -> resource_type=users, resource_id=123
            path_parts = request.url.path.strip("/").split("/")
            resource_type = path_parts[-2] if len(path_parts) > 1 else "unknown"
            resource_id = path_parts[-1] if len(path_parts) > 1 and path_parts[-1].isdigit() else None

            action = f"{resource_type}.{request.method.lower()}"

            # 构建日志对象
            audit_log = AuditLog(
                user_id=user_id,
                organization_id=organization_id,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                ip_address=request.client.host,
                user_agent=request.headers.get("user-agent"),
                status="SUCCESS" if status_code < 400 else "FAILURE",
                error_message=error,
                # trace_id 可以在这里添加，如果已有 Trace 中间件
            )

            # 写入数据库
            db = DBHelper()
            with db.transaction() as session:
                session.add(audit_log)
                # session.commit() # transaction 上下文会自动 commit

        except Exception as e:
            # 审计日志记录失败不应影响主业务，只记录错误日志
            log.error(f"Failed to record audit log: {e}")

    def _record_audit_log_background(self, request, status_code, process_time, error=None):
        """同步包装器，用于在异常处理中调用"""
        import asyncio
        loop = asyncio.get_event_loop()
        loop.create_task(self._record_audit_log(request, status_code, process_time, error))
