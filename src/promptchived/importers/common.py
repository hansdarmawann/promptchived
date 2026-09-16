import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

def stable_hash(*values: object) -> str:
    encoded = "\x1f".join("" if value is None else str(value) for value in values)
    return hashlib.sha256(encoded.encode("utf-8", errors="replace")).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def json_safe(value: Any) -> Any:
    """Return JSON-compatible data while keeping the original export structure."""
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))


def parse_timestamp(value: object) -> datetime | None:
    if value in (None, ""):
        return None
    try:
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(float(value), tz=UTC)
        raw = str(value).replace("\u202f", " ").strip()
        if raw.replace(".", "", 1).isdigit():
            return datetime.fromtimestamp(float(raw), tz=UTC)
        offsets = {" WIB": " +07:00", " WITA": " +08:00", " WIT": " +09:00"}
        for suffix, offset in offsets.items():
            if raw.endswith(suffix):
                raw = raw[: -len(suffix)] + offset
                break
        parsed = None
        for format_string in (
            "%b %d, %Y, %I:%M:%S %p %z",
            "%b %d, %Y, %I:%M:%S %p",
        ):
            try:
                parsed = datetime.strptime(raw, format_string)
                break
            except ValueError:
                pass
        if parsed is None:
            try:
                parsed = datetime.fromisoformat(raw)
            except ValueError:
                from dateutil import parser as date_parser

                parsed = date_parser.parse(raw)
        return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)
    except (ValueError, TypeError, OverflowError):
        return None
