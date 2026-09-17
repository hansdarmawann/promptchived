import re
import time
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import and_, or_, select, update
from sqlalchemy.orm import Session, selectinload

from ..db import get_session_factory
from ..importers import (
    NormalizedConversation,
    NormalizedMessage,
)
from ..importers.chatgpt import parse_chatgpt_file
from ..importers.gemini import parse_gemini_file
from ..importers.common import file_sha256, stable_hash
from ..models import (
    Attachment,
    Conversation,
    ImportFile,
    ImportJob,
    JobStatus,
    Message,
    MessageRevision,
    SearchChunk,
    Source,
)
from .embeddings import EmbeddingService, cheap_chunks

CHATGPT_FILE = re.compile(r"^conversations(?:-\d+)?(?: \(\d+\))?\.json$", re.I)
GEMINI_FILE = re.compile(r"^MyActivity(?: \(\d+\))?\.html$", re.I)


def discover_files(source: Source) -> list[Path]:
    root = Path(source.root_path).resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"Source folder not found: {root}")
    pattern = CHATGPT_FILE if source.provider == "chatgpt" else GEMINI_FILE
    files = [path for path in root.rglob("*") if path.is_file() and pattern.match(path.name)]
    return sorted(files, key=lambda path: (path.stat().st_mtime_ns, str(path).lower()))


def enqueue_scan(session: Session, source: Source) -> ImportJob:
    pending = session.scalar(
        select(ImportJob).where(
            ImportJob.source_id == source.id,
            ImportJob.status.in_([JobStatus.pending.value, JobStatus.running.value]),
        )
    )
    if pending:
        return pending
    job = ImportJob(source_id=source.id, status=JobStatus.pending.value)
    session.add(job)
    session.commit()
    session.refresh(job)
    return job


