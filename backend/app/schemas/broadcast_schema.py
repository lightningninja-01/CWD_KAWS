"""
API contract schemas for the Broadcast Campaign Drawer.
"""
from pydantic import BaseModel, Field


class BroadcastRequest(BaseModel):
    tenant_id: str
    target_tags: list[str] = Field(..., min_length=1, max_length=100, description="Customer tags defining the cohort")
    template_name: str = Field(..., min_length=1, max_length=512, pattern=r"^[a-z0-9_]+$")
    template_params: list[str] = Field(default_factory=list, max_length=20, description="Positional template params")


class BroadcastResult(BaseModel):
    tenant_id: str
    total_targeted: int
    total_sent: int
    total_failed: int
    failed_numbers: list[str] = Field(default_factory=list)


class BroadcastJobResponse(BaseModel):
    job_id: str
    tenant_id: str
    status: str
    created: bool = True


class BroadcastJobStatus(BaseModel):
    job_id: str
    tenant_id: str
    status: str
    attempts: int
    result: BroadcastResult | None = None
    last_error: str | None = None
