"""Markdown rendering with an allow-list sanitizer for every authoring path."""
import re

import bleach
import markdown

_MD_EXTENSIONS = ["fenced_code", "tables", "sane_lists", "nl2br", "codehilite"]
_MD_CONFIG = {"codehilite": {"guess_lang": False, "css_class": "highlight"}}


def render_markdown(text: str) -> str:
    rendered = markdown.markdown(
        text or "", extensions=_MD_EXTENSIONS, extension_configs=_MD_CONFIG
    )
    tags = set(bleach.sanitizer.ALLOWED_TAGS) | {
        "p", "pre", "code", "blockquote", "hr", "br", "h1", "h2", "h3",
        "h4", "h5", "h6", "table", "thead", "tbody", "tr", "th", "td",
        "img", "del", "div", "span",
    }
    attrs = {
        **bleach.sanitizer.ALLOWED_ATTRIBUTES,
        "a": ["href", "title", "rel"],
        "img": ["src", "alt", "title", "width", "height"],
        "code": ["class"], "div": ["class"], "span": ["class"],
    }
    return bleach.clean(
        rendered,
        tags=tags,
        attributes=attrs,
        protocols={"http", "https", "mailto"},
        strip=True,
    )


_SLUG_STRIP = re.compile(r"[^a-z0-9一-鿿]+")


def slugify(text: str) -> str:
    """尽量从标题生成 slug；中文标题会保留汉字（URL 会被编码，够用）。"""
    slug = _SLUG_STRIP.sub("-", (text or "").lower()).strip("-")
    return slug[:80]


_CJK = re.compile(r"[㐀-䶿一-鿿]")
_WORD = re.compile(r"[A-Za-z0-9_']+")


def word_count(text: str) -> int:
    """中文按字、英文按词计数。"""
    t = text or ""
    return len(_CJK.findall(t)) + len(_WORD.findall(t))


def reading_minutes(text: str) -> int:
    """按每分钟 400 字/词估算，至少 1 分钟。"""
    n = word_count(text)
    return max(1, round(n / 400)) if n else 0
