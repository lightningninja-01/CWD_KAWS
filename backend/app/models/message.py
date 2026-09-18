"""
Message document model — the audit log of every inbound/outbound message,
per assignment spec.
"""
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from bson import ObjectId
from pydantic import BaseModel, Field, field_validator


class MessageSender(StrEnum):
    CUSTOMER = "customer"
    BOT = "bot"
    HUMAN_AGENT = "human_agent"


class MessageType(StrEnum):
    TEXT = "text"
    IMAGE = "image"
    DOCUMENT = "document"
    EMAIL = "email"


class MessageStatus(StrEnum):
    PENDING_RESPONSE = "PENDING_RESPONSE"  # set by Acknowledge node on inbound save
    SENT = "SENT"
    DELIVERED = "DELIVERED"
    FAILED = "FAILED"


class MediaAttachment(BaseModel):
    url: str
    mime_type: str
    filename: str | None = None  # relevant for documents


class Message(BaseModel):
    id: str = Field(default_factory=lambda: str(ObjectId()), alias="_id")
    tenant_id: str
    session_id: str
    sender: MessageSender
    message_type: MessageType
    text: str | None = None
    media: MediaAttachment | None = None
    status: MessageStatus = MessageStatus.SENT
    metadata: dict[str, Any] = Field(default_factory=dict)  # e.g. sentiment_score, meta_message_id
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = {"populate_by_name": True, "arbitrary_types_allowed": True}

    @field_validator("id", mode="before")
    @classmethod
    def _stringify_object_id(cls, value: Any) -> str:
        return str(value) if isinstance(value, ObjectId) else value

    def to_mongo(self) -> dict[str, Any]:
        data = self.model_dump(by_alias=True, exclude={"id"})
        data["_id"] = ObjectId(self.id) if ObjectId.is_valid(self.id) else self.id
        return data
