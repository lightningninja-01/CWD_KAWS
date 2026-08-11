"""
Session repository — the hot path for every inbound webhook: given
(tenant_id, customer_phone), find-or-create the session.
"""
from datetime import datetime, timezone
from pymongo import ReturnDocument

from app.database.repositories.base_repository import BaseRepository
from app.models.session import Session, SessionStatus


class SessionRepository(BaseRepository[Session]):
    collection_name = "sessions"
    model_cls = Session

    async def get_or_create(self, tenant_id: str, customer_phone: str) -> Session:
        """
        Compound-unique on (tenant_id, customer_phone) — see the index in
        connection.py. Reopens a RESOLVED session automatically rather than
        forcing a new session document per conversation gap, since the
        assignment models "session" as the ongoing relationship, not a
        single chat window.
        """
        session = Session(tenant_id=tenant_id, customer_phone=customer_phone)
        doc = await self._collection.find_one_and_update(
            {"tenant_id": tenant_id, "customer_phone": customer_phone},
            {"$setOnInsert": session.to_mongo()},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        result = self._to_model(doc)
        if result.status == SessionStatus.RESOLVED:
            await self.update_status(tenant_id, result.id, SessionStatus.WAITING_FOR_BOT)
            result.status = SessionStatus.WAITING_FOR_BOT
        return result

    async def update_status(self, tenant_id: str, session_id: str, status: SessionStatus) -> bool:
        return await self.update_scoped(
            tenant_id,
            session_id,
            {"status": status.value, "updated_at": datetime.now(timezone.utc)},
        )

    async def touch_last_message(self, tenant_id: str, session_id: str) -> bool:
        return await self.update_scoped(
            tenant_id,
            session_id,
            {"last_message_at": datetime.now(timezone.utc), "updated_at": datetime.now(timezone.utc)},
        )

    async def list_active_for_tenant(self, tenant_id: str) -> list[Session]:
        """Used by the dashboard's Live Chat List — most recently active first."""
        return await self.find_many_scoped(tenant_id, sort=[("last_message_at", -1)])
