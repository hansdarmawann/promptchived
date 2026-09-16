import json
import mimetypes
from pathlib import Path
from typing import Any

from .common import json_safe, parse_timestamp, stable_hash
from .normalized import NormalizedAttachment, NormalizedConversation, NormalizedMessage


def _load_asset_map(folder: Path) -> dict[str, str]:
    candidates = sorted(folder.glob("conversation_asset_file_names*.json"))
    for candidate in candidates:
        try:
            data = json.loads(candidate.read_text(encoding="utf-8-sig"))
            if isinstance(data, dict):
                return {str(key): str(value) for key, value in data.items()}
        except (OSError, ValueError):
            continue
    return {}


def _asset_path(pointer: str, asset_map: dict[str, str], folder: Path, root: Path) -> Path | None:
    name = pointer.rsplit("/", 1)[-1]
    options = [name, f"{name}.dat" if not name.endswith(".dat") else name]
    mapped = next((asset_map[key] for key in options if key in asset_map), None)
    candidates = [folder / mapped] if mapped else []
    candidates.extend(folder / value for value in options)
    return next((path for path in candidates if path and path.is_file() and path.resolve().is_relative_to(root.resolve())), None)


def _content_text(content: dict[str, Any]) -> str:
    parts = content.get("parts") or []
    collected: list[str] = []
    for part in parts:
        if isinstance(part, str):
            collected.append(part)
        elif isinstance(part, dict) and isinstance(part.get("text"), str):
            collected.append(part["text"])
    if content.get("content_type") == "thoughts":
        for thought in content.get("thoughts") or []:
            if isinstance(thought, dict):
                text = thought.get("content") or thought.get("summary")
                if text:
                    collected.append(str(text))
    return "\n\n".join(value.strip() for value in collected if value and value.strip())


def _attachments(
    message: dict[str, Any], asset_map: dict[str, str], folder: Path, root: Path
) -> list[NormalizedAttachment]:
    candidates: list[dict[str, Any]] = []
    for part in (message.get("content") or {}).get("parts") or []:
        if isinstance(part, dict) and (part.get("asset_pointer") or part.get("audio_asset_pointer")):
            candidates.append(part)
    for item in (message.get("metadata") or {}).get("attachments") or []:
        if isinstance(item, dict):
            candidates.append(item)

    results: list[NormalizedAttachment] = []
    seen: set[str] = set()
    for item in candidates:
        pointer = item.get("asset_pointer") or item.get("audio_asset_pointer") or item.get("id")
        if not pointer:
            continue
        path = _asset_path(str(pointer), asset_map, folder, root)
        if path is None:
            continue
        relative = path.resolve().relative_to(root.resolve()).as_posix()
        if relative in seen:
            continue
        seen.add(relative)
        mime = item.get("mime_type") or mimetypes.guess_type(path.name)[0]
        results.append(
            NormalizedAttachment(
                relative_path=relative,
                original_name=asset_map.get(path.name, path.name),
                mime_type=mime,
                size_bytes=path.stat().st_size,
            )
        )
    return results


def _active_nodes(mapping: dict[str, Any], current_node: str | None) -> set[str]:
    active: set[str] = set()
    node_id = current_node
    while node_id and node_id not in active:
        active.add(node_id)
        node = mapping.get(node_id) or {}
        node_id = node.get("parent")
    return active


def parse_chatgpt_file(path: Path, source_root: Path) -> list[NormalizedConversation]:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, list):
        raise ValueError(f"Akar JSON harus berupa daftar: {path}")
    asset_map = _load_asset_map(path.parent)
    output: list[NormalizedConversation] = []

    for raw_conversation in data:
        if not isinstance(raw_conversation, dict):
            continue
        mapping = raw_conversation.get("mapping") or {}
        current_node = raw_conversation.get("current_node")
        active = _active_nodes(mapping, current_node)
        nodes = list(mapping.items())
        nodes.sort(
            key=lambda pair: (
                parse_timestamp(((pair[1] or {}).get("message") or {}).get("create_time"))
                or parse_timestamp(raw_conversation.get("create_time"))
                or parse_timestamp(0),
                pair[0],
            )
        )
        messages: list[NormalizedMessage] = []
        for order, (node_id, node) in enumerate(nodes):
            message = (node or {}).get("message")
            if not isinstance(message, dict):
                continue
            content = message.get("content") or {}
            body = _content_text(content)
            attachments = _attachments(message, asset_map, path.parent, source_root)
            if not body and not attachments:
                continue
            message_id = str(message.get("id") or node_id)
            messages.append(
                NormalizedMessage(
                    source_id=message_id,
                    parent_source_id=node.get("parent"),
                    role=str((message.get("author") or {}).get("role") or "unknown"),
                    body=body,
                    created_at=parse_timestamp(message.get("create_time")),
                    sort_order=order,
                    content_type=str(content.get("content_type") or "text"),
                    is_current_path=node_id in active,
                    raw_payload=json_safe(message),
                    attachments=attachments,
                )
            )
        conversation_id = raw_conversation.get("conversation_id") or raw_conversation.get("id")
        title = str(raw_conversation.get("title") or "Tanpa judul")
        created_at = parse_timestamp(raw_conversation.get("create_time"))
        updated_at = parse_timestamp(raw_conversation.get("update_time"))
        fingerprint = stable_hash("chatgpt", conversation_id or title, created_at)
        output.append(
            NormalizedConversation(
                source_id=str(conversation_id) if conversation_id else None,
                fingerprint=fingerprint,
                title=title,
                created_at=created_at,
                updated_at=updated_at,
                current_node_source_id=str(current_node) if current_node else None,
                messages=messages,
                raw_payload={
                    key: json_safe(value)
                    for key, value in raw_conversation.items()
                    if key != "mapping"
                },
            )
        )
    return output

