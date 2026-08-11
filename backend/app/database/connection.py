"""
MongoDB connection lifecycle, using Motor (async driver).

A single AsyncIOMotorClient is created on app startup and reused for the
process lifetime (Motor manages its own connection pool internally — do
NOT create a new client per request, that defeats pooling entirely).

Falls back to mongomock_motor for local development if real MongoDB is unavailable.
"""
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.config.settings import get_settings
from app.utils.logger import get_logger

log = get_logger(__name__)


class MongoConnection:
    """
    Thin wrapper around the Motor client so we have one place to manage
    connect/disconnect and one place tests can mock/override.
    """

    def __init__(self) -> None:
        self._client: AsyncIOMotorClient | None = None
        self._db: AsyncIOMotorDatabase | None = None

    async def connect(self) -> None:
        settings = get_settings()
        try:
            self._client = AsyncIOMotorClient(settings.mongodb_uri)
            self._db = self._client[settings.mongodb_db_name]
            # Fail fast on startup if Atlas is unreachable, rather than on first request.
            await self._client.admin.command("ping")
            await self._ensure_indexes()
            log.info(f"Connected to MongoDB database '{settings.mongodb_db_name}'")
        except Exception as e:
            if settings.is_production or not settings.allow_in_memory_database:
                self._client = None
                self._db = None
                log.error(f"Failed to connect to MongoDB in production: {type(e).__name__}: {e}")
                raise
            log.warning(f"Failed to connect to MongoDB ({type(e).__name__}): {e}. Falling back to in-memory mock for development.")
            from mongomock_motor import AsyncMongoMockClient
            self._client = AsyncMongoMockClient()
            self._db = self._client[settings.mongodb_db_name]
            await self._ensure_indexes()
            log.info(f"Using in-memory mongomock database '{settings.mongodb_db_name}' for development")

    async def disconnect(self) -> None:
        if self._client is not None:
            self._client.close()
            log.info("MongoDB connection closed")

    @property
    def db(self) -> AsyncIOMotorDatabase:
        if self._db is None:
            raise RuntimeError("MongoDB connection not initialized — call connect() during app startup")
        return self._db

    async def _ensure_indexes(self) -> None:
        """
        Indexes that matter for this access pattern:
        - tenants: unique lookup by external tenant slug (used by webhook routing)
        - sessions: compound lookup by (tenant_id, customer_phone) — the hot path
          for every inbound message
        - messages: lookup by session_id ordered by timestamp — used by
          Context Retriever's "last 5 messages" query
        """
        await self._db.tenants.create_index("phone_number_id", unique=True)
        await self._db.sessions.create_index([("tenant_id", 1), ("customer_phone", 1)], unique=True)
        await self._db.messages.create_index([("session_id", 1), ("created_at", -1)])
        await self._db.messages.create_index(
            "metadata.meta_message_id",
            unique=True,
            partialFilterExpression={"metadata.meta_message_id": {"$type": "string"}},
            name="unique_meta_message_id",
        )
        await self._db.customers.create_index([("tenant_id", 1), ("phone_number", 1)], unique=True)
        await self._db.jobs.create_index("deduplication_key", unique=True, sparse=True)
        await self._db.jobs.create_index([("status", 1), ("available_at", 1), ("lease_until", 1)])


mongo_connection = MongoConnection()


def get_database() -> AsyncIOMotorDatabase:
    """FastAPI dependency: returns the active database handle."""
    return mongo_connection.db
