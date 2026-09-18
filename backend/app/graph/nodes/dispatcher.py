"""
Dispatcher Node — the final node in the normal (non-handover) path.
Sends the AI's decided reply via the correct Meta API call, persists the
outbound message, stops the typing indicator, and updates session status.
"""
from typing import Any

from app.exceptions.custom_exceptions import MediaAssetNotFoundError
from app.graph.dependencies import GraphDependencies
from app.graph.state import ConversationState
from app.models.message import MediaAttachment, Message, MessageSender, MessageStatus, MessageType
from app.models.session import SessionStatus
from app.utils.logger import get_logger

log = get_logger(__name__)


def build_dispatcher_node(deps: GraphDependencies):
    async def dispatcher(state: ConversationState) -> dict[str, Any]:
        tenant_id = state["tenant_id"]
        session_id = state["session_id"]
        customer_phone = state["customer_phone"]
        phone_number_id = state.get("phone_number_id")
        decision = state["reply_decision"]
        node_log = get_logger(__name__, tenant_id=tenant_id, session_id=session_id)

        media_attachment: MediaAttachment | None = None
        meta_id: str | None = None
        success = True
        error_message: str | None = None

        try:
            channel = state.get("channel", "whatsapp")
            
            if channel == "gmail":
                # We are sending an email reply
                from app.services.tools.gmail_tools import gmail_reply_to_email
                # For the demo, the user is 'demo_user'
                user_id = "demo_user" if tenant_id == "demo_tenant" else tenant_id
                message_id = state["incoming_message"].meta_message_id
                
                res = await gmail_reply_to_email(
                    tenant_id=tenant_id,
                    user_id=user_id,
                    message_id=message_id,
                    body=decision.text_content
                )
                meta_id = res.get("message_id")
            
            else:
                # Standard WhatsApp dispatch
                if decision.reply_type == "text":
                    meta_id = await deps.whatsapp_client.send_text(customer_phone, decision.text_content, phone_number_id=phone_number_id)
    
                elif decision.reply_type == "image":
                    url = _resolve_media_url(state["media_library"], decision.media_asset_key, tenant_id)
                    meta_id = await deps.whatsapp_client.send_image(customer_phone, url, caption=decision.text_content, phone_number_id=phone_number_id)
                    media_attachment = MediaAttachment(url=url, mime_type="image/jpeg")
    
                elif decision.reply_type == "document":
                    url = _resolve_media_url(state["media_library"], decision.media_asset_key, tenant_id)
                    filename = decision.media_asset_key or "document.pdf"
                    meta_id = await deps.whatsapp_client.send_document(
                        customer_phone, url, filename=filename, caption=decision.text_content, phone_number_id=phone_number_id
                    )
                    media_attachment = MediaAttachment(url=url, mime_type="application/pdf", filename=filename)

        except Exception as exc:  # noqa: BLE001 — must not crash; record failure and move on
            node_log.error(f"Dispatch failed: {exc!r}")
            success, error_message = False, str(exc)

        outbound_doc = Message(
            tenant_id=tenant_id,
            session_id=session_id,
            sender=MessageSender.BOT,
            message_type=MessageType(decision.reply_type),
            text=decision.text_content,
            media=media_attachment,
            status=MessageStatus.SENT if success else MessageStatus.FAILED,
            metadata={
                "meta_message_id": meta_id,
                "sentiment_score": decision.sentiment_score,
                "reasoning": decision.reasoning,
            },
        )
        await deps.message_repo.insert(outbound_doc)
        await deps.session_repo.update_status(tenant_id, session_id, SessionStatus.WAITING_FOR_BOT)
        await deps.typing_heartbeat.stop(session_id)

        node_log.info(f"Dispatched {decision.reply_type} reply", extra={"success": success})
        return {"dispatch_result": {"success": success, "meta_message_id": meta_id, "error_message": error_message}}

    return dispatcher


def _resolve_media_url(media_library: dict[str, str], asset_key: str | None, tenant_id: str) -> str:
    if not asset_key or asset_key not in media_library:
        raise MediaAssetNotFoundError(asset_key or "<none>", tenant_id)
    return media_library[asset_key]


