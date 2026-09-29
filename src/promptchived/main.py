import uuid
from datetime import datetime
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, Form, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from .config import get_settings
from .db import get_db
from .i18n import SUPPORTED_LANGUAGES, language_from_request, translator
from .models import Attachment, Conversation, ImportJob, Message, Source
from .schemas import (
    ConversationRead,
    ConversationSummary,
    JobRead,
    SearchResponse,
    SourceCreate,
    SourceRead,
)
from .services.attachments import UnsafeAttachmentPath, resolve_attachment
from .services.import_jobs import enqueue_scan
from .services.rendering import format_datetime, render_highlight, render_markdown
from .services.search import search

PACKAGE_DIR = Path(__file__).parent
app = FastAPI(title="Promptchived", version="0.1.0")
app.mount("/static", StaticFiles(directory=PACKAGE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=PACKAGE_DIR / "templates")
templates.env.filters["markdown"] = render_markdown
templates.env.filters["highlight"] = render_highlight
templates.env.filters["localtime"] = format_datetime


def render_template(request: Request, name: str, context: dict | None = None):
    language = language_from_request(request)
    return templates.TemplateResponse(
        request=request,
        name=name,
        context={**(context or {}), "lang": language, "t": translator(language)},
    )


def optional_choice(value: str | None, choices: set[str], field: str) -> str | None:
    value = value or None
    if value is not None and value not in choices:
        raise HTTPException(422, f"Invalid {field}")
    return value


def source_browser_roots() -> list[Path]:
    """Return existing folders explicitly allowed in the local folder picker."""
    roots: list[Path] = []
    for value in get_settings().source_browser_roots.split(";"):
        if not value.strip():
            continue
        root = Path(value.strip()).expanduser().resolve()
        if root.is_dir() and root not in roots:
            roots.append(root)
    return roots


def is_inside_browser_root(path: Path, roots: list[Path]) -> bool:
    return any(path == root or root in path.parents for root in roots)


def source_path_status(root_path: str) -> str:
    """A source may be registered while its external drive is disconnected."""
    try:
        return "available" if Path(root_path).is_dir() else "unavailable"
    except OSError:
        return "unavailable"


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/source-folders")
def list_source_folders(path: str | None = None) -> dict:
    """List configured local folders without exposing the rest of the filesystem."""
    roots = source_browser_roots()
    root_items = [{"name": root.name or str(root), "path": str(root)} for root in roots]
    if path is None:
        return {"roots": root_items, "path": None, "parent": None, "folders": []}

    current = Path(path).expanduser().resolve()
    if not is_inside_browser_root(current, roots):
        raise HTTPException(403, "Folder is outside the configured source locations")
    if not current.is_dir():
        raise HTTPException(404, "Folder not found")

    try:
        folders = sorted(
            (
                {"name": item.name, "path": str(item.resolve())}
                for item in current.iterdir()
                if item.is_dir() and is_inside_browser_root(item.resolve(), roots)
            ),
            key=lambda item: item["name"].lower(),
        )
    except OSError as exc:
        raise HTTPException(403, "Folder cannot be read") from exc

    parent = str(current.parent) if current not in roots else None
    return {"roots": root_items, "path": str(current), "parent": parent, "folders": folders}


@app.get("/", response_class=HTMLResponse)
def home(request: Request, db: Session = Depends(get_db)):
    sources = list(db.scalars(select(Source).order_by(Source.name)))
    recent_jobs = list(db.scalars(select(ImportJob).order_by(ImportJob.created_at.desc()).limit(10)))
    statuses = {source.id: source_path_status(source.root_path) for source in sources}
    return render_template(
        request,
        "index.html",
        {"sources": sources, "jobs": recent_jobs, "source_statuses": statuses},
    )


@app.post("/language")
def set_language(language: str = Form(...), next_url: str = Form("/")):
    if language not in SUPPORTED_LANGUAGES:
        raise HTTPException(422, "Unsupported language")
    if not next_url.startswith("/") or next_url.startswith("//"):
        next_url = "/"
    response = RedirectResponse(next_url, status_code=303)
    response.set_cookie(
        "promptchived_language", language, max_age=31_536_000, samesite="lax"
    )
    return response


@app.post("/sources")
def create_source_form(
    name: str = Form(...),
    provider: Literal["chatgpt", "gemini"] = Form(...),
    root_path: str = Form(...),
    db: Session = Depends(get_db),
):
    create_source(SourceCreate(name=name, provider=provider, root_path=root_path), db)
    return RedirectResponse("/", status_code=303)


@app.post("/sources/{source_id}/scan")
def scan_source_form(source_id: uuid.UUID, db: Session = Depends(get_db)):
    source = db.get(Source, source_id)
    if not source:
        raise HTTPException(404, "Source not found")
    enqueue_scan(db, source)
    return RedirectResponse("/", status_code=303)


@app.get("/conversations", response_class=HTMLResponse)
def conversations_page(
    request: Request,
    page: int = Query(1, ge=1),
    source_id: uuid.UUID | None = None,
    db: Session = Depends(get_db),
):
    per_page = 30
    query = select(Conversation).order_by(
        Conversation.source_updated_at.desc().nullslast(), Conversation.created_at.desc()
    )
    if source_id:
        query = query.where(Conversation.source_id == source_id)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    items = list(db.scalars(query.offset((page - 1) * per_page).limit(per_page)))
    return render_template(
        request,
        "conversations.html",
        {"items": items, "page": page, "pages": max(1, (total + per_page - 1) // per_page)},
    )


@app.get("/conversations/{conversation_id}", response_class=HTMLResponse)
def conversation_page(
    conversation_id: uuid.UUID,
    request: Request,
    branches: bool = False,
    focus: uuid.UUID | None = None,
    db: Session = Depends(get_db),
):
    conversation = db.scalar(
        select(Conversation)
        .options(selectinload(Conversation.messages).selectinload(Message.attachments), selectinload(Conversation.source))
        .where(Conversation.id == conversation_id)
    )
    if not conversation:
        raise HTTPException(404, "Conversation not found")
    messages = conversation.messages if branches else [m for m in conversation.messages if m.is_current_path]
    return render_template(
        request,
        "conversation.html",
        {"conversation": conversation, "messages": messages, "branches": branches, "focus": focus},
    )


@app.get("/search", response_class=HTMLResponse)
def search_page(
    request: Request,
    q: str = "",
    mode: Literal["fulltext", "semantic", "hybrid"] = "hybrid",
    provider: str | None = None,
    role: str | None = None,
    page: int = Query(1, ge=1),
    db: Session = Depends(get_db),
):
    provider = optional_choice(provider, {"chatgpt", "gemini"}, "provider")
    role = optional_choice(role, {"user", "assistant", "system", "tool"}, "role")
    result = search(db, q, mode=mode, provider=provider, role=role, page=page) if q.strip() else None
    return render_template(
        request,
        "search.html",
        {"result": result, "q": q, "mode": mode, "provider": provider, "role": role},
    )


@app.post("/api/sources", response_model=SourceRead, status_code=201)
def create_source(payload: SourceCreate, db: Session = Depends(get_db)):
    root = Path(payload.root_path).expanduser().resolve()
    if not root.is_dir():
        raise HTTPException(422, "Source folder not found")
    existing = db.scalar(select(Source).where(Source.root_path == str(root)))
    if existing:
        raise HTTPException(409, "This folder is already registered")
    source = Source(name=payload.name, provider=payload.provider, root_path=str(root))
    db.add(source)
    db.commit()
    db.refresh(source)
    return source


@app.post("/api/sources/{source_id}/scan", response_model=JobRead, status_code=202)
def scan_source(source_id: uuid.UUID, db: Session = Depends(get_db)):
    source = db.get(Source, source_id)
    if not source:
        raise HTTPException(404, "Source not found")
    return enqueue_scan(db, source)


@app.get("/api/imports/{job_id}", response_model=JobRead)
def get_import(job_id: uuid.UUID, db: Session = Depends(get_db)):
    job = db.get(ImportJob, job_id)
    if not job:
        raise HTTPException(404, "Import job not found")
    return job


@app.get("/api/conversations")
def list_conversations(
    page: int = Query(1, ge=1),
    per_page: int = Query(30, ge=1, le=100),
    source_id: uuid.UUID | None = None,
    db: Session = Depends(get_db),
):
    query = select(Conversation)
    if source_id:
        query = query.where(Conversation.source_id == source_id)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    items = list(
        db.scalars(
            query.order_by(Conversation.source_updated_at.desc().nullslast())
            .offset((page - 1) * per_page)
            .limit(per_page)
        )
    )
    return {
        "items": [ConversationSummary.model_validate(item) for item in items],
        "page": page,
        "per_page": per_page,
        "total": total,
    }


@app.get("/api/conversations/{conversation_id}", response_model=ConversationRead)
def get_conversation(conversation_id: uuid.UUID, db: Session = Depends(get_db)):
    conversation = db.scalar(
        select(Conversation)
        .options(selectinload(Conversation.messages).selectinload(Message.attachments))
        .where(Conversation.id == conversation_id)
    )
    if not conversation:
        raise HTTPException(404, "Conversation not found")
    return conversation


@app.get("/api/search", response_model=SearchResponse)
def api_search(
    q: str = Query(min_length=1),
    mode: Literal["fulltext", "semantic", "hybrid"] = "hybrid",
    source_id: uuid.UUID | None = None,
    provider: str | None = None,
    role: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    provider = optional_choice(provider, {"chatgpt", "gemini"}, "provider")
    role = optional_choice(role, {"user", "assistant", "system", "tool"}, "role")
    return search(
        db, q, mode, source_id, provider, role, date_from, date_to, page, per_page
    )


@app.get("/api/attachments/{attachment_id}")
def get_attachment(
    attachment_id: uuid.UUID,
    download: bool = False,
    db: Session = Depends(get_db),
):
    attachment = db.scalar(
        select(Attachment)
        .options(
            selectinload(Attachment.message)
            .selectinload(Message.conversation)
            .selectinload(Conversation.source)
        )
        .where(Attachment.id == attachment_id)
    )
    if not attachment:
        raise HTTPException(404, "Attachment not found")
    try:
        path = resolve_attachment(
            attachment.message.conversation.source.root_path, attachment.relative_path
        )
    except (FileNotFoundError, UnsafeAttachmentPath):
        raise HTTPException(404, "Attachment file is unavailable") from None
    return FileResponse(
        path,
        media_type=attachment.mime_type or "application/octet-stream",
        filename=attachment.original_name if download else None,
        content_disposition_type="attachment" if download else "inline",
    )
