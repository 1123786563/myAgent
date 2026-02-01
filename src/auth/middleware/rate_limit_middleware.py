"""
限流中间件
Rate Limiting Middleware
"""

from fastapi import Request, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from collections import defaultdict
from datetime import datetime, timedelta
import asyncio
from core.config_manager import ConfigManager
from infra.logger import get_logger

log = get_logger("RateLimiter")


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    令牌桶限流中间件

    - 默认: 100 请求/分钟
    - 认证端点: 10 请求/分钟 (防止暴力破解)
    """

    def __init__(self, app):
        super().__init__(app)
        self.requests: dict = defaultdict(list)
        self.lock = asyncio.Lock()

        # 配置
        self.window_seconds = ConfigManager.get_int("api.rate_limit_window", 60)
        self.max_requests = ConfigManager.get_int("api.rate_limit_max", 100)
        self.auth_max_requests = ConfigManager.get_int("api.auth_rate_limit_max", 10)

        # 白名单路径 (不限流)
        self.whitelist_paths = {"/health", "/docs", "/openapi.json", "/redoc"}

    async def dispatch(self, request: Request, call_next) -> Response:
        # 跳过白名单路径
        path = request.url.path
        if path in self.whitelist_paths:
            return await call_next(request)

        client_ip = self._get_client_ip(request)

        # 认证端点使用更严格的限制
        is_auth_endpoint = path.startswith("/api/v1/auth/")
        max_req = self.auth_max_requests if is_auth_endpoint else self.max_requests

        async with self.lock:
            now = datetime.now()
            window_start = now - timedelta(seconds=self.window_seconds)

            # 清理过期请求记录
            self.requests[client_ip] = [
                req_time for req_time in self.requests[client_ip]
                if req_time > window_start
            ]

            current_count = len(self.requests[client_ip])

            if current_count >= max_req:
                log.warning(f"Rate limit exceeded: {client_ip} on {path} ({current_count}/{max_req})")
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="请求过于频繁，请稍后重试",
                    headers={"Retry-After": str(self.window_seconds)}
                )

            self.requests[client_ip].append(now)
            remaining = max_req - current_count - 1

        response = await call_next(request)

        # 添加限流响应头
        response.headers["X-RateLimit-Limit"] = str(max_req)
        response.headers["X-RateLimit-Remaining"] = str(max(0, remaining))
        response.headers["X-RateLimit-Reset"] = str(self.window_seconds)

        return response

    def _get_client_ip(self, request: Request) -> str:
        """获取客户端真实 IP (支持反向代理)"""
        # 检查 X-Forwarded-For 头
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            # 取第一个 IP (原始客户端)
            return forwarded.split(",")[0].strip()

        # 检查 X-Real-IP 头
        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            return real_ip

        # 回退到直接连接 IP
        return request.client.host if request.client else "unknown"

    async def cleanup_old_records(self):
        """定期清理过期记录 (可通过后台任务调用)"""
        async with self.lock:
            now = datetime.now()
            window_start = now - timedelta(seconds=self.window_seconds * 2)

            expired_ips = []
            for ip, times in self.requests.items():
                # 过滤并检查是否为空
                self.requests[ip] = [t for t in times if t > window_start]
                if not self.requests[ip]:
                    expired_ips.append(ip)

            for ip in expired_ips:
                del self.requests[ip]
