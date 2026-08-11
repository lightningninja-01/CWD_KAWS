from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.database import connection as connection_module


class FakeCollection:
    async def create_index(self, *args, **kwargs):
        return None

    async def index_information(self):
        return {}


class FakeDatabase:
    def __init__(self):
        self.tenants = FakeCollection()
        self.sessions = FakeCollection()
        self.messages = FakeCollection()
        self.customers = FakeCollection()


class FakeMongoMockClient:
    def __init__(self):
        self.admin = SimpleNamespace(command=AsyncMock())
        self._db = FakeDatabase()

    def __getitem__(self, name):
        return self._db

    def close(self):
        return None


@pytest.mark.asyncio
async def test_connect_with_mock_client(monkeypatch):
    monkeypatch.setattr(connection_module, "AsyncIOMotorClient", lambda *_args, **_kwargs: FakeMongoMockClient())

    mongo_connection = connection_module.MongoConnection()
    await mongo_connection.connect()

    assert mongo_connection.db is not None
    assert mongo_connection._client is not None
