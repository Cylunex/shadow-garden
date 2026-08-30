"""Preview-time link, asset and stable-source validation.

Live HTTP checks are opt-in. They resolve every hop and reject loopback, private,
link-local and reserved destinations before opening a socket, preventing the preview
tool from becoming an SSRF proxy.
"""
from __future__ import annotations

import ipaddress
import json
import socket
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urljoin, urlsplit

import requests

from .config import SITE_DIR, settings
from .rendering import render_markdown

_SOURCE_PREFIXES = ("shadow://archive/records/", "shadow://travel/maps/")


class _Links(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.values: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        wanted = "href" if tag == "a" else "src" if tag == "img" else None
        if wanted:
            value = dict(attrs).get(wanted)
            if value:
                self.values.append((tag, value))


def _issue(code: str, message: str, reference: str, *, severity: str = "error") -> dict[str, str]:
    return {"code": code, "severity": severity, "message": message, "reference": reference[:500]}


def _safe_public_url(url: str) -> tuple[bool, str]:
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError:
        return False, "URL 端口格式无效"
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return False, "只允许完整的 HTTP(S) URL"
    if parsed.username or parsed.password:
        return False, "URL 不能包含凭据"
    if port and port not in {80, 443}:
        return False, "外链检查只允许 80/443 端口"
    try:
        addresses = {
            item[4][0]
            for item in socket.getaddrinfo(parsed.hostname, port or (443 if parsed.scheme == "https" else 80))
        }
    except OSError:
        return False, "域名无法解析"
    for raw in addresses:
        address = ipaddress.ip_address(raw)
        if not address.is_global:
            return False, "目标地址不是公网地址"
    return True, ""


def _probe_external(url: str) -> tuple[bool, str]:
    session = requests.Session()
    session.trust_env = False
    current = url
    try:
        for _ in range(4):
            safe, reason = _safe_public_url(current)
            if not safe:
                return False, reason
            response = session.get(
                current,
                allow_redirects=False,
                timeout=(3, 5),
                stream=True,
                headers={"Accept": "text/html,*/*;q=0.1", "Range": "bytes=0-0"},
            )
            try:
                if response.status_code in {301, 302, 303, 307, 308}:
                    location = response.headers.get("location")
                    if not location:
                        return False, "重定向缺少 Location"
                    current = urljoin(current, location)
                    continue
                return response.status_code < 400, f"HTTP {response.status_code}"
            finally:
                response.close()
        return False, "重定向次数过多"
    except requests.RequestException as exc:
        return False, type(exc).__name__
    finally:
        session.close()


def _internal_exists(conn, owner_id: str, value: str) -> bool:
    parsed = urlsplit(value)
    path = parsed.path
    if "\\" in path or any(part == ".." for part in Path(path).parts):
        return False
    if path.startswith("/uploads/"):
        name = path.removeprefix("/uploads/")
        return bool(name and Path(name).name == name and (settings.uploads_dir / name).is_file())
    if path in {"/blog/post.html", "/blog/post"}:
        slug = (parse_qs(parsed.query).get("slug") or [""])[0]
        return bool(
            slug
            and conn.execute(
                "SELECT 1 FROM posts WHERE owner_id=? AND slug=?", (owner_id, slug)
            ).fetchone()
        )
    target = (SITE_DIR / path.lstrip("/")).resolve()
    root = SITE_DIR.resolve()
    if not target.is_relative_to(root):
        return False
    return target.is_file() or (target / "index.html").is_file()


def validate_post(
    conn,
    *,
    owner_id: str,
    title: str,
    content_md: str,
    source_refs: list[str],
    check_external: bool | None = None,
) -> dict[str, Any]:
    issues: list[dict[str, str]] = []
    if not title.strip():
        issues.append(_issue("title_missing", "发布前需要标题", "title"))
    if not content_md.strip():
        issues.append(
            _issue(
                "content_missing", "正文为空；确认这是刻意的短表达", "content_md",
                severity="warning",
            )
        )

    html = render_markdown(content_md)
    parser = _Links()
    parser.feed(html)
    external = settings.external_link_checks if check_external is None else check_external
    checks = {"internal": 0, "external": 0, "assets": 0, "archive": 0, "travel": 0}

    for source in dict.fromkeys(item.strip() for item in source_refs if item.strip()):
        if not source.startswith(_SOURCE_PREFIXES):
            issues.append(_issue("source_ref_invalid", "只接受稳定的 Archive 或 Travel 资源引用", source))
            continue
        if source.startswith("shadow://archive/"):
            checks["archive"] += 1
        else:
            checks["travel"] += 1
        if any(part in {"", ".", ".."} for part in source.split("/")[3:]):
            issues.append(_issue("source_ref_invalid", "资源引用格式无效", source))

    asset_urls = {
        row["url"] for row in conn.execute(
            "SELECT url FROM asset_files WHERE owner_id=?", (owner_id,)
        )
    }
    for kind, value in parser.values:
        parsed = urlsplit(value)
        if parsed.scheme in {"", None} and value.startswith("/"):
            checks["assets" if kind == "img" else "internal"] += 1
            if not _internal_exists(conn, owner_id, value):
                issues.append(_issue("internal_link_broken", "站内链接或资源不存在", value))
            continue
        if parsed.scheme not in {"http", "https", "mailto"}:
            issues.append(_issue("url_scheme_invalid", "链接协议不受支持", value))
            continue
        if parsed.scheme == "mailto":
            continue
        if value in asset_urls:
            checks["assets"] += 1
            continue
        checks["external"] += 1
        safe, reason = _safe_public_url(value)
        if not safe:
            issues.append(_issue("external_link_unsafe", reason, value))
        elif external:
            ok, detail = _probe_external(value)
            if not ok:
                issues.append(_issue("external_link_broken", detail, value))
        else:
            issues.append(
                _issue(
                    "external_link_unchecked",
                    "外链语法有效；当前环境未启用实时探测",
                    value,
                    severity="warning",
                )
            )

    return {
        "valid": not any(item["severity"] == "error" for item in issues),
        "content_html": html,
        "issues": issues,
        "checks": checks,
    }


def decode_validation(raw: str) -> dict[str, Any]:
    try:
        value = json.loads(raw or "{}")
        return value if isinstance(value, dict) else {}
    except (TypeError, ValueError):
        return {}
