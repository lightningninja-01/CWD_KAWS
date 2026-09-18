"""
Google Integration model.
Stores user-level OAuth credentials securely.
"""
from datetime import datetime, timezone
from typing import Any

from bson import ObjectId
from pydantic import BaseModel, Field, field_validator


class GoogleIntegration(BaseModel):
    """
    Mongo document shape for the `google_integrations` collection.
    Associated with a tenant and a user (or generic 'demo' user).
    """

    id: str = Field(default_factory=lambda: str(ObjectId()), alias="_id")
    tenant_id: str
    user_id: str
    
    # OAuth Credentials
    access_token: str
    refresh_token: str | None = None
    token_expiry: datetime | None = None
    granted_scopes: list[str] = Field(default_factory=list)
    
    # Google Account Info
    google_email: str | None = None
    
    # Status
    is_connected: bool = True
    
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = {"populate_by_name": True, "arbitrary_types_allowed": True}

    @field_validator("id", mode="before")
    @classmethod
    def _stringify_object_id(cls, value: Any) -> str:
        return str(value) if isinstance(value, ObjectId) else value

    def to_mongo(self) -> dict[str, Any]:
        """Serialize for insertion, converting the string id back to ObjectId."""
        data = self.model_dump(by_alias=True, exclude={"id"})
        data["_id"] = ObjectId(self.id) if ObjectId.is_valid(self.id) else self.id
        return data
