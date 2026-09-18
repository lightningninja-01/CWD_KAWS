"""
Gmail Listener service (Phase 6A).
Polls Gmail for new messages, normalizes them, and queues them as jobs for the LangGraph agent.
Designed to be swapped for a Pub/Sub push webhook later (Phase 6B).
"""
import asyncio
from contextlib import suppress

from app.config.settings import get_settings
from app.database.repositories.integration_repository import IntegrationRepository
from app.database.repositories.job_repository import JobRepository
from app.services.google_oauth import GoogleOAuthService
from app.utils.logger import get_logger
import httpx
import base64

log = get_logger(__name__)

class GmailListener:
    def __init__(self, db, job_repo: JobRepository):
        self.db = db
        self._job_repo = job_repo
        self._integration_repo = IntegrationRepository(db)
        self._oauth = GoogleOAuthService()
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()

    def start(self) -> None:
        self._task = asyncio.create_task(self._run(), name="gmail-listener-worker")

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task

    async def _run(self) -> None:
        """Polls Gmail for active integrations."""
        settings = get_settings()
        while not self._stop.is_set():
            try:
                await self._poll_all_integrations()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                log.error(f"Gmail listener polling failed: {e}")
            
            # Poll every 60 seconds
            await asyncio.sleep(60)

    async def _poll_all_integrations(self) -> None:
        """Finds all active Google Integrations and polls their unread emails."""
        # Note: In a real system you might want a more sophisticated 'last_history_id' sync approach
        cursor = self._integration_repo._collection.find({"is_connected": True})
        async for doc in cursor:
            tenant_id = doc.get("tenant_id")
            user_id = doc.get("user_id")
            if not tenant_id or not user_id:
                continue
                
            try:
                await self._poll_user_gmail(tenant_id, user_id)
            except Exception as e:
                log.error(f"Failed to poll Gmail for tenant {tenant_id}, user {user_id}: {e}")

    async def _poll_user_gmail(self, tenant_id: str, user_id: str) -> None:
        integration = await self._integration_repo.get_by_user(tenant_id, user_id)
        if not integration:
            return
            
        access_token = await self._oauth.ensure_valid_token(integration, self._integration_repo)
        
        async with httpx.AsyncClient(timeout=10.0, headers={"Authorization": f"Bearer {access_token}"}) as client:
            # Query for unread messages sent after Sept 17, 2026 to avoid processing ancient emails
            url = "https://gmail.googleapis.com/gmail/v1/users/me/messages"
            resp = await client.get(url, params={"q": "is:unread after:2026/09/17", "maxResults": 10})
            if resp.status_code != 200:
                return
                
            messages = resp.json().get("messages", [])
            for msg_ref in messages:
                msg_id = msg_ref["id"]
                
                # Fetch full message
                msg_resp = await client.get(f"{url}/{msg_id}", params={"format": "full"})
                if msg_resp.status_code != 200:
                    continue
                    
                msg_data = msg_resp.json()
                
                # Normalize and queue job
                payload = self._normalize_to_webhook_payload(tenant_id, msg_data)
                
                # Insert job to be picked up by JobWorker (reuses WhatsApp's reliable processing)
                await self._job_repo.enqueue("webhook_message", payload, deduplication_key=f"gmail:{msg_id}")
                
                # Mark as read so we don't process it again
                await client.post(f"{url}/{msg_id}/modify", json={"removeLabelIds": ["UNREAD"]})
                log.info(f"Queued Gmail message {msg_id} for processing")

    def _normalize_to_webhook_payload(self, tenant_id: str, msg_data: dict) -> dict:
        """
        Translates a Gmail message into the shape our app expects from webhooks.
        Our graph's `IncomingMessage` supports `channel='gmail'`.
        """
        headers = {h["name"].lower(): h["value"] for h in msg_data.get("payload", {}).get("headers", [])}
        
        body = ""
        payload = msg_data.get("payload", {})
        if "parts" in payload:
            for part in payload["parts"]:
                if part.get("mimeType") == "text/plain" and "data" in part.get("body", {}):
                    body = base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", errors="replace")
                    break
        elif "body" in payload and "data" in payload["body"]:
            body = base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="replace")

        # Fake the Meta webhook shape for the dispatcher, OR map directly.
        # Since we use `app.api.routers.webhook.process_queued_message`, it expects the raw Meta shape currently.
        # Actually, it's cleaner to inject a direct shape if we modify `process_queued_message`.
        # For now, we wrap it in a custom payload type so the webhook router can distinguish it.
        return {
            "source": "gmail",
            "tenant_id": tenant_id,
            "message_id": msg_data["id"],
            "from_email": headers.get("from", "unknown"),
            "text": body,
            "thread_id": msg_data.get("threadId")
        }