def claim_job(session: Session) -> ImportJob | None:
    stale_before = datetime.now(UTC) - timedelta(minutes=10)
    job = session.scalar(
        select(ImportJob)
        .where(
            or_(
                ImportJob.status == JobStatus.pending.value,
                and_(
                    ImportJob.status == JobStatus.running.value,
                    ImportJob.updated_at < stale_before,
                ),
            )
        )
        .order_by(ImportJob.created_at)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    if job:
        if job.status == JobStatus.running.value:
            job.files_processed = 0
            job.conversations_processed = 0
            job.messages_processed = 0
            job.error_count = 0
        job.status = JobStatus.running.value
        job.started_at = datetime.now(UTC)
        session.commit()
    return job


def _message_fingerprint(message: NormalizedMessage) -> str:
    return stable_hash(
        message.source_id or "", message.parent_source_id or "", message.role,
        message.created_at, message.body,
    )


def _find_conversation(
    session: Session, source_id: uuid.UUID, incoming: NormalizedConversation
) -> Conversation | None:
    clauses = [Conversation.fingerprint == incoming.fingerprint]
    if incoming.source_id:
        clauses.append(Conversation.provider_conversation_id == incoming.source_id)
    return session.scalar(
        select(Conversation).where(Conversation.source_id == source_id, or_(*clauses)).limit(1)
    )


def _upsert_message(
    session: Session,
    conversation: Conversation,
    incoming: NormalizedMessage,
    import_file: ImportFile,
) -> tuple[Message, bool]:
    fingerprint = _message_fingerprint(incoming)
    clauses = [Message.fingerprint == fingerprint]
    if incoming.source_id:
        clauses.append(Message.source_message_id == incoming.source_id)
    message = session.scalar(
        select(Message).where(Message.conversation_id == conversation.id, or_(*clauses)).limit(1)
    )
    changed = False
    if message is None:
        message = Message(
            conversation=conversation,
            source_file_id=import_file.id,
            source_message_id=incoming.source_id,
            parent_source_id=incoming.parent_source_id,
            fingerprint=fingerprint,
            role=incoming.role,
            content_type=incoming.content_type,
            body=incoming.body,
            source_created_at=incoming.created_at,
            sort_order=incoming.sort_order,
            is_current_path=incoming.is_current_path,
            raw_payload=incoming.raw_payload,
        )
        session.add(message)
        session.flush()
        changed = True
    else:
        if message.body != incoming.body:
            session.add(
                MessageRevision(message_id=message.id, body=message.body, raw_payload=message.raw_payload)
            )
            message.body = incoming.body
            message.fingerprint = fingerprint
            message.raw_payload = incoming.raw_payload
            changed = True
        message.source_file_id = import_file.id
        message.parent_source_id = incoming.parent_source_id
        message.sort_order = incoming.sort_order
        message.is_current_path = incoming.is_current_path

    existing_attachments = {item.fingerprint for item in message.attachments}
    for item in incoming.attachments:
        attachment_fingerprint = stable_hash(item.relative_path, item.original_name, item.size_bytes)
        if attachment_fingerprint in existing_attachments:
            continue
        message.attachments.append(
            Attachment(
                relative_path=item.relative_path,
                original_name=item.original_name,
                mime_type=item.mime_type,
                size_bytes=item.size_bytes,
                fingerprint=attachment_fingerprint,
            )
        )
    if changed:
        message.chunks.clear()
        # Flush orphan deletes before inserting positions 0..N again.
        session.flush()
        for position, (body, token_count) in enumerate(cheap_chunks(message.body)):
            message.chunks.append(
                SearchChunk(
                    position=position,
                    title=conversation.title,
                    body=body,
                    token_count=token_count,
                )
            )
    return message, changed


def upsert_conversation(
    session: Session,
    source: Source,
    import_file: ImportFile,
    incoming: NormalizedConversation,
) -> tuple[Conversation, int]:
    conversation = _find_conversation(session, source.id, incoming)
    if conversation is None:
        title_changed = False
        conversation = Conversation(
            source_id=source.id,
            provider_conversation_id=incoming.source_id,
            fingerprint=incoming.fingerprint,
            title=incoming.title,
            source_created_at=incoming.created_at,
            source_updated_at=incoming.updated_at,
            current_node_source_id=incoming.current_node_source_id,
            raw_payload=incoming.raw_payload,
        )
        session.add(conversation)
        session.flush()
    else:
        title_changed = False
        is_newer = (
            incoming.updated_at is None
            or conversation.source_updated_at is None
            or incoming.updated_at >= conversation.source_updated_at
        )
        if is_newer:
            title_changed = conversation.title != incoming.title
            conversation.title = incoming.title
            conversation.source_created_at = incoming.created_at or conversation.source_created_at
            conversation.source_updated_at = incoming.updated_at
            conversation.current_node_source_id = incoming.current_node_source_id
            conversation.raw_payload = incoming.raw_payload
        if incoming.source_id and not conversation.provider_conversation_id:
            conversation.provider_conversation_id = incoming.source_id

    changed = 0
    for incoming_message in incoming.messages:
        _, was_changed = _upsert_message(session, conversation, incoming_message, import_file)
        changed += int(was_changed)
    if title_changed:
        session.execute(
            update(SearchChunk)
            .where(
                SearchChunk.message_id.in_(
                    select(Message.id).where(Message.conversation_id == conversation.id)
                )
            )
            .values(title=incoming.title)
        )
    return conversation, changed


def _parse_file(source: Source, path: Path) -> list[NormalizedConversation]:
    root = Path(source.root_path).resolve()
    if source.provider == "chatgpt":
        return parse_chatgpt_file(path, root)
    if source.provider == "gemini":
        return parse_gemini_file(path, root)
    raise ValueError(f"Unsupported provider: {source.provider}")


def _import_path(session: Session, source: Source, path: Path) -> tuple[int, int, bool]:
    root = Path(source.root_path).resolve()
    relative_path = path.resolve().relative_to(root).as_posix()
    stat = path.stat()
    digest = file_sha256(path)
    record = session.scalar(
        select(ImportFile).where(
            ImportFile.source_id == source.id, ImportFile.relative_path == relative_path
        )
    )
    if record and record.sha256 == digest and record.status == "imported":
        return 0, 0, True
    if record is None:
        record = ImportFile(
            source_id=source.id,
            relative_path=relative_path,
            sha256=digest,
            size_bytes=stat.st_size,
            modified_ns=stat.st_mtime_ns,
        )
        session.add(record)
        session.flush()
    else:
        record.sha256 = digest
        record.size_bytes = stat.st_size
        record.modified_ns = stat.st_mtime_ns
        record.status = "pending"
        record.error = None

    conversations = _parse_file(source, path)
    message_count = 0
    for incoming in conversations:
        _, changed = upsert_conversation(session, source, record, incoming)
        message_count += changed
    record.status = "imported"
    record.imported_at = datetime.now(UTC)
    return len(conversations), message_count, False


def embed_pending(
    session: Session, limit: int | None = None, job_id: uuid.UUID | None = None
) -> tuple[int, str | None]:
    messages = list(
        session.scalars(
            select(Message)
            .join(SearchChunk)
            .options(selectinload(Message.chunks), selectinload(Message.conversation))
            .where(SearchChunk.embedding.is_(None))
            .order_by(Message.created_at)
            .distinct()
            .limit(limit or 100_000)
        ).unique()
    )
    if not messages:
        return 0, None
    try:
        service = EmbeddingService()
        settings = service.settings
        message_ids = []
        for message in messages:
            exact_chunks = service.tokenizer_chunks(message.body)
            message.chunks.clear()
            # The unique (message_id, position) constraint requires old rows
            # to be deleted before replacement chunks are inserted.
            session.flush()
            for position, (body, token_count) in enumerate(exact_chunks):
                message.chunks.append(
                    SearchChunk(
                        position=position,
                        title=message.conversation.title,
                        body=body,
                        token_count=token_count,
                    )
                )
            message_ids.append(message.id)
        session.flush()
        chunks = list(
            session.scalars(
                select(SearchChunk)
                .where(SearchChunk.message_id.in_(message_ids))
                .order_by(SearchChunk.message_id, SearchChunk.position)
            )
        )
        completed = 0
        for offset in range(0, len(chunks), settings.embedding_batch_size):
            batch = chunks[offset : offset + settings.embedding_batch_size]
            vectors = service.encode_passages([chunk.body for chunk in batch])
            for chunk, vector in zip(batch, vectors, strict=True):
                chunk.embedding = vector
                chunk.embedding_model = settings.embedding_model
                chunk.embedding_error = None
                completed += 1
            if job_id:
                heartbeat_job = session.get(ImportJob, job_id)
                if heartbeat_job:
                    heartbeat_job.updated_at = datetime.now(UTC)
            session.commit()
        return completed, None
    except Exception as exc:  # The text import remains usable if model setup fails.
        session.rollback()
        return 0, f"Embedding did not finish: {exc}"


def _record_file_failure(session: Session, source: Source, path: Path, error: str) -> None:
    root = Path(source.root_path).resolve()
    try:
        relative_path = path.resolve().relative_to(root).as_posix()
        stat = path.stat()
        digest = file_sha256(path)
    except OSError:
        return
    record = session.scalar(
        select(ImportFile).where(
            ImportFile.source_id == source.id, ImportFile.relative_path == relative_path
        )
    )
    if record is None:
        record = ImportFile(
            source_id=source.id,
            relative_path=relative_path,
            sha256=digest,
            size_bytes=stat.st_size,
            modified_ns=stat.st_mtime_ns,
        )
        session.add(record)
    record.status = "failed"
    record.error = error


def process_job(job_id: uuid.UUID) -> None:
    session_factory = get_session_factory()
    with session_factory() as session:
        job = session.get(ImportJob, job_id)
        if job is None:
            return
        source = session.get(Source, job.source_id)
        if source is None:
            job.status = JobStatus.failed.value
            job.last_error = "Source not found"
            session.commit()
            return
        try:
            files = discover_files(source)
            job.files_total = len(files)
            session.commit()
        except Exception as exc:
            job.status = JobStatus.failed.value
            job.last_error = str(exc)
            job.finished_at = datetime.now(UTC)
            session.commit()
            return

        for path in files:
            try:
                conversations, messages, _ = _import_path(session, source, path)
                job.files_processed += 1
                job.conversations_processed += conversations
                job.messages_processed += messages
                job.checkpoint = {"last_file": str(path)}
                session.commit()
            except Exception as exc:
                session.rollback()
                job = session.get(ImportJob, job_id)
                source = session.get(Source, job.source_id)
                _record_file_failure(session, source, path, str(exc))
                job.files_processed += 1
                job.error_count += 1
                job.last_error = f"{path.name}: {exc}"
                job.checkpoint = {"last_file": str(path)}
                session.commit()

        _, embedding_error = embed_pending(session, job_id=job_id)
        job = session.get(ImportJob, job_id)
        if embedding_error:
            job.error_count += 1
            job.last_error = embedding_error
        job.status = (
            JobStatus.partial.value if job.error_count else JobStatus.succeeded.value
        )
        job.finished_at = datetime.now(UTC)
        session.commit()


def run_worker(once: bool = False, poll_seconds: float = 2.0) -> None:
    session_factory = get_session_factory()
    while True:
        with session_factory() as session:
            job = claim_job(session)
            job_id = job.id if job else None
        if job_id:
            process_job(job_id)
        elif once:
            return
        else:
            time.sleep(poll_seconds)
