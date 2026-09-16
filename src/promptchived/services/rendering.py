import bleach
import html
from datetime import datetime

from ..config import get_settings
from markdown_it import MarkdownIt

_markdown = MarkdownIt("commonmark", {"html": False, "linkify": True, "typographer": False})
_tags = set(bleach.sanitizer.ALLOWED_TAGS) | {
    "p", "pre", "code", "h1", "h2", "h3", "h4", "h5", "h6",
    "ul", "ol", "li", "blockquote", "hr", "br", "table", "thead", "tbody", "tr", "th", "td",
}


def render_markdown(value: str) -> str:
    rendered = _markdown.render(value or "")
    return bleach.clean(
        rendered,
        tags=_tags,
        attributes={"a": ["href", "title"]},
        protocols={"http", "https", "mailto"},
        strip=True,
    )


def render_highlight(value: str) -> str:
    escaped = html.escape(value or "")
    return escaped.replace("&lt;mark&gt;", "<mark>").replace("&lt;/mark&gt;", "</mark>")


def format_datetime(value: datetime | None) -> str:
    if value is None:
        return ""
    return value.astimezone(get_settings().zoneinfo).strftime("%d %b %Y · %H:%M WIB")
