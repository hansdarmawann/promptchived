import uuid
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.orm import Session

from ..config import get_settings
from .embeddings import EmbeddingService


BASE_FILTERS = """
  (CAST(:source_id AS uuid) IS NULL OR s.id = CAST(:source_id AS uuid))
  AND (CAST(:provider AS text) IS NULL OR s.provider = CAST(:provider AS text))
  AND (CAST(:role AS text) IS NULL OR m.role = CAST(:role AS text))
  AND (CAST(:date_from AS timestamptz) IS NULL OR m.source_created_at >= CAST(:date_from AS timestamptz))
  AND (CAST(:date_to AS timestamptz) IS NULL OR m.source_created_at < CAST(:date_to AS timestamptz))
"""


def _params(
    query: str,
    source_id: uuid.UUID | None,
    provider: str | None,
    role: str | None,
    date_from: datetime | None,
    date_to: datetime | None,
) -> dict:
    return {
        "query": query,
        "source_id": str(source_id) if source_id else None,
        "provider": provider,
        "role": role,
        "date_from": date_from.isoformat() if date_from else None,
        "date_to": date_to.isoformat() if date_to else None,
    }


def fulltext_candidates(session: Session, parameters: dict, limit: int) -> list[dict]:
    rows = session.execute(
        text(
            f"""
            WITH q AS (SELECT websearch_to_tsquery('pg_catalog.simple', :query) value)
            SELECT sc.id chunk_id, m.id message_id, c.id conversation_id,
                   c.title conversation_title, s.name source_name, s.provider, m.role,
                   m.source_created_at created_at, m.is_current_path,
                   ts_headline('pg_catalog.simple', sc.body, q.value,
                     'StartSel=<mark>, StopSel=</mark>, MaxFragments=2, MaxWords=35, MinWords=12') snippet,
                   ts_rank_cd(sc.search_vector, q.value, 32) score
            FROM search_chunks sc
            JOIN messages m ON m.id = sc.message_id
            JOIN conversations c ON c.id = m.conversation_id
            JOIN sources s ON s.id = c.source_id
            CROSS JOIN q
            WHERE sc.search_vector @@ q.value AND {BASE_FILTERS}
            ORDER BY score DESC
            LIMIT :limit
            """
        ),
        {**parameters, "limit": limit},
    ).mappings()
    return [dict(row) for row in rows]


def semantic_candidates(
    session: Session, parameters: dict, vector: list[float], limit: int
) -> list[dict]:
    rows = session.execute(
        text(
            f"""
            SELECT sc.id chunk_id, m.id message_id, c.id conversation_id,
                   c.title conversation_title, s.name source_name, s.provider, m.role,
                   m.source_created_at created_at, m.is_current_path,
                   left(sc.body, 420) snippet,
                   1 - (sc.embedding <=> CAST(:embedding AS vector)) score
            FROM search_chunks sc
            JOIN messages m ON m.id = sc.message_id
            JOIN conversations c ON c.id = m.conversation_id
            JOIN sources s ON s.id = c.source_id
            WHERE sc.embedding IS NOT NULL AND {BASE_FILTERS}
            ORDER BY sc.embedding <=> CAST(:embedding AS vector)
            LIMIT :limit
            """
        ),
        {**parameters, "embedding": str(vector), "limit": limit},
    ).mappings()
    return [dict(row) for row in rows]


def _collapse(rows: list[dict]) -> list[dict]:
    by_message: dict[object, dict] = {}
    for row in rows:
        existing = by_message.get(row["message_id"])
        if existing is None or row["score"] > existing["score"]:
            by_message[row["message_id"]] = row
    return sorted(by_message.values(), key=lambda item: item["score"], reverse=True)


def _rrf(fulltext: list[dict], semantic: list[dict], k: int) -> list[dict]:
    combined: dict[object, dict] = {}
    for ranking in (fulltext, semantic):
        seen_messages: set[object] = set()
        rank = 0
        for row in ranking:
            message_id = row["message_id"]
            if message_id in seen_messages:
                continue
            seen_messages.add(message_id)
            rank += 1
            if message_id not in combined:
                combined[message_id] = {**row, "score": 0.0}
            combined[message_id]["score"] += 1.0 / (k + rank)
    return sorted(combined.values(), key=lambda item: item["score"], reverse=True)


def embedding_coverage(session: Session) -> float:
    row = session.execute(
        text(
            "SELECT count(*) total, count(embedding) embedded FROM search_chunks"
        )
    ).mappings().one()
    return 1.0 if not row["total"] else row["embedded"] / row["total"]


def search(
    session: Session,
    query: str,
    mode: str = "hybrid",
    source_id: uuid.UUID | None = None,
    provider: str | None = None,
    role: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    page: int = 1,
    per_page: int = 20,
) -> dict:
    settings = get_settings()
    parameters = _params(query, source_id, provider, role, date_from, date_to)
    coverage = embedding_coverage(session)
    lexical: list[dict] = []
    semantic: list[dict] = []
    notice = None
    if mode in {"fulltext", "hybrid"}:
        lexical = fulltext_candidates(session, parameters, settings.search_candidates)
    if mode in {"semantic", "hybrid"}:
        if coverage > 0:
            vector = EmbeddingService().encode_query(query)
            semantic = semantic_candidates(session, parameters, vector, settings.search_candidates)
        else:
            notice = "Embeddings are unavailable; keyword results are shown."

    if mode == "fulltext" or (mode == "hybrid" and not semantic):
        ranked = _collapse(lexical)
    elif mode == "semantic":
        ranked = _collapse(semantic)
    else:
        ranked = _rrf(lexical, semantic, settings.rrf_k)
    start = (page - 1) * per_page
    return {
        "items": ranked[start : start + per_page],
        "page": page,
        "per_page": per_page,
        "mode": mode,
        "embedding_coverage": coverage,
        "notice": notice,
    }
