from pydantic import BaseModel, Field
from datetime import datetime
from .constants import ClientType, GroupStatus, SearchStatus, ContactType


class GroupGenerate(BaseModel):
    client_type: str
    count: int = Field(50, ge=5, le=200)


class GroupGenerateResponse(BaseModel):
    client_type: str
    names: list[str]
    source: str = "gemini_generated"  # "gemini_generated" | "manual"


class GroupCreate(BaseModel):
    name: str
    client_type: str


class GroupUpdate(BaseModel):
    name: str | None = None
    client_type: str | None = None


class GroupOut(BaseModel):
    id: int
    name: str
    client_type: str
    source: str
    status: str
    total_clients: int = 0
    found_count: int = 0
    not_found_count: int = 0
    pending_count: int = 0
    created_at: datetime
    updated_at: datetime


class ClientCreate(BaseModel):
    name: str
    extra_data: dict | None = None


class ClientOut(BaseModel):
    id: int
    group_id: int
    name: str
    extra_data: dict | None = None
    search_status: str
    contact_count: int = 0
    created_at: datetime


class ContactResultOut(BaseModel):
    id: int
    client_id: int
    contact_type: str
    value: str
    source_url: str | None = None
    source_type: str | None = None
    confidence: float
    is_approved: bool
    is_selected: bool
    edited_value: str | None = None
    created_at: datetime


class ContactCreate(BaseModel):
    contact_type: str
    value: str
    source_url: str | None = None
    source_type: str | None = None
