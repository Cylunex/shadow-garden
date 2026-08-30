from __future__ import annotations

import json
import secrets
import sqlite3
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from typing_extensions import Literal

from ..auth import (
    actor_id,
    content_owner_id,
    get_redis,
    optional_content_editor,
    require_admin,
    require_content_editor,
    require_publisher,
)
from ..content_health import decode_validation, validate_post
from ..config import settings
from ..db import get_db, inserted_id, now_iso, tags_from_json, tags_to_json
from ..oidc import BrowserIdentity
from ..rendering import reading_minutes, render_markdown, slugify, word_count

router = APIRouter(prefix="/api/posts", tags=["posts"])
PostState = Literal["draft", "preview", "revision", "published", "withdrawn"]


class PostIn(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    slug: str = Field(default="", max_length=100)
    summary: str = Field(default="", max_length=1000)
    content_md: str = Field(default="", max_length=1_000_000)
    tags: List[str] = Field(default_factory=list, max_length=50)
    source_refs: List[str] = Field(default_factory=list, max_length=50)
    status: PostState = "draft"


class PostPatch(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=240)
    slug: Optional[str] = Field(default=None, max_length=100)
    summary: Optional[str] = Field(default=None, max_length=1000)
    content_md: Optional[str] = Field(default=None, max_length=1_000_000)
    tags: Optional[List[str]] = Field(default=None, max_length=50)
    source_refs: Optional[List[str]] = Field(default=None, max_length=50)
    status: Optional[PostState] = None


class PreviewOptions(BaseModel):
    check_external: bool | None = None


def _json_list(raw: str) -> list[str]:
    try:
        value = json.loads(raw or "[]")
        return [str(item) for item in value] if isinstance(value, list) else []
    except (TypeError, ValueError):
        return []


def _serialize(row: sqlite3.Row, with_content: bool = False) -> dict:
    post = {
        "id": row["id"], "slug": row["slug"], "title": row["title"],
        "summary": row["summary"], "tags": tags_from_json(row["tags"]),
        "source_refs": _json_list(row["source_refs"]), "status": row["status"],
        "revision": row["revision"], "previewed_revision": row["previewed_revision"],
        "published_at": row["published_at"], "withdrawn_at": row["withdrawn_at"],
        "views": row["views"], "waters": row["waters"],
        "created_at": row["created_at"], "updated_at": row["updated_at"],
        "validation": decode_validation(row["validation_json"]),
    }
    if with_content:
        post.update(
            content_md=row["content_md"], content_html=row["content_html"],
            word_count=word_count(row["content_md"]),
            reading_minutes=reading_minutes(row["content_md"]),
        )
    return post


def _unique_slug(conn, owner_id: str, wanted: str, exclude_id: Optional[int]) -> str:
    slug = slugify(wanted) or f"post-{secrets.token_hex(4)}"
    candidate = slug
    suffix = 2
    while True:
        row = conn.execute(
            "SELECT id FROM posts WHERE owner_id=? AND slug=?", (owner_id, candidate)
        ).fetchone()
        if row is None or row["id"] == exclude_id:
            return candidate
        candidate = f"{slug}-{suffix}"
        suffix += 1


def _context(request: Request) -> tuple[str, str]:
    operation = request.state.operation_context
    return actor_id(request), operation.correlation_id


def _snapshot(conn, row, *, actor: str, correlation_id: str) -> None:
    conn.execute(
        """INSERT INTO post_revisions
           (post_id, owner_id, revision, state, title, slug, summary, content_md,
            content_html, tags, source_refs, validation_json, actor_id,
            correlation_id, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            row["id"], row["owner_id"], row["revision"], row["status"], row["title"],
            row["slug"], row["summary"], row["content_md"], row["content_html"],
            row["tags"], row["source_refs"], row["validation_json"], actor,
            correlation_id, now_iso(),
        ),
    )


def _event(
    conn,
    row,
    *,
    from_state: str | None,
    to_state: str,
    actor: str,
    correlation_id: str,
    detail: str = "",
) -> None:
    conn.execute(
        """INSERT INTO post_events
           (post_id, owner_id, from_state, to_state, revision, actor_id,
            correlation_id, detail, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            row["id"], row["owner_id"], from_state, to_state, row["revision"],
            actor, correlation_id, detail, now_iso(),
        ),
    )


def _owned(conn, post_id: int, owner_id: str):
    row = conn.execute(
        "SELECT * FROM posts WHERE id=? AND owner_id=?", (post_id, owner_id)
    ).fetchone()
    if row is None:
        raise HTTPException(404, "文章不存在")
    return row


@router.get("")
def list_posts(
    tag: Optional[str] = None,
    is_editor: bool = Depends(optional_content_editor),
    owner_id: str = Depends(content_owner_id),
    conn=Depends(get_db),
):
    if is_editor:
        rows = conn.execute(
            "SELECT * FROM posts WHERE owner_id=? ORDER BY COALESCE(published_at, created_at) DESC",
            (owner_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM posts WHERE owner_id=? AND status='published' ORDER BY published_at DESC",
            (owner_id,),
        ).fetchall()
    items = [_serialize(row) for row in rows]
    if tag:
        items = [item for item in items if tag in item["tags"]]
    return {"items": items}


@router.get("/{slug}")
def get_post(
    slug: str,
    is_editor: bool = Depends(optional_content_editor),
    owner_id: str = Depends(content_owner_id),
    conn=Depends(get_db),
):
    row = conn.execute(
        "SELECT * FROM posts WHERE owner_id=? AND slug=?", (owner_id, slug)
    ).fetchone()
    if row is None or (row["status"] != "published" and not is_editor):
        raise HTTPException(404, "文章不存在")
    if not is_editor:
        conn.execute("UPDATE posts SET views=views+1 WHERE id=? AND owner_id=?", (row["id"], owner_id))
        row = _owned(conn, row["id"], owner_id)
    post = _serialize(row, with_content=True)
    post["prev"] = post["next"] = None
    if row["status"] == "published":
        previous = conn.execute(
            """SELECT slug,title FROM posts WHERE owner_id=? AND status='published'
               AND (published_at,id)<(?,?) ORDER BY published_at DESC,id DESC LIMIT 1""",
            (owner_id, row["published_at"], row["id"]),
        ).fetchone()
        following = conn.execute(
            """SELECT slug,title FROM posts WHERE owner_id=? AND status='published'
               AND (published_at,id)>(?,?) ORDER BY published_at,id LIMIT 1""",
            (owner_id, row["published_at"], row["id"]),
        ).fetchone()
        if previous:
            post["prev"] = dict(previous)
        if following:
            post["next"] = dict(following)
    return post


@router.post("/{slug}/water")
def water_post(slug: str, request: Request, owner_id: str = Depends(content_owner_id), conn=Depends(get_db)):
    row = conn.execute(
        "SELECT id,waters FROM posts WHERE owner_id=? AND slug=? AND status='published'",
        (owner_id, slug),
    ).fetchone()
    if row is None:
        raise HTTPException(404, "文章不存在")
    redis = get_redis()
    if redis is not None:
        ip = request.headers.get("x-real-ip") or (request.client.host if request.client else "unknown")
        key = f"garden:water:{owner_id}:{slug}:{ip}"
        if not redis.set(key, 1, nx=True, ex=86400):
            return {"waters": row["waters"], "watered": False}
    conn.execute("UPDATE posts SET waters=waters+1 WHERE id=? AND owner_id=?", (row["id"], owner_id))
    fresh = conn.execute("SELECT waters FROM posts WHERE id=? AND owner_id=?", (row["id"], owner_id)).fetchone()
    return {"waters": fresh["waters"], "watered": True}


@router.post("", status_code=201)
def create_post(
    body: PostIn,
    request: Request,
    identity: Optional[BrowserIdentity] = Depends(require_content_editor),
    owner_id: str = Depends(content_owner_id),
    conn=Depends(get_db),
):
    requested_state = body.status
    if requested_state not in {"draft", "published"}:
        raise HTTPException(409, "新文章必须从草稿开始")
    if requested_state == "published" and (
        identity is None or not identity.in_group(settings.publisher_group)
    ):
        raise HTTPException(403, "需要 Garden 发布权限")
    now = now_iso()
    actor, correlation = _context(request)
    slug = _unique_slug(conn, owner_id, body.slug.strip() or body.title, None)
    cursor = conn.execute(
        """INSERT INTO posts
           (owner_id,slug,title,summary,content_md,content_html,tags,status,published_at,
            revision,previewed_revision,withdrawn_at,source_refs,validation_json,
            created_at,updated_at)
           VALUES (?,?,?,?,?,?,?,'draft',NULL,1,NULL,NULL,?,'{}',?,?) RETURNING id""",
        (
            owner_id, slug, body.title.strip(), body.summary.strip(), body.content_md,
            render_markdown(body.content_md), tags_to_json(body.tags),
            json.dumps(body.source_refs, ensure_ascii=False), now, now,
        ),
    )
    row = _owned(conn, inserted_id(cursor), owner_id)
    _snapshot(conn, row, actor=actor, correlation_id=correlation)
    _event(conn, row, from_state=None, to_state="draft", actor=actor, correlation_id=correlation)
    if requested_state == "published":
        row, validation = preview_transition(conn, row, request=request)
        if not validation["valid"]:
            raise HTTPException(422, {"code": "preview_failed", "validation": validation})
        row = publish_transition(conn, row, request=request)
    return _serialize(row, with_content=True)


def _update_post(post_id: int, body: PostIn, request: Request, owner_id: str, conn) -> dict:
    row = _owned(conn, post_id, owner_id)
    if body.status != row["status"]:
        raise HTTPException(409, "状态只能通过预览、发布或撤回动作改变")
    if row["status"] == "published":
        raise HTTPException(409, "已发布文章需先撤回再修订")
    new_state = "revision" if row["status"] in {"preview", "revision", "withdrawn"} else "draft"
    revision = row["revision"] + 1
    slug = _unique_slug(conn, owner_id, body.slug.strip() or body.title, post_id)
    conn.execute(
        """UPDATE posts SET slug=?,title=?,summary=?,content_md=?,content_html=?,tags=?,
           status=?,revision=?,previewed_revision=NULL,source_refs=?,validation_json='{}',
           updated_at=? WHERE id=? AND owner_id=?""",
        (
            slug, body.title.strip(), body.summary.strip(), body.content_md,
            render_markdown(body.content_md), tags_to_json(body.tags), new_state, revision,
            json.dumps(body.source_refs, ensure_ascii=False), now_iso(), post_id, owner_id,
        ),
    )
    fresh = _owned(conn, post_id, owner_id)
    actor, correlation = _context(request)
    _snapshot(conn, fresh, actor=actor, correlation_id=correlation)
    if new_state != row["status"]:
        _event(conn, fresh, from_state=row["status"], to_state=new_state, actor=actor, correlation_id=correlation, detail="content revised")
    return _serialize(fresh, with_content=True)


@router.put("/{post_id}")
def update_post(
    post_id: int,
    body: PostIn,
    request: Request,
    identity: Optional[BrowserIdentity] = Depends(require_content_editor),
    owner_id: str = Depends(content_owner_id),
    conn=Depends(get_db),
):
    row = _owned(conn, post_id, owner_id)
    if body.status != row["status"]:
        if identity is None:
            raise HTTPException(403, "Agent 只能修改未发布草稿")
        if body.status != "published" or not identity.in_group(settings.publisher_group):
            raise HTTPException(409, "状态只能通过预览、发布或撤回动作改变")
        draft_body = body.model_copy(update={"status": row["status"]})
        _update_post(post_id, draft_body, request, owner_id, conn)
        fresh, validation = preview_transition(
            conn, _owned(conn, post_id, owner_id), request=request
        )
        if not validation["valid"]:
            raise HTTPException(422, {"code": "preview_failed", "validation": validation})
        return _serialize(publish_transition(conn, fresh, request=request), with_content=True)
    return _update_post(post_id, body, request, owner_id, conn)


@router.patch("/{post_id}")
def patch_post(
    post_id: int,
    body: PostPatch,
    request: Request,
    identity: Optional[BrowserIdentity] = Depends(require_content_editor),
    owner_id: str = Depends(content_owner_id),
    conn=Depends(get_db),
):
    row = _owned(conn, post_id, owner_id)
    current = {
        "title": row["title"], "slug": row["slug"], "summary": row["summary"],
        "content_md": row["content_md"], "tags": tags_from_json(row["tags"]),
        "source_refs": _json_list(row["source_refs"]), "status": row["status"],
    }
    current.update(body.model_dump(exclude_unset=True))
    if identity is None and current["status"] != row["status"]:
        raise HTTPException(403, "Agent 只能修改未发布草稿")
    return _update_post(post_id, PostIn(**current), request, owner_id, conn)


def preview_transition(conn, row, *, request: Request, check_external: bool | None = None):
    if row["status"] not in {"draft", "revision"}:
        raise HTTPException(409, "只有草稿或修订稿可以生成发布预览")
    validation = validate_post(
        conn,
        owner_id=row["owner_id"],
        title=row["title"],
        content_md=row["content_md"],
        source_refs=_json_list(row["source_refs"]),
        check_external=check_external,
    )
    encoded = json.dumps(validation, ensure_ascii=False, separators=(",", ":"))
    conn.execute(
        "UPDATE posts SET validation_json=?,content_html=? WHERE id=? AND owner_id=?",
        (encoded, validation["content_html"], row["id"], row["owner_id"]),
    )
    if not validation["valid"]:
        return _owned(conn, row["id"], row["owner_id"]), validation
    previous = row["status"]
    conn.execute(
        "UPDATE posts SET status='preview',previewed_revision=revision,updated_at=? WHERE id=? AND owner_id=?",
        (now_iso(), row["id"], row["owner_id"]),
    )
    fresh = _owned(conn, row["id"], row["owner_id"])
    actor, correlation = _context(request)
    _event(conn, fresh, from_state=previous, to_state="preview", actor=actor, correlation_id=correlation, detail="preview validation passed")
    return fresh, validation


@router.post("/{post_id}/preview")
def preview_post(
    post_id: int,
    body: PreviewOptions,
    request: Request,
    _: Optional[BrowserIdentity] = Depends(require_content_editor),
    owner_id: str = Depends(content_owner_id),
    conn=Depends(get_db),
):
    row, validation = preview_transition(
        conn, _owned(conn, post_id, owner_id), request=request, check_external=body.check_external
    )
    return {"post": _serialize(row, with_content=True), "validation": validation}


def publish_transition(conn, row, *, request: Request) -> object:
    if row["status"] != "preview" or row["previewed_revision"] != row["revision"]:
        raise HTTPException(409, "发布前必须通过当前修订版的预览校验")
    validation = validate_post(
        conn, owner_id=row["owner_id"], title=row["title"], content_md=row["content_md"],
        source_refs=_json_list(row["source_refs"]), check_external=None,
    )
    if not validation["valid"]:
        raise HTTPException(409, {"code": "preview_stale", "validation": validation})
    now = now_iso()
    conn.execute(
        """UPDATE posts SET status='published',published_at=?,withdrawn_at=NULL,
           validation_json=?,content_html=?,updated_at=? WHERE id=? AND owner_id=?""",
        (
            now, json.dumps(validation, ensure_ascii=False, separators=(",", ":")),
            validation["content_html"], now, row["id"], row["owner_id"],
        ),
    )
    fresh = _owned(conn, row["id"], row["owner_id"])
    actor, correlation = _context(request)
    _event(conn, fresh, from_state="preview", to_state="published", actor=actor, correlation_id=correlation, detail="current preview published")
    return fresh


@router.post("/{post_id}/publish", dependencies=[Depends(require_publisher)])
def publish_post(post_id: int, request: Request, owner_id: str = Depends(content_owner_id), conn=Depends(get_db)):
    return _serialize(publish_transition(conn, _owned(conn, post_id, owner_id), request=request), with_content=True)


@router.post("/{post_id}/withdraw", dependencies=[Depends(require_publisher)])
def withdraw_post(post_id: int, request: Request, owner_id: str = Depends(content_owner_id), conn=Depends(get_db)):
    row = _owned(conn, post_id, owner_id)
    if row["status"] != "published":
        raise HTTPException(409, "只有已发布文章可以撤回")
    now = now_iso()
    conn.execute(
        "UPDATE posts SET status='withdrawn',withdrawn_at=?,updated_at=? WHERE id=? AND owner_id=?",
        (now, now, post_id, owner_id),
    )
    fresh = _owned(conn, post_id, owner_id)
    actor, correlation = _context(request)
    _event(conn, fresh, from_state="published", to_state="withdrawn", actor=actor, correlation_id=correlation, detail="public post withdrawn")
    return _serialize(fresh, with_content=True)


@router.get("/{post_id}/history", dependencies=[Depends(require_content_editor)])
def post_history(post_id: int, owner_id: str = Depends(content_owner_id), conn=Depends(get_db)):
    _owned(conn, post_id, owner_id)
    revisions = [dict(row) for row in conn.execute(
        """SELECT revision,state,actor_id,correlation_id,created_at,title,slug
           FROM post_revisions WHERE post_id=? AND owner_id=? ORDER BY revision DESC""",
        (post_id, owner_id),
    )]
    events = [dict(row) for row in conn.execute(
        """SELECT from_state,to_state,revision,actor_id,correlation_id,detail,created_at
           FROM post_events WHERE post_id=? AND owner_id=? ORDER BY id""",
        (post_id, owner_id),
    )]
    return {"post_id": post_id, "revisions": revisions, "events": events}


@router.delete("/{post_id}", dependencies=[Depends(require_admin)])
def delete_post(post_id: int, owner_id: str = Depends(content_owner_id), conn=Depends(get_db)):
    row = _owned(conn, post_id, owner_id)
    if row["status"] == "published":
        raise HTTPException(409, "已发布文章必须先撤回；删除不会替代撤回审计")
    conn.execute("DELETE FROM posts WHERE id=? AND owner_id=?", (post_id, owner_id))
    return {"ok": True}
