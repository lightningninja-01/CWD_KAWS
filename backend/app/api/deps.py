"""
Shared FastAPI dependencies.

Repositories are cheap (just wrap a Motor collection handle) so they're
instantiated per-request off the shared DB connection. Services that wrap
external clients (Gemini, httpx-based Meta client) are process-level
singletons, assembled once at startup and stored on app.state — see
main.py's lifespan handler.
"""
from fastapi import Depends, Request
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.database.connection import get_database
from app.database.repositories.customer_repository import CustomerRepository
from app.database.repositories.message_repository import MessageRepository
from app.database.repositories.session_repository import SessionRepository
from app.database.repositories.tenant_repository import TenantRepository
from app.services.broadcast_service import BroadcastService
from app.services.tenant_service import TenantService


def get_tenant_repo(db: AsyncIOMotorDatabase = Depends(get_database)) -> TenantRepository:
    return TenantRepository(db)


def get_session_repo(db: AsyncIOMotorDatabase = Depends(get_database)) -> SessionRepository:
    return SessionRepository(db)


def get_message_repo(db: AsyncIOMotorDatabase = Depends(get_database)) -> MessageRepository:
    return MessageRepository(db)


def get_customer_repo(db: AsyncIOMotorDatabase = Depends(get_database)) -> CustomerRepository:
    return CustomerRepository(db)


def get_tenant_service(tenant_repo: TenantRepository = Depends(get_tenant_repo)) -> TenantService:
    return TenantService(tenant_repo)


def get_broadcast_service(
    request: Request,
    customer_repo: CustomerRepository = Depends(get_customer_repo),
) -> BroadcastService:
    return BroadcastService(customer_repo, request.app.state.whatsapp_client, TenantRepository(request.app.state.db))


