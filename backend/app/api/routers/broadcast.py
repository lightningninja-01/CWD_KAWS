"""
Broadcast endpoint — triggered by the dashboard's Broadcast Campaign Drawer.
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from datetime import datetime, timedelta, timezone

from app.api.auth import AuthContext, authenticate
from app.database.repositories.job_repository import JobRepository
from app.config.settings import get_settings
from app.schemas.broadcast_schema import BroadcastJobResponse, BroadcastJobStatus, BroadcastRequest, BroadcastResult

router = APIRouter()


@router.post("", response_model=BroadcastJobResponse, status_code=202)
async def send_broadcast(
    payload: BroadcastRequest,
    request: Request,
    auth: AuthContext = Depends(authenticate),
) -> BroadcastJobResponse:
    auth.require_tenant(payload.tenant_id)
    jobs = JobRepository(request.app.state.db)
    settings = get_settings()
    recent = await jobs.recent_count("broadcast", payload.tenant_id, datetime.now(timezone.utc) - timedelta(minutes=1))
    if recent >= settings.broadcast_jobs_per_minute:
        raise HTTPException(status_code=429, detail="Broadcast rate limit exceeded; retry in one minute")
    job, created = await jobs.enqueue(
        "broadcast", payload.model_dump(), tenant_id=payload.tenant_id,
    )
    return BroadcastJobResponse(job_id=job["_id"], tenant_id=payload.tenant_id, status=job["status"], created=created)


@router.get("/{tenant_id}/{job_id}", response_model=BroadcastJobStatus)
async def get_broadcast_status(
    tenant_id: str, job_id: str, request: Request, auth: AuthContext = Depends(authenticate)
) -> BroadcastJobStatus:
    auth.require_tenant(tenant_id)
    job = await JobRepository(request.app.state.db).get_scoped(job_id, tenant_id)
    if job is None or job.get("type") != "broadcast":
        raise HTTPException(status_code=404, detail="Broadcast job not found")
    result = BroadcastResult.model_validate(job["result"]) if job.get("result") else None
    return BroadcastJobStatus(
        job_id=job["_id"], tenant_id=tenant_id, status=job["status"],
        attempts=job["attempts"], result=result, last_error=job.get("last_error"),
    )
