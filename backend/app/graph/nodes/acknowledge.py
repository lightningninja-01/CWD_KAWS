"""
Acknowledge Node — the first thing that happens after a webhook is received.

Responsibilities (per assignment spec):
1. Save the inbound message to the DB with status=PENDING_RESPONSE.
2. Send the read receipt.
3. Turn the typing indicator ON and start the heartbeat that keeps it alive
   for the duration of LLM reasoning (WhatsApp's typing indicator expires
   after ~25s, so a single fire-and-forget call isn't enough).

This node must be fast and must not raise — it's on the critical path that
determines how quickly the customer sees the typing indicator, which is
the whole point of the UX requirement.
"""
from typing import Any

from app.graph.dependencies import GraphDependencies
from app.graph.state import ConversationState
from app.models.message import Message, MessageSender, MessageStatus, MessageType
from app.models.session import SessionStatus
from app.utils.logger import get_logger

log = get_logger(__name__)


def build_acknowledge_node(deps: GraphDependencies):
    async def acknowledge(state: ConversationState) -> dict[str, Any]:
        tenant_id = state["tenant_id"]
        session_id = state["session_id"]
        incoming = state["incoming_message"]
        phone_number_id = state.get("phone_number_id")
        node_log = get_logger(__name__, tenant_id=tenant_id, session_id=session_id)

        # Save inbound message first — the audit log must exist even if the
        # subsequent Meta API calls fail, so we never silently drop a
        # customer message from the record.
        inbound_doc = Message(
            tenant_id=tenant_id,
            session_id=session_id,
            sender=MessageSender.CUSTOMER,
            message_type=MessageType(incoming.message_type),
            text=incoming.text_body,
            status=MessageStatus.PENDING_RESPONSE,
            metadata={"meta_message_id": incoming.meta_message_id},
        )
        await deps.message_repo.insert(inbound_doc)
        await deps.session_repo.touch_last_message(tenant_id, session_id)
        # AGENT_RESPONDING is the signal the dashboard polls for to render the
        # "typing..." state, since we use polling instead of a WebSocket push —
        # this status change IS the typing indicator's visible representation.
        await deps.session_repo.update_status(tenant_id, session_id, SessionStatus.AGENT_RESPONDING)

        # Fire read receipt + typing ON. Failure here is logged but never
        # fatal — a missed typing indicator shouldn't block the reply.
        try:
            if incoming.channel == "whatsapp":
                await deps.whatsapp_client.mark_as_read(incoming.meta_message_id, phone_number_id=phone_number_id)
                await deps.typing_heartbeat.start(session_id, incoming.meta_message_id, phone_number_id)
        except Exception as exc:  # noqa: BLE001 — intentionally broad; this must never crash the graph
            node_log.warning(f"Read receipt / typing indicator failed (non-fatal): {exc!r}")

        node_log.info("Acknowledged inbound message", extra={"message_type": incoming.message_type})
        return {"inbound_message_doc_id": inbound_doc.id}

    return acknowledge



