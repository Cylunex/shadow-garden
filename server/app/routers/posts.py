import secrets
import sqlite3
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from typing_extensions import Literal

from ..auth import (
    get_redis,
    optional_content_editor,
    require_admin,
    require_content_editor,
)
from ..oidc import BrowserIdentity
from ..db import get_db, inserted_id, now_iso, tags_from_json, tags_to_json
from ..rendering import reading_minutes, render_markdown, slugify, word_count

router = APIRouter(prefix="/api/posts", tags=["posts"])


class PostIn(BaseModel):
    title: str = Field(min_length=1)
    slug: str = ""
    summary: str = ""
    content_md: str = ""
    tags: List[str] = []
    status: Literal["draft", "published"] = "draft"


class PostPatch(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1)
    slug: Optional[str] = None
    summary: Optional[str] = None
    content_md: Optional[str] = None
    tags: Optional[List[str]] = None
    status: Optional[Literal["draft", "published"]] = None


def _serialize(row: sqlite3.Row, with_content: bool = False) -> dict:
    post = {
        "id": row["id"],
        "slug": row["slug"],
        "title": row["title"],
        "summary": row["summary"],
        "tags": tags_from_json(row["tags"]),
        "status": row["status"],
        "published_at": row["published_at"],
        "views": row["views"],
        "waters": row["waters"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }
    if with_content:
        post["content_md"] = row["content_md"]
        post["content_html"] = row["content_html"]
        post["word_count"] = word_count(row["content_md"])
        post["reading_minutes"] = reading_minutes(row["content_md"])
    return post


def _unique_slug(conn: sqlite3.Connection, wanted: str, exclude_id: Optional[int]) -> str:
    slug = wanted or f"post-{secrets.token_hex(4)}"
    candidate = slug
    n = 2
    while True:
        row = conn.execute(
            "SELECT id FROM posts WHERE slug = ?", (candidate,)
        ).fetchone()
        if row is None or row["id"] == exclude_id:
            return candidate
        candidate = f"{slug}-{n}"
        n += 1


@router.get("")
def list_posts(
    tag: Optional[str] = None,
    is_editor: bool = Depends(optional_content_editor),
    conn: sqlite3.Connection = Depends(get_db),
):
    if is_editor:
        rows = conn.execute(
            "SELECT * FROM posts ORDER BY COALESCE(published_at, created_at) DESC"
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM posts WHERE status = 'published' ORDER BY published_at DESC"
        ).fetchall()
    posts = [_serialize(r) for r in rows]
    if tag:
        posts = [p for p in posts if tag in p["tags"]]
    return {"items": posts}


@router.get("/{slug}")
def get_post(
    slug: str,
    is_editor: bool = Depends(optional_content_editor),
    conn: sqlite3.Connection = Depends(get_db),
):
    row = conn.execute("SELECT * FROM posts WHERE slug = ?", (slug,)).fetchone()
    if row is None or (row["status"] != "published" and not is_editor):
        raise HTTPException(404, "文章不存在")

    # 公开访问计一次阅读（管理端预览不算）
    if not is_editor and row["status"] == "published":
        conn.execute("UPDATE posts SET views = views + 1 WHERE id = ?", (row["id"],))
        row = conn.execute("SELECT * FROM posts WHERE id = ?", (row["id"],)).fetchone()

    post = _serialize(row, with_content=True)
    post["prev"] = post["next"] = None
    if row["status"] == "published":
        prev_row = conn.execute(
            """SELECT slug, title FROM posts WHERE status = 'published'
               AND (published_at, id) < (?, ?) ORDER BY published_at DESC, id DESC LIMIT 1""",
            (row["published_at"], row["id"]),
        ).fetchone()
        next_row = conn.execute(
            """SELECT slug, title FROM posts WHERE status = 'published'
               AND (published_at, id) > (?, ?) ORDER BY published_at ASC, id ASC LIMIT 1""",
            (row["published_at"], row["id"]),
        ).fetchone()
        if prev_row:
            post["prev"] = {"slug": prev_row["slug"], "title": prev_row["title"]}
        if next_row:
            post["next"] = {"slug": next_row["slug"], "title": next_row["title"]}
    return post


@router.post("/{slug}/water")
def water_post(
    slug: str,
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
):
    """给文章浇水（匿名点赞）。配置了 Redis 时每 IP 每篇每天限一次。"""
    row = conn.execute(
        "SELECT id, waters FROM posts WHERE slug = ? AND status = 'published'", (slug,)
    ).fetchone()
    if row is None:
        raise HTTPException(404, "文章不存在")

    r = get_redis()
    if r is not None:
        ip = request.headers.get("x-real-ip") or (
            request.client.host if request.client else "unknown"
        )
        # SETNX + 24h 过期：今天浇过就不再计数
        if not r.set(f"garden:water:{slug}:{ip}", 1, nx=True, ex=86400):
            return {"waters": row["waters"], "watered": False}

    conn.execute("UPDATE posts SET waters = waters + 1 WHERE id = ?", (row["id"],))
    fresh = conn.execute("SELECT waters FROM posts WHERE id = ?", (row["id"],)).fetchone()
    return {"waters": fresh["waters"], "watered": True}


def _require_agent_draft(
    identity: Optional[BrowserIdentity],
    *,
    requested_status: str,
    current_status: Optional[str] = None,
) -> None:
    if identity is not None:
        return
    if requested_status == "published" or current_status == "published":
        raise HTTPException(403, "Agent 只能创建和修改未发布草稿")


@router.post("", status_code=201)
def create_post(
    body: PostIn,
    identity: Optional[BrowserIdentity] = Depends(require_content_editor),
    conn: sqlite3.Connection = Depends(get_db),
):
    _require_agent_draft(identity, requested_status=body.status)
    now = now_iso()
    slug = _unique_slug(conn, body.slug.strip() or slugify(body.title), None)
    published_at = now if body.status == "published" else None
    cur = conn.execute(
        """INSERT INTO posts (slug, title, summary, content_md, content_html,
                              tags, status, published_at, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) RETURNING id""",
        (
            slug, body.title, body.summary, body.content_md,
            render_markdown(body.content_md), tags_to_json(body.tags),
            body.status, published_at, now, now,
        ),
    )
    row = conn.execute("SELECT * FROM posts WHERE id = ?", (inserted_id(cur),)).fetchone()
    return _serialize(row, with_content=True)


def _update_post(post_id: int, body: PostIn, conn: sqlite3.Connection) -> dict:
    row = conn.execute("SELECT * FROM posts WHERE id = ?", (post_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "文章不存在")
    slug = _unique_slug(conn, body.slug.strip() or slugify(body.title), post_id)
    # 首次发布时记 published_at，之后保持不变
    published_at = row["published_at"]
    if body.status == "published" and not published_at:
        published_at = now_iso()
    if body.status == "draft":
        published_at = None
    conn.execute(
        """UPDATE posts SET slug=?, title=?, summary=?, content_md=?, content_html=?,
                            tags=?, status=?, published_at=?, updated_at=?
           WHERE id=?""",
        (
            slug, body.title, body.summary, body.content_md,
            render_markdown(body.content_md), tags_to_json(body.tags),
            body.status, published_at, now_iso(), post_id,
        ),
    )
    row = conn.execute("SELECT * FROM posts WHERE id = ?", (post_id,)).fetchone()
    return _serialize(row, with_content=True)


@router.put("/{post_id}")
def update_post(
    post_id: int,
    body: PostIn,
    identity: Optional[BrowserIdentity] = Depends(require_content_editor),
    conn: sqlite3.Connection = Depends(get_db),
):
    row = conn.execute("SELECT status FROM posts WHERE id = ?", (post_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "文章不存在")
    _require_agent_draft(
        identity,
        requested_status=body.status,
        current_status=row["status"],
    )
    return _update_post(post_id, body, conn)


@router.patch("/{post_id}")
def patch_post(
    post_id: int,
    body: PostPatch,
    identity: Optional[BrowserIdentity] = Depends(require_content_editor),
    conn: sqlite3.Connection = Depends(get_db),
):
    row = conn.execute("SELECT * FROM posts WHERE id = ?", (post_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "文章不存在")
    current = {
        "title": row["title"],
        "slug": row["slug"],
        "summary": row["summary"],
        "content_md": row["content_md"],
        "tags": tags_from_json(row["tags"]),
        "status": row["status"],
    }
    current.update(body.model_dump(exclude_unset=True))
    _require_agent_draft(
        identity,
        requested_status=current["status"],
        current_status=row["status"],
    )
    return _update_post(post_id, PostIn(**current), conn)


@router.delete("/{post_id}", dependencies=[Depends(require_admin)])
def delete_post(post_id: int, conn: sqlite3.Connection = Depends(get_db)):
    cur = conn.execute("DELETE FROM posts WHERE id = ?", (post_id,))
    if cur.rowcount == 0:
        raise HTTPException(404, "文章不存在")
    return {"ok": True}
