import mimetypes
import re
from pathlib import Path
from urllib.parse import urlparse

from bs4 import BeautifulSoup, Tag

from .common import parse_timestamp, stable_hash
from .normalized import NormalizedAttachment, NormalizedConversation, NormalizedMessage

GEMINI_ID_PATTERN = re.compile(r"/app/([^/?#]+)")
DATE_PATTERN = re.compile(
    r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},\s+\d{4},",
    re.IGNORECASE,
)


def _main_content(block: Tag) -> Tag | None:
    for cell in block.select("div.content-cell"):
        classes = set(cell.get("class") or [])
        if "mdl-typography--caption" not in classes and "mdl-typography--text-right" not in classes:
            return cell
    return None


def _split_activity(cell: Tag) -> tuple[str, str, object | None]:
    lines = [line.strip() for line in cell.get_text("\n").splitlines() if line.strip()]
    prompt_index = next((i for i, line in enumerate(lines) if line.lower().startswith("prompted")), 0)
    date_index = next((i for i, line in enumerate(lines) if DATE_PATTERN.search(line)), None)
    if date_index is None:
        prompt = lines[prompt_index + 1] if len(lines) > prompt_index + 1 else ""
        answer = "\n".join(lines[prompt_index + 2 :])
        return prompt, answer, None
    prompt_lines = lines[prompt_index + 1 : date_index]
    prompt = "\n".join(prompt_lines).strip()
    answer = "\n".join(lines[date_index + 1 :]).strip()
    return prompt, answer, parse_timestamp(lines[date_index])


def _conversation_id(block: Tag) -> str | None:
    for anchor in block.select("a[href]"):
        match = GEMINI_ID_PATTERN.search(str(anchor.get("href")))
        if match:
            return match.group(1)
    return None


def _attachments(block: Tag, html_path: Path, source_root: Path) -> list[NormalizedAttachment]:
    results: list[NormalizedAttachment] = []
    seen: set[str] = set()
    for element, attribute in [*[(x, "src") for x in block.select("[src]")], *[(x, "href") for x in block.select("a[href]")]]:
        value = str(element.get(attribute) or "")
        parsed = urlparse(value)
        if not value or parsed.scheme or parsed.netloc or value.startswith("#"):
            continue
        path = (html_path.parent / parsed.path).resolve()
        try:
            relative = path.relative_to(source_root.resolve()).as_posix()
        except ValueError:
            continue
        if not path.is_file() or relative in seen:
            continue
        seen.add(relative)
        results.append(
            NormalizedAttachment(
                relative_path=relative,
                original_name=path.name,
                mime_type=mimetypes.guess_type(path.name)[0],
                size_bytes=path.stat().st_size,
            )
        )
    return results


def parse_gemini_file(path: Path, source_root: Path) -> list[NormalizedConversation]:
    soup = BeautifulSoup(path.read_text(encoding="utf-8-sig", errors="replace"), "html.parser")
    grouped: dict[str, list[tuple[str, str, object | None, list[NormalizedAttachment], int]]] = {}
    titles: dict[str, str] = {}
    known_provider_ids: set[str] = set()
    for index, block in enumerate(soup.select("div.outer-cell")):
        cell = _main_content(block)
        if cell is None:
            continue
        prompt, answer, timestamp = _split_activity(cell)
        if not prompt and not answer:
            continue
        provider_id = _conversation_id(block)
        identity = provider_id or stable_hash("gemini-activity", timestamp, prompt, answer)
        if provider_id:
            known_provider_ids.add(identity)
        grouped.setdefault(identity, []).append(
            (prompt, answer, timestamp, _attachments(block, path, source_root), index)
        )
        titles.setdefault(identity, (prompt[:120] if prompt else "Gemini activity"))

    conversations: list[NormalizedConversation] = []
    for identity, activities in grouped.items():
        activities.sort(key=lambda item: (item[2] is None, item[2], item[4]))
        provider_id = identity if identity in known_provider_ids else None
        messages: list[NormalizedMessage] = []
        for activity_index, (prompt, answer, timestamp, attachments, _) in enumerate(activities):
            user_id = stable_hash(identity, timestamp, prompt, "user")
            assistant_id = stable_hash(identity, timestamp, answer, "assistant")
            if prompt:
                messages.append(
                    NormalizedMessage(
                        source_id=user_id,
                        parent_source_id=None if not messages else messages[-1].source_id,
                        role="user",
                        body=prompt,
                        created_at=timestamp,
                        sort_order=activity_index * 2,
                        raw_payload={"activity_index": activity_index},
                        attachments=attachments,
                    )
                )
            if answer:
                messages.append(
                    NormalizedMessage(
                        source_id=assistant_id,
                        parent_source_id=user_id if prompt else (messages[-1].source_id if messages else None),
                        role="assistant",
                        body=answer,
                        created_at=timestamp,
                        sort_order=activity_index * 2 + 1,
                        raw_payload={"activity_index": activity_index},
                    )
                )
        timestamps = [item[2] for item in activities if item[2] is not None]
        fingerprint = stable_hash("gemini", identity)
        conversations.append(
            NormalizedConversation(
                source_id=provider_id,
                fingerprint=fingerprint,
                title=titles[identity] or "Gemini activity",
                created_at=min(timestamps) if timestamps else None,
                updated_at=max(timestamps) if timestamps else None,
                current_node_source_id=messages[-1].source_id if messages else None,
                messages=messages,
                raw_payload={"source_html": path.name},
            )
        )
    return conversations
