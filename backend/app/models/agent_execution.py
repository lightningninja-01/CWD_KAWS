"""
Agent Execution models for safe telemetry logging (without hidden CoT).
"""
from datetime import datetime, timezone
from typing import Any

from bson import ObjectId
from pydantic import BaseModel, Field, field_validator


class ToolExecutionLog(BaseModel):
    tool_name: str
    execution_status: str
    safe_input_metadata: dict[str, Any] = Field(default_factory=dict)
    result_summary: str | None = None
    error_information: str | None = None
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AgentExecution(BaseModel):
    id: str = Field(default_factory=lambda: str(ObjectId()), alias="_id")
    execution_id: str = Field(default_factory=lambda: str(ObjectId()))
    tenant_id: str
    user_id: str | None = None
    channel: str = "whatsapp"
    input_summary: str | None = None
    intent: str | None = None
    status: str = "processing"
    tools_used: list[ToolExecutionLog] = Field(default_factory=list)
    final_result_summary: str | None = None
    
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = {"populate_by_name": True, "arbitrary_types_allowed": True}

    @field_validator("id", mode="before")
    @classmethod
    def _stringify_object_id(cls, value: Any) -> str:
        return str(value) if isinstance(value, ObjectId) else value

    def to_mongo(self) -> dict[str, Any]:
        data = self.model_dump(by_alias=True, exclude={"id"})
        data["_id"] = ObjectId(self.id) if ObjectId.is_valid(self.id) else self.id
        return data
