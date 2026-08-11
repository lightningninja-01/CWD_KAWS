"""
FastAPI application factory.

Wires process-level singletons (Mongo connection, Meta client, LLM/vision
services, typing heartbeat, the compiled LangGraph) on app.state during
startup via the lifespan context manager — these are expensive-ish to
construct and hold external connections, so they're built once and reused
for the process lifetime, not per-request.
"""
from contextlib import asynccontextmanager
import time
from uuid import uuid4

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routers import broadcast, messages, sessions, tenants, webhook
from app.config.settings import get_settings
from app.database.connection import mongo_connection
from app.database.repositories.message_repository import MessageRepository
from app.database.repositories.customer_repository import CustomerRepository
from app.database.repositories.job_repository import JobRepository
from app.database.repositories.session_repository import SessionRepository
from app.database.repositories.tenant_repository import TenantRepository
from app.exceptions.handlers import register_exception_handlers
from app.graph.builder import build_conversation_graph
from app.graph.dependencies import GraphDependencies
from app.services.llm_service import LLMService
from app.services.broadcast_service import BroadcastService
from app.services.job_worker import JobWorker
from app.services.typing_heartbeat import TypingHeartbeatService
from app.services.vision_service import VisionService
from app.services.whatsapp_client import WhatsAppClient
from app.utils.logger import get_logger

log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()

    await mongo_connection.connect()

    # --- Process-level service singletons ---
    whatsapp_client = WhatsAppClient()
    llm_service = LLMService()
    vision_service = VisionService(whatsapp_client)
    typing_heartbeat = TypingHeartbeatService(whatsapp_client)

    app.state.whatsapp_client = whatsapp_client
    app.state.llm_service = llm_service
    app.state.vision_service = vision_service
    app.state.typing_heartbeat = typing_heartbeat
    app.state.db = mongo_connection.db

    # --- Graph, compiled once and reused for every conversation turn ---
    db = mongo_connection.db
    graph_deps = GraphDependencies(
        tenant_repo=TenantRepository(db),
        session_repo=SessionRepository(db),
        message_repo=MessageRepository(db),
        whatsapp_client=whatsapp_client,
        llm_service=llm_service,
        vision_service=vision_service,
        typing_heartbeat=typing_heartbeat,
    )
    app.state.graph_deps = graph_deps
    app.state.compiled_graph = build_conversation_graph(graph_deps)

    job_repo = JobRepository(db)
    job_worker = JobWorker(app, job_repo, BroadcastService(CustomerRepository(db), whatsapp_client, TenantRepository(db)))
    app.state.job_repo = job_repo
    app.state.job_worker = job_worker
    job_worker.start()

    log.info(f"{settings.app_name} started in '{settings.environment}' mode")
    yield

    await job_worker.stop()
    await mongo_connection.disconnect()
    log.info("Application shutdown complete")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_origin_regex=settings.cors_allowed_origin_regex,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_exception_handlers(app)

    @app.middleware("http")
    async def request_observability(request, call_next):
        request_id = request.headers.get("X-Request-ID", str(uuid4()))
        started = time.perf_counter()
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Response-Time-Ms"] = f"{(time.perf_counter() - started) * 1000:.2f}"
        return response

    app.include_router(webhook.router, prefix="/api/webhooks", tags=["webhook"])
    app.include_router(tenants.router, prefix="/api/tenants", tags=["tenants"])
    app.include_router(sessions.router, prefix="/api/sessions", tags=["sessions"])
    app.include_router(messages.router, prefix="/api/messages", tags=["messages"])
    app.include_router(broadcast.router, prefix="/api/broadcast", tags=["broadcast"])

    @app.get("/")
    async def root_redirect():
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url="/docs")

    @app.get("/health")
    async def health_check() -> dict:
        return {"status": "ok", "app": settings.app_name}

    @app.get("/ready")
    async def readiness_check():
        from fastapi.responses import JSONResponse
        try:
            await mongo_connection._client.admin.command("ping")
            worker_running = bool(app.state.job_worker._task and not app.state.job_worker._task.done())
            healthy = worker_running
            return JSONResponse(
                status_code=200 if healthy else 503,
                content={"status": "ready" if healthy else "not_ready", "database": "ok", "worker": "ok" if worker_running else "stopped"},
            )
        except Exception:
            return JSONResponse(status_code=503, content={"status": "not_ready", "database": "unavailable"})

    @app.get("/metrics")
    async def metrics():
        from fastapi.responses import PlainTextResponse
        depth = await app.state.job_repo.queue_depth()
        return PlainTextResponse(
            "# HELP whatsapp_jobs_active Queued and running durable jobs\n"
            "# TYPE whatsapp_jobs_active gauge\n"
            f"whatsapp_jobs_active {depth}\n",
            media_type="text/plain; version=0.0.4",
        )

    return app


app = create_app()
