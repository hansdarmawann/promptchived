from pathlib import Path


class UnsafeAttachmentPath(ValueError):
    pass


def resolve_attachment(root_path: str, relative_path: str) -> Path:
    root = Path(root_path).resolve()
    candidate = (root / relative_path).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise UnsafeAttachmentPath("Lampiran berada di luar folder sumber") from exc
    if not candidate.is_file():
        raise FileNotFoundError(candidate)
    return candidate
