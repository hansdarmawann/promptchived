from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class NormalizedAttachment:
    relative_path: str
    original_name: str
    mime_type: str | None = None
    size_bytes: int | None = None


@dataclass(slots=True)
class NormalizedMessage:
    source_id: str | None
    parent_source_id: str | None
    role: str
    body: str
    created_at: datetime | None
    sort_order: int
    content_type: str = "text"
    is_current_path: bool = True
    raw_payload: dict[str, Any] = field(default_factory=dict)
    attachments: list[NormalizedAttachment] = field(default_factory=list)


@dataclass(slots=True)
class NormalizedConversation:
    source_id: str | None
    fingerprint: str
    title: str
    created_at: datetime | None
    updated_at: datetime | None
    current_node_source_id: str | None
    messages: list[NormalizedMessage]
    raw_payload: dict[str, Any] = field(default_factory=dict)

