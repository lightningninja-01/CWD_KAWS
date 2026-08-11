"""
WhatsApp webhook router — the most latency-critical endpoint in the system.

POST /api/webhooks/whatsapp MUST return HTTP 200 within 3 seconds or Meta
will consider delivery failed and retry, causing duplicate processing.
To guarantee this regardless of DB or LLM latency, the handler does the
absolute minimum synchronously (signature verification + payload parsing)
and durably enqueues everything else — tenant lookup, session creation, and
the full LangGraph run — in MongoDB. The response is returned after the
durable write, without waiting for LLM work.
"""
from fastapi import APIRouter, Header, Query, Request, Response

from app.exceptions.custom_exceptions import InvalidWebhookSignatureError, TenantNotFoundError
from app.graph.state import ConversationState, IncomingMessage
from app.schemas.webhook_payload import WebhookInboundMessage, WebhookPayload
from app.utils.logger import get_logger
from app.utils.signature_verification import verify_meta_signature
from app.database.repositories.job_repository import JobRepository
from app.config.settings import get_settings

router = APIRouter()
log = get_logger(__name__)


@router.get("/whatsapp")
async def verify_webhook(
    hub_mode: str = Query(alias="hub.mode"),
    hub_challenge: str = Query(alias="hub.challenge"),
    hub_verify_token: str = Query(alias="hub.verify_token"),
) -> Response:
    """
    Meta's webhook verification handshake — required once when configuring
    the webhook URL in the Meta App dashboard.
    """
    settings = get_settings()
    if hub_mode == "subscribe" and hub_verify_token == settings.meta_webhook_verify_token:
        log.info("Webhook verification succeeded")
        return Response(content=hub_challenge, media_type="text/plain", status_code=200)

    log.warning("Webhook verification failed — token mismatch")
    return Response(content="Verification failed", status_code=403)


@router.post("/whatsapp")
async def receive_webhook(
    request: Request,
    x_hub_signature_256: str | None = Header(default=None),
) -> Response:
    raw_body = await request.body()

    if not verify_meta_signature(raw_body, x_hub_signature_256):
        # Logged but we still return 200-shaped rejection info via exception
        # handler status code (401) — Meta doesn't retry on 4xx, only 5xx/timeout,
        # so this is safe and correctly signals "rejected, don't retry."
        raise InvalidWebhookSignatureError()

    payload = WebhookPayload.model_validate_json(raw_body)
    extracted = payload.extract_first_message()

    if extracted is None:
        # Status callback (delivery/read receipt) with no new message — ack and exit.
        return Response(status_code=200)

    inbound_message, phone_number_id = extracted

    # Persist before acknowledging Meta. The unique key makes webhook retries safe.
    jobs = JobRepository(request.app.state.db)
    await jobs.enqueue(
        "webhook_message",
        {"inbound": inbound_message.model_dump(by_alias=True), "phone_number_id": phone_number_id},
        deduplication_key=f"whatsapp:{inbound_message.id}",
    )

    return Response(status_code=200)


async def process_queued_message(app, payload: dict) -> None:
    """
    The actual conversation pipeline, run fully in the background — the
    webhook has already responded to Meta by the time this executes.
    """
    inbound = WebhookInboundMessage.model_validate(payload["inbound"])
    phone_number_id = payload["phone_number_id"]
    graph_deps = app.state.graph_deps
    compiled_graph = app.state.compiled_graph

    try:
        tenant = await graph_deps.tenant_repo.get_by_phone_number_id(phone_number_id)
    except TenantNotFoundError:
        log.error(f"No tenant configured for phone_number_id={phone_number_id} — dropping message")
        return

    session = await graph_deps.session_repo.get_or_create(tenant.id, inbound.from_)

    message_type = inbound.type if inbound.type in ("text", "image", "document") else "text"
    incoming_message = IncomingMessage(
        meta_message_id=inbound.id,
        from_phone=inbound.from_,
        message_type=message_type,
        text_body=inbound.text.body if inbound.text else None,
        media_id=(inbound.image or inbound.document).id if (inbound.image or inbound.document) else None,
        media_mime_type=(inbound.image or inbound.document).mime_type if (inbound.image or inbound.document) else None,
    )

    initial_state: ConversationState = {
        "tenant_id": tenant.id,
        "session_id": session.id,
        "customer_phone": inbound.from_,
        "phone_number_id": phone_number_id,
        "incoming_message": incoming_message,
    }

    log.info(
        f"Starting graph run for tenant={tenant.id} session={session.id} "
        f"message_type={message_type}"
    )
    await compiled_graph.ainvoke(initial_state)

