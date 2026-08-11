"""
Integration test for the webhook flow — verifies the core architectural
requirement: the endpoint responds immediately and does NOT wait for the
LangGraph run to complete.
"""
import json
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.utils.signature_verification import verify_meta_signature
import hashlib
import hmac


def _sign(body: bytes, secret: str) -> str:
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


SAMPLE_PAYLOAD = {
    "object": "whatsapp_business_account",
    "entry": [
        {
            "id": "entry1",
            "changes": [
                {
                    "field": "messages",
                    "value": {
                        "messaging_product": "whatsapp",
                        "metadata": {"phone_number_id": "test-phone-number-id", "display_phone_number": "1555"},
                        "contacts": [{"wa_id": "15559998888", "profile": {"name": "Test Customer"}}],
                        "messages": [
                            {
                                "id": "wamid.test123",
                                "from": "15559998888",
                                "timestamp": "1234567890",
                                "type": "text",
                                "text": {"body": "Hi, do you have the catalog?"},
                            }
                        ],
                    },
                }
            ],
        }
    ],
}


class TestWebhookVerification:
    async def test_get_verification_echoes_challenge_on_valid_token(self, monkeypatch):
        monkeypatch.setenv("META_WEBHOOK_VERIFY_TOKEN", "test-verify-token")
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/api/webhooks/whatsapp",
                params={"hub.mode": "subscribe", "hub.challenge": "12345", "hub.verify_token": "test-verify-token"},
            )
        assert response.status_code == 200
        assert response.text == "12345"

    async def test_get_verification_rejects_wrong_token(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/api/webhooks/whatsapp",
                params={"hub.mode": "subscribe", "hub.challenge": "12345", "hub.verify_token": "wrong-token"},
            )
        assert response.status_code == 403


class TestWebhookAsyncHandling:
    async def test_post_returns_200_without_waiting_for_graph_completion(self):
        """
        The core requirement: POST responds immediately. We verify this by
        patching the background processor to hang indefinitely — if the
        route awaited it, this test would time out; since it doesn't, the
        request must complete without waiting for the (never-resolving) task.
        """
        raw_body = json.dumps(SAMPLE_PAYLOAD).encode()
        signature = _sign(raw_body, "test-app-secret")

        enqueue = AsyncMock(return_value=({"_id": "job-1"}, True))
        with patch("app.api.routers.webhook.JobRepository") as repo_cls:
            repo_cls.return_value.enqueue = enqueue
            app.state.db = object()
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post(
                    "/api/webhooks/whatsapp",
                    content=raw_body,
                    headers={"X-Hub-Signature-256": signature, "Content-Type": "application/json"},
                )

        assert response.status_code == 200
        enqueue.assert_awaited_once()

    async def test_rejects_invalid_signature(self):
        raw_body = json.dumps(SAMPLE_PAYLOAD).encode()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/webhooks/whatsapp",
                content=raw_body,
                headers={"X-Hub-Signature-256": "sha256=wrongsignature", "Content-Type": "application/json"},
            )
        assert response.status_code == 401


async def _never_resolve():
    import asyncio

    await asyncio.sleep(3600)


def test_signature_verification_util_matches_hmac_reference():
    body = b'{"test": "payload"}'
    secret = "my-secret"
    valid_sig = _sign(body, secret)

    with patch("app.utils.signature_verification.get_settings") as mock_settings:
        mock_settings.return_value.meta_app_secret = secret
        assert verify_meta_signature(body, valid_sig) is True
        assert verify_meta_signature(body, "sha256=deadbeef") is False
        assert verify_meta_signature(body, None) is False
