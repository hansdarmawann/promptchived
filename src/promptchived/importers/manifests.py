from pathlib import Path, PureWindowsPath


def read_manifest(path: Path) -> list[Path]:
    raw = path.read_bytes()
    text = None
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        text = raw.decode("utf-8", errors="replace")
    return [Path(line.strip()) for line in text.splitlines() if line.strip()]


def infer_source_root(path: Path) -> Path | None:
    entries = read_manifest(path)
    if not entries:
        return None
    first = PureWindowsPath(str(entries[0]))
    return Path(str(first.parent))
