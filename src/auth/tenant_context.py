import contextvars
from typing import Optional

# Define the context variable to store the tenant ID
# Default is None, meaning no tenant context is set
tenant_id_context: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("tenant_id", default=None)

def get_tenant_id() -> Optional[str]:
    """
    Get the current tenant ID from the context.
    Returns None if no tenant ID is set.
    """
    return tenant_id_context.get()

def set_tenant_id(tenant_id: Optional[str]) -> contextvars.Token:
    """
    Set the tenant ID in the context.
    Returns a token that can be used to reset the context variable.
    """
    return tenant_id_context.set(tenant_id)

def reset_tenant_id(token: contextvars.Token) -> None:
    """
    Reset the tenant ID to its previous value using the provided token.
    """
    tenant_id_context.reset(token)
