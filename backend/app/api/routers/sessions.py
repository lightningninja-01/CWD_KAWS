"""
Session endpoints — powers the dashboard's Live Chat List, including the
NEEDS_HUMAN highlighting (frontend just checks `status` on each row).
"""
from fastapi import APIRouter, Depends

from app.api.auth import AuthContext, authenticate
from app.api.deps import get_session_repo
from app.database.repositories.session_repository import SessionRepository
from app.schemas.session_schema import SessionResponse

router = APIRouter()


@router.get("/{tenant_id}", response_model=list[SessionResponse])
async def list_sessions(
    tenant_id: str,
    repo: SessionRepository = Depends(get_session_repo),
    auth: AuthContext = Depends(authenticate),
) -> list[SessionResponse]:
    auth.require_tenant(tenant_id)
    sessions = await repo.list_active_for_tenant(tenant_id)
    return [SessionResponse(**s.model_dump()) for s in sessions]
