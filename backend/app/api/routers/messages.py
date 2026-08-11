"""
Message endpoints — powers the dashboard's Conversation Window
(message bubbles, media previews, PDF badges).
"""
from fastapi import APIRouter, Depends

from app.api.auth import AuthContext, authenticate
from app.api.deps import get_message_repo
from app.database.repositories.message_repository import MessageRepository
from app.schemas.message_schema import MessageResponse

router = APIRouter()


@router.get("/{tenant_id}/{session_id}", response_model=list[MessageResponse])
async def list_messages(
    tenant_id: str,
    session_id: str,
    repo: MessageRepository = Depends(get_message_repo),
    auth: AuthContext = Depends(authenticate),
) -> list[MessageResponse]:
    auth.require_tenant(tenant_id)
    messages = await repo.list_for_session(tenant_id, session_id)
    return [MessageResponse(**m.model_dump()) for m in messages]
