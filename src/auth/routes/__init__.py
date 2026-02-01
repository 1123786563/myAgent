"""
认证服务路由模块初始化
"""

from auth.routes.auth_routes import router as auth_router
from auth.routes.user_routes import router as user_router
from auth.routes.role_routes import router as role_router

__all__ = ["auth_router", "user_router", "role_router"]
