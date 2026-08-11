import pytest
from mongomock_motor import AsyncMongoMockClient

from app.database.repositories.job_repository import JobRepository


@pytest.fixture
def repo():
    db = AsyncMongoMockClient()["jobs_test"]
    return JobRepository(db), db


@pytest.mark.asyncio
async def test_enqueue_is_idempotent_by_deduplication_key(repo):
    jobs, db = repo
    await db.jobs.create_index("deduplication_key", unique=True, sparse=True)
    first, created_first = await jobs.enqueue("webhook_message", {"x": 1}, deduplication_key="message:1")
    second, created_second = await jobs.enqueue("webhook_message", {"x": 2}, deduplication_key="message:1")
    assert created_first is True
    assert created_second is False
    assert first["_id"] == second["_id"]


@pytest.mark.asyncio
async def test_claim_and_complete_job(repo):
    jobs, _ = repo
    queued, _ = await jobs.enqueue("broadcast", {"tenant_id": "t1"}, tenant_id="t1")
    claimed = await jobs.claim_next(60)
    assert claimed["_id"] == queued["_id"]
    assert claimed["status"] == "running"
    assert claimed["attempts"] == 1
    await jobs.complete(claimed["_id"], {"total_sent": 1})
    completed = await jobs.get_scoped(claimed["_id"], "t1")
    assert completed["status"] == "completed"
    assert completed["result"]["total_sent"] == 1


@pytest.mark.asyncio
async def test_failure_requeues_then_becomes_terminal(repo):
    jobs, _ = repo
    queued, _ = await jobs.enqueue("broadcast", {}, tenant_id="t1")
    queued["attempts"] = 1
    await jobs.fail(queued, "temporary", max_attempts=2)
    retry = await jobs.get_scoped(queued["_id"], "t1")
    assert retry["status"] == "queued"
    retry["attempts"] = 2
    await jobs.fail(retry, "permanent", max_attempts=2)
    failed = await jobs.get_scoped(queued["_id"], "t1")
    assert failed["status"] == "failed"
