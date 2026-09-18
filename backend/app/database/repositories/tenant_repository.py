"""
Tenant repository.

Deliberately does NOT extend BaseRepository — a Tenant document is not
itself scoped *by* a tenant_id (it defines one), so the tenant-scoping
pattern used everywhere else doesn't apply here. Keeping this separate
avoids a confusing "tenant scoped to itself" API.
"""
from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.exceptions.custom_exceptions import TenantNotFoundError
from app.models.tenant import Tenant


class TenantRepository:
    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self._collection = db["tenants"]

    def _to_model(self, doc: dict[str, Any] | None) -> Tenant | None:
        if doc is None:
            return None
        return Tenant.model_validate({**doc, "_id": str(doc["_id"])})

    async def get_by_id(self, tenant_id: str) -> Tenant:
        if ObjectId.is_valid(tenant_id):
            query = {"_id": ObjectId(tenant_id)}
        else:
            query = {"_id": tenant_id}
            
        doc = await self._collection.find_one(query)
        model = self._to_model(doc)
        if model is None:
            raise TenantNotFoundError(tenant_id)
        return model

    async def get_by_phone_number_id(self, phone_number_id: str) -> Tenant:
        """
        Used by the webhook handler to route an inbound Meta payload to the
        correct tenant — Meta's payload identifies the recipient by
        phone_number_id, not by our internal tenant_id.
        """
        doc = await self._collection.find_one({"phone_number_id": phone_number_id})
        model = self._to_model(doc)
        if model is None:
            raise TenantNotFoundError(phone_number_id)
        return model

    async def list_all(self) -> list[Tenant]:
        cursor = self._collection.find({})
        return [self._to_model(doc) for doc in await cursor.to_list(length=None)]

    async def insert(self, tenant: Tenant) -> Tenant:
        await self._collection.insert_one(tenant.to_mongo())
        return tenant
