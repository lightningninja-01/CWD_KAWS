"""Worker that executes leased Mongo jobs and safely retries failures."""
import asyncio
from contextlib import suppress

from app.config.settings import get_settings
from app.database.repositories.job_repository import JobRepository
from app.schemas.broadcast_schema import BroadcastRequest
from app.services.broadcast_service import BroadcastService
from app.utils.logger import get_logger

log = get_logger(__name__)


class JobWorker:
    def __init__(self, app, repo: JobRepository, broadcast_service: BroadcastService) -> None:
        self._app = app
        self._repo = repo
        self._broadcast_service = broadcast_service
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()

    def start(self) -> None:
        self._task = asyncio.create_task(self._run(), name="durable-job-worker")

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task

    async def _run(self) -> None:
        settings = get_settings()
        while not self._stop.is_set():
            job = await self._repo.claim_next(settings.job_lease_seconds)
            if job is None:
                await asyncio.sleep(settings.job_poll_interval_seconds)
                continue
            try:
                result = await self._execute(job)
                await self._repo.complete(job["_id"], result)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # top-level durable job boundary
                log.error(f"Job {job['_id']} ({job['type']}) failed: {exc!r}", exc_info=True)
                await self._repo.fail(job, repr(exc), settings.job_max_attempts)

    async def _execute(self, job: dict) -> dict:
        if job["type"] == "webhook_message":
            from app.api.routers.webhook import process_queued_message
            await process_queued_message(self._app, job["payload"])
            return {"processed": True}
        if job["type"] == "broadcast":
            result = await self._broadcast_service.send_broadcast(BroadcastRequest.model_validate(job["payload"]))
            return result.model_dump()
        raise ValueError(f"Unsupported job type: {job['type']}")
