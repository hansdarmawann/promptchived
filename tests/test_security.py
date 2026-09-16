from pathlib import Path

import pytest

from promptchived.services.attachments import UnsafeAttachmentPath, resolve_attachment
from promptchived.services.rendering import render_highlight, render_markdown


def test_attachment_must_stay_inside_source(tmp_path):
    root = tmp_path / "source"
    root.mkdir()
    safe = root / "photo.jpg"
    safe.write_bytes(b"image")
    outside = tmp_path / "secret.txt"
    outside.write_text("secret")

    assert resolve_attachment(str(root), "photo.jpg") == safe.resolve()
    with pytest.raises(UnsafeAttachmentPath):
        resolve_attachment(str(root), "../secret.txt")


def test_renderers_do_not_allow_exported_scripts():
    rendered = render_markdown("hello <script>alert(1)</script> [x](javascript:alert(1))")
    assert "<script" not in rendered
    assert 'href="javascript:' not in rendered
    highlighted = render_highlight('<script>x</script> <mark>match</mark>')
    assert "<script" not in highlighted
    assert "<mark>match</mark>" in highlighted
