from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from app.api.auth import authenticate


@pytest.mark.asyncio
async def test_rejects_missing_key_when_auth_enabled():
    settings = SimpleNamespace(auth_disabled=False, is_production=True, admin_api_key="a" * 32, tenant_api_keys={})
    with patch("app.api.auth.get_settings", return_value=settings):
        with pytest.raises(HTTPException) as exc:
            await authenticate(None)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_tenant_key_only_authorizes_configured_tenant():
    settings = SimpleNamespace(
        auth_disabled=False, is_production=True, admin_api_key="a" * 32,
        tenant_api_keys={"tenant-secret": ["tenant-a"]},
    )
    with patch("app.api.auth.get_settings", return_value=settings):
        context = await authenticate("tenant-secret")
    context.require_tenant("tenant-a")
    with pytest.raises(HTTPException) as exc:
        context.require_tenant("tenant-b")
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_admin_key_can_access_any_tenant():
    settings = SimpleNamespace(
        auth_disabled=False, is_production=True, admin_api_key="admin-secret", tenant_api_keys={}
    )
    with patch("app.api.auth.get_settings", return_value=settings):
        context = await authenticate("admin-secret")
    context.require_tenant("any-tenant")
    context.require_admin()
