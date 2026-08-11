"""Mongo-backed durable queue with leases, retries, and deduplication."""
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError


class JobRepository:
    def __init__(self, db) -> None:
        self._collection = db["jobs"]

    async def enqueue(
        self, job_type: str, payload: dict[str, Any], *, tenant_id: str | None = None,
        deduplication_key: str | None = None,
    ) -> tuple[dict[str, Any], bool]:
        now = datetime.now(timezone.utc)
        doc = {
            "_id": str(uuid4()), "type": job_type, "tenant_id": tenant_id,
            "payload": payload, "status": "queued", "attempts": 0,
            "available_at": now, "created_at": now, "updated_at": now,
        }
        if deduplication_key:
            doc["deduplication_key"] = deduplication_key
        try:
            await self._collection.insert_one(doc)
            return doc, True
        except DuplicateKeyError:
            existing = await self._collection.find_one({"deduplication_key": deduplication_key})
            return existing, False

    async def claim_next(self, lease_seconds: int) -> dict[str, Any] | None:
        now = datetime.now(timezone.utc)
        return await self._collection.find_one_and_update(
            {
                "$or": [
                    {"status": "queued", "available_at": {"$lte": now}},
                    {"status": "running", "lease_until": {"$lte": now}},
                ]
            },
            {"$set": {"status": "running", "lease_until": now + timedelta(seconds=lease_seconds), "updated_at": now},
             "$inc": {"attempts": 1}},
            sort=[("available_at", 1), ("created_at", 1)],
            return_document=ReturnDocument.AFTER,
        )

    async def complete(self, job_id: str, result: dict[str, Any] | None = None) -> None:
        now = datetime.now(timezone.utc)
        await self._collection.update_one(
            {"_id": job_id},
            {"$set": {"status": "completed", "result": result or {}, "completed_at": now, "updated_at": now},
             "$unset": {"lease_until": ""}},
        )

    async def fail(self, job: dict[str, Any], error: str, max_attempts: int) -> None:
        now = datetime.now(timezone.utc)
        terminal = job["attempts"] >= max_attempts
        update: dict[str, Any] = {
            "status": "failed" if terminal else "queued",
            "last_error": error[:2000], "updated_at": now,
        }
        if terminal:
            update["failed_at"] = now
        else:
            update["available_at"] = now + timedelta(seconds=min(60, 2 ** job["attempts"]))
        await self._collection.update_one({"_id": job["_id"]}, {"$set": update, "$unset": {"lease_until": ""}})

    async def get_scoped(self, job_id: str, tenant_id: str | None = None) -> dict[str, Any] | None:
        query: dict[str, Any] = {"_id": job_id}
        if tenant_id is not None:
            query["tenant_id"] = tenant_id
        return await self._collection.find_one(query)

    async def queue_depth(self) -> int:
        return await self._collection.count_documents({"status": {"$in": ["queued", "running"]}})

    async def recent_count(self, job_type: str, tenant_id: str, since: datetime) -> int:
        return await self._collection.count_documents(
            {"type": job_type, "tenant_id": tenant_id, "created_at": {"$gte": since}}
        )
