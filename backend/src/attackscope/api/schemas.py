from typing import Any, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from attackscope.normalization.events import Category, Severity, SourceKind


class EventOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    schema_version: Literal[1]
    timestamp: AwareDatetime
    received_at: AwareDatetime
    host_id: UUID
    source: SourceKind
    event_type: str
    category: Category
    severity: Severity
    src_ip: str | None
    dst_ip: str | None
    src_port: int | None
    dst_port: int | None
    protocol: str | None
    classification: dict[str, Any] | None
    attributes: dict[str, Any]
    source_reference: str | None
    safe_original: dict[str, Any]


class Coverage(BaseModel):
    detail_available_from: AwareDatetime
    kind: Literal["detail"] = "detail"


class EventsPage(BaseModel):
    items: list[EventOut]
    next_cursor: str | None
    coverage: Coverage


class HostOut(BaseModel):
    id: UUID
    name: str
    created_at: AwareDatetime
    disabled: bool


class HostsPage(BaseModel):
    items: list[HostOut]
    next_cursor: UUID | None


class IngestionResult(BaseModel):
    accepted: int = Field(ge=0)
    duplicates: int = Field(ge=0)
    schema_version: Literal[1] = 1
