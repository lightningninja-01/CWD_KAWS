from typing import Any
from datetime import datetime, timezone

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ReturnDocument

from app.models.integration import GoogleIntegration


class IntegrationRepository:
    """Repository for GoogleIntegration documents."""

    def __init__(self, db: AsyncIOMotorDatabase):
        self._collection = db.google_integrations

    async def get_by_user(self, tenant_id: str, user_id: str) -> GoogleIntegration | None:
        """Fetch the Google integration for a specific user within a tenant."""
        doc = await self._collection.find_one({"tenant_id": tenant_id, "user_id": user_id, "is_connected": True})
        if not doc:
            return None
        return GoogleIntegration.model_validate(doc)

    async def upsert(self, integration: GoogleIntegration) -> GoogleIntegration:
        """Insert or update a Google integration."""
        doc = integration.to_mongo()
        doc["updated_at"] = datetime.now(timezone.utc)
        
        _id = doc.pop("_id", None)
        update_op = {"$set": doc}
        if _id:
            update_op["$setOnInsert"] = {"_id": _id}
        
        updated_doc = await self._collection.find_one_and_update(
            {"tenant_id": integration.tenant_id, "user_id": integration.user_id},
            update_op,
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        return GoogleIntegration.model_validate(updated_doc)

    async def disconnect(self, tenant_id: str, user_id: str) -> bool:
        """Mark a Google integration as disconnected."""
        result = await self._collection.update_one(
            {"tenant_id": tenant_id, "user_id": user_id},
            {"$set": {"is_connected": False, "updated_at": datetime.now(timezone.utc)}}
        )
        return result.modified_count > 0
