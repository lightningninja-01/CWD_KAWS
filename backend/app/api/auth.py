"""API-key authentication and tenant authorization for dashboard routes."""
from dataclasses import dataclass
from hmac import compare_digest

from fastapi import Header, HTTPException, status

from app.config.settings import get_settings


@dataclass(frozen=True)
class AuthContext:
    role: str
    tenant_ids: frozenset[str]

    def require_tenant(self, tenant_id: str) -> None:
        if self.role != "admin" and tenant_id not in self.tenant_ids:
            # Deliberately avoid revealing whether the tenant exists.
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant access denied")

    def require_admin(self) -> None:
        if self.role != "admin":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Administrator access required")


async def authenticate(x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> AuthContext:
    settings = get_settings()
    if settings.auth_disabled and not settings.is_production:
        return AuthContext("admin", frozenset())
    if not x_api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing API key")
    if settings.admin_api_key and compare_digest(x_api_key, settings.admin_api_key):
        return AuthContext("admin", frozenset())
    for candidate, tenant_ids in settings.tenant_api_keys.items():
        if compare_digest(x_api_key, candidate):
            return AuthContext("tenant", frozenset(tenant_ids))
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")
