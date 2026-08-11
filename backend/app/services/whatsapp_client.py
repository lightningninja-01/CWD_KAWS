"""
WhatsApp Cloud API client - wraps every Meta Graph API call this app makes.

Retry policy: exponential backoff on 5xx/timeout/connection errors only.
4xx errors mean the payload itself is wrong (bad phone number, expired
token, malformed template) - retrying won't fix that, so we fail fast and
surface a typed MetaAPIError instead of burning retries on a guaranteed
failure.
"""
import asyncio

import httpx

from app.config.settings import get_settings
from app.exceptions.custom_exceptions import MetaAPIError
from app.utils.logger import get_logger

log = get_logger(__name__)

_MAX_RETRIES = 3
_BACKOFF_BASE_SECONDS = 1.0


class WhatsAppClient:
    def __init__(self) -> None:
        settings = get_settings()
        self._phone_number_id = settings.meta_phone_number_id
        self._base_url = settings.graph_api_base_url
        self._default_access_token = settings.meta_access_token
        self._access_tokens = settings.meta_access_tokens

    def _headers_for(self, phone_number_id: str | None = None) -> dict[str, str]:
        token = self._access_tokens.get(phone_number_id or "", self._default_access_token)
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    async def _post(self, payload: dict, *, phone_number_id: str | None = None) -> dict:
        outbound_phone_number_id = phone_number_id or self._phone_number_id
        url = f"{self._base_url}/{outbound_phone_number_id}/messages"
        last_error: Exception | None = None

        async with httpx.AsyncClient(timeout=10.0) as client:
            for attempt in range(1, _MAX_RETRIES + 1):
                try:
                    response = await client.post(url, headers=self._headers_for(outbound_phone_number_id), json=payload)
                    if response.status_code >= 500:
                        raise MetaAPIError(
                            f"Meta API server error (status {response.status_code})",
                            response_body=response.text,
                        )
                    if response.status_code >= 400:
                        # Client error: payload/auth issue. Don't retry, fail immediately.
                        raise MetaAPIError(
                            f"Meta API rejected request (status {response.status_code}): {response.text}",
                            response_body=response.text,
                            status_code=response.status_code,
                        )
                    return response.json()

                except (httpx.TimeoutException, httpx.ConnectError, MetaAPIError) as exc:
                    last_error = exc
                    is_retryable = not (isinstance(exc, MetaAPIError) and exc.status_code < 500)
                    if not is_retryable or attempt == _MAX_RETRIES:
                        break
                    backoff = _BACKOFF_BASE_SECONDS * (2 ** (attempt - 1))
                    log.warning(f"Meta API call failed (attempt {attempt}/{_MAX_RETRIES}), retrying in {backoff}s")
                    await asyncio.sleep(backoff)

        raise last_error if last_error else MetaAPIError("Meta API call failed for an unknown reason")

    async def mark_as_read(self, meta_message_id: str, *, phone_number_id: str | None = None) -> None:
        await self._post({
            "messaging_product": "whatsapp",
            "status": "read",
            "message_id": meta_message_id,
        }, phone_number_id=phone_number_id)

    async def send_typing_indicator(self, meta_message_id: str, *, phone_number_id: str | None = None) -> None:
        """
        Meta's typing indicator is anchored to the message being replied to.
        Called repeatedly by the heartbeat service since the indicator
        expires after ~25 seconds on Meta's side.
        """
        await self._post({
            "messaging_product": "whatsapp",
            "status": "read",
            "message_id": meta_message_id,
            "typing_indicator": {"type": "text"},
        }, phone_number_id=phone_number_id)

    async def send_text(self, to_phone: str, body: str, *, phone_number_id: str | None = None) -> str:
        result = await self._post({
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to_phone,
            "type": "text",
            "text": {"body": body, "preview_url": False},
        }, phone_number_id=phone_number_id)
        return _extract_message_id(result)

    async def send_image(
        self,
        to_phone: str,
        image_url: str,
        caption: str = "",
        *,
        phone_number_id: str | None = None,
    ) -> str:
        result = await self._post({
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to_phone,
            "type": "image",
            "image": {"link": image_url, "caption": caption},
        }, phone_number_id=phone_number_id)
        return _extract_message_id(result)

    async def send_document(
        self,
        to_phone: str,
        document_url: str,
        filename: str,
        caption: str = "",
        *,
        phone_number_id: str | None = None,
    ) -> str:
        result = await self._post({
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to_phone,
            "type": "document",
            "document": {"link": document_url, "filename": filename, "caption": caption},
        }, phone_number_id=phone_number_id)
        return _extract_message_id(result)

    async def send_template(
        self, to_phone: str, template_name: str, params: list[str], *, phone_number_id: str | None = None
    ) -> str:
        """Used by the broadcast service; WhatsApp requires pre-approved templates for outbound-initiated messages."""
        components = [{"type": "body", "parameters": [{"type": "text", "text": p} for p in params]}] if params else []
        result = await self._post({
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to_phone,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": "en_US"},
                "components": components,
            },
        }, phone_number_id=phone_number_id)
        return _extract_message_id(result)

    async def fetch_media_url(self, media_id: str) -> str:
        """Meta's media objects require a two-step fetch: ID -> temporary URL -> bytes."""
        settings = get_settings()
        url = f"{self._base_url}/{media_id}"
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, headers={"Authorization": f"Bearer {settings.meta_access_token}"})
            if response.status_code >= 400:
                raise MetaAPIError(f"Failed to fetch media metadata (status {response.status_code})")
            return response.json()["url"]

    async def download_media_bytes(self, media_url: str) -> bytes:
        settings = get_settings()
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(media_url, headers={"Authorization": f"Bearer {settings.meta_access_token}"})
            if response.status_code >= 400:
                raise MetaAPIError(f"Failed to download media bytes (status {response.status_code})")
            return response.content


def _extract_message_id(meta_response: dict) -> str:
    try:
        return meta_response["messages"][0]["id"]
    except (KeyError, IndexError):
        raise MetaAPIError("Meta API response missing expected message ID", response_body=str(meta_response))
