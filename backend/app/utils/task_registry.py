"""
In-process asyncio task registry.

Used for two things that need explicit lifecycle control:
1. The typing indicator heartbeat (started in Acknowledge, must be
   cancelled the instant Dispatcher/Handover sends the real reply).
Webhook and broadcast work use the durable Mongo job queue; this registry is
intentionally limited to ephemeral typing indicators.
"""
import asyncio
from typing import Coroutine

from app.utils.logger import get_logger

log = get_logger(__name__)


class TaskRegistry:
    def __init__(self) -> None:
        self._tasks: dict[str, asyncio.Task] = {}

    def spawn(self, key: str, coro: Coroutine, *, on_error_log: str = "Background task failed") -> asyncio.Task:
        """
        Cancels any existing task under the same key before starting a new
        one — prevents leaking duplicate heartbeats if a node somehow
        starts twice for the same session.
        """
        self.cancel(key)

        async def _wrapped() -> None:
            try:
                await coro
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 — top-level task boundary, must not vanish silently
                log.error(f"{on_error_log}: {exc!r}", extra={"task_key": key})

        task = asyncio.create_task(_wrapped())
        self._tasks[key] = task
        return task

    def cancel(self, key: str) -> None:
        existing = self._tasks.pop(key, None)
        if existing is not None and not existing.done():
            existing.cancel()

    def is_running(self, key: str) -> bool:
        task = self._tasks.get(key)
        return task is not None and not task.done()


task_registry = TaskRegistry()
