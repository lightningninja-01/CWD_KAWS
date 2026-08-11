"""
API contract schemas for tenant endpoints — decoupled from the Mongo
document model (models/tenant.py) so the API surface can evolve
independently of storage shape.
"""
from pydantic import BaseModel, Field


class BrandingSchema(BaseModel):
    display_name: str
    primary_color: str = "#4F46E5"
    logo_url: str | None = None


class TenantCreateRequest(BaseModel):
    company_name: str
    phone_number_id: str
    system_prompt: str
    media_library: dict[str, str] = Field(default_factory=dict)
    branding: BrandingSchema


class TenantResponse(BaseModel):
    id: str
    company_name: str
    phone_number_id: str
    system_prompt: str
    media_library: dict[str, str]
    branding: BrandingSchema
