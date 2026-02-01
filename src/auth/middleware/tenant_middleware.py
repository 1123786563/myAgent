from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from auth.tenant_context import set_tenant_id, reset_tenant_id

class TenantMiddleware(BaseHTTPMiddleware):
    """
    Middleware to extract Tenant ID from headers and set it in the context.
    Currently trusts the X-Tenant-ID header for development purposes.
    """
    async def dispatch(self, request: Request, call_next):
        # Extract tenant ID from headers
        # Default to None if not present
        tenant_id = request.headers.get("X-Tenant-ID")

        # Set the tenant ID in the context variable
        token = set_tenant_id(tenant_id)

        try:
            # Process the request
            response = await call_next(request)
            return response
        finally:
            # Reset the context variable after the request is processed
            # This ensures that the context is clean for the next use (though usually task-local)
            reset_tenant_id(token)
