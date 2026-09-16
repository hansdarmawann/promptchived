import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class SourceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    provider: Literal["chatgpt", "gemini"]
    root_path: str = Field(min_length=1)


class SourceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    provider: str
    root_path: str
    enabled: bool


class JobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    source_id: uuid.UUID
    status: str
    files_total: int
    files_processed: int
    conversations_processed: int
    messages_processed: int
    error_count: int
    last_error: str | None
    checkpoint: dict
    started_at: datetime | None
    finished_at: datetime | None


class AttachmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    original_name: str
    mime_type: str | None
    size_bytes: int | None


class MessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    source_message_id: str | None
    parent_source_id: str | None
    role: str
    content_type: str
    body: str
    source_created_at: datetime | None
    sort_order: int
    is_current_path: bool
    attachments: list[AttachmentRead]


class ConversationSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    title: str
    source_created_at: datetime | None
    source_updated_at: datetime | None
    provider_conversation_id: str | None
    source_id: uuid.UUID


class ConversationRead(ConversationSummary):
    current_node_source_id: str | None
    messages: list[MessageRead]


class Page(BaseModel):
    items: list
    page: int
    per_page: int
    total: int


class SearchResult(BaseModel):
    message_id: uuid.UUID
    conversation_id: uuid.UUID
    conversation_title: str
    source_name: str
    provider: str
    role: str
    created_at: datetime | None
    snippet: str
    score: float
    is_current_path: bool


class SearchResponse(BaseModel):
    items: list[SearchResult]
    page: int
    per_page: int
    mode: str
    embedding_coverage: float
    notice: str | None = None

