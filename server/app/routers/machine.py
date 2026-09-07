"""Stable, least-privileged Garden API consumed by Shadow Plugin hosts."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from typing import Any, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from shadow_sdk.confirmation import (
    ConfirmationBinding,
    ConfirmationError,
    ConfirmationReplayStore,
    ConfirmationVerifier,
)

from ..agent import require_agent
from ..auth import content_owner_id
from ..config import settings
from ..db import get_db, inserted_id, now_iso, tags_from_json, tags_to_json
from ..rendering import render_markdown, slugify
from .posts import (
    _event,
    _snapshot,
    _unique_slug,
    preview_transition,
    publish_transition,
)

router = APIRouter(prefix="/api/machine/v1/agent", tags=["machine-agent"])


class NexusReviewCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: str = Field(min_length=1, max_length=120)
    summary: str = Field(min_length=1, max_length=500)
    fields: dict[str, Any] = Field(default_factory=dict)
    source_text: str = Field(default="", max_length=4000)
    source_refs: list[str] = Field(default_factory=list, max_length=16)


class NexusGardenCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    protocol: Literal["shadow.command.v1"]
    command_id: str = Field(pattern=r"^cmd_[A-Za-z0-9_-]{8,128}$")
    capability_ref: str = Field(pattern=r"^shadow://capabilities/.+/garden\.posts\.draft$")
    operation_id: Literal["execute_nexus_garden_command"]
    schema_version: Literal[1]
    arguments: NexusReviewCreate
    target_refs: list[str] = Field(default_factory=list, max_length=16)
    source_refs: list[str] = Field(default_factory=list, max_length=16)


_verifier: ConfirmationVerifier | None = None
_verifier_key: tuple[str, str, str, str] | None = None


def _authorization(value: str | None) -> str:
    return value or ""


def _request_id(request: Request) -> str:
    return request.state.operation_context.trace_id


def _review_id(agent_id: str, idempotency_key: str) -> str:
    digest = hashlib.sha256(f"{agent_id}\0{idempotency_key}".encode()).hexdigest()
    return f"review-{digest[:32]}"


def _request_hash(body: NexusReviewCreate) -> str:
    value = body.model_dump(mode="json")
    encoded = json.dumps(
        value, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _review_envelope(
    review: sqlite3.Row,
    post: sqlite3.Row,
    trace_id: str,
    *,
    receipt: str | None = None,
    replayed: bool = False,
) -> dict[str, Any]:
    status = {
        "pending": "pending",
        "published": "committed",
        "rejected": "rejected",
    }[review["status"]]
    return {
        "protocol": "shadow.review.v1",
        "review_id": review["id"],
        "reference": f"shadow://garden/reviews/{review['id']}",
        "revision": post["revision"],
        "domain": "garden",
        "intent": review["intent"],
        "summary": post["summary"] or post["title"],
        "state": status,
        "fields": {
            "postId": post["id"],
            "slug": post["slug"],
            "contentMd": post["content_md"],
            "tags": tags_from_json(post["tags"]),
            "publicUrl": f"/blog/{post['slug']}",
        },
        "risk_level": "L3",
        "created_at": review["created_at"],
        "source_refs": json.loads(post["source_refs"] or "[]"),
        "trace_id": trace_id,
        "receipt": receipt,
        "replayed": replayed,
    }


def _load_review(conn: sqlite3.Connection, review_id: str, owner_id: str) -> tuple[Any, Any]:
    review = conn.execute(
        "SELECT * FROM garden_agent_reviews WHERE id=? AND owner_id=?", (review_id, owner_id)
    ).fetchone()
    if review is None:
        raise HTTPException(404, "Garden review not found")
    post = conn.execute(
        "SELECT * FROM posts WHERE id=? AND owner_id=?", (review["post_id"], owner_id)
    ).fetchone()
    if post is None:
        raise HTTPException(409, "Garden review has lost its post")
    return review, post


def _confirmation_verifier() -> ConfirmationVerifier:
    global _verifier, _verifier_key
    key = (
        settings.confirmation_public_key_file,
        settings.confirmation_key_id,
        settings.confirmation_issuer,
        settings.confirmation_replay_db,
    )
    if not all(key):
        raise HTTPException(503, "Garden confirmation verification is not configured")
    if _verifier is None or _verifier_key != key:
        try:
            _verifier = ConfirmationVerifier(
                {key[1]: key[0]},
                allowed_issuers={key[2]},
                replay_store=ConfirmationReplayStore(key[3]),
            )
        except (ConfirmationError, OSError, ValueError) as exc:
            raise HTTPException(503, "Garden confirmation verification is unavailable") from exc
        _verifier_key = key
    return _verifier


@router.get("/summary", operation_id="get_garden_agent_summary")
def get_summary(
    authorization: str | None = Header(default=None),
    owner_id: str = Depends(content_owner_id),
    conn: sqlite3.Connection = Depends(get_db),
):
    require_agent(_authorization(authorization), scope="garden.summary.read")
    counts = {
        "published": conn.execute(
            "SELECT COUNT(*) AS n FROM posts WHERE owner_id=? AND status='published'", (owner_id,)
        ).fetchone()["n"],
        "drafts": conn.execute(
            "SELECT COUNT(*) AS n FROM posts WHERE owner_id=? AND status IN ('draft','preview','revision')", (owner_id,)
        ).fetchone()["n"],
        "pendingReviews": conn.execute(
            "SELECT COUNT(*) AS n FROM garden_agent_reviews WHERE owner_id=? AND status='pending'", (owner_id,)
        ).fetchone()["n"],
    }
    return {"status": "ready", "summary": "Garden 内容工作区已连接", "counts": counts}


@router.post("/nexus/reviews", status_code=201, operation_id="create_nexus_garden_review")
def create_review(
    body: NexusReviewCreate,
    request: Request,
    authorization: str | None = Header(default=None),
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=200),
    owner_id: str = Depends(content_owner_id),
    conn: sqlite3.Connection = Depends(get_db),
):
    identity = require_agent(_authorization(authorization), scope="garden.posts.draft")
    review_id = _review_id(identity.agent_id, idempotency_key)
    request_hash = _request_hash(body)
    existing = conn.execute(
        "SELECT * FROM garden_agent_reviews WHERE id=? AND owner_id=?", (review_id, owner_id)
    ).fetchone()
    if existing is not None:
        if existing["request_hash"] != request_hash:
            raise HTTPException(409, "Idempotency key was reused with different content")
        _, post = _load_review(conn, review_id, owner_id)
        return _review_envelope(
            existing, post, _request_id(request), replayed=True
        )

    fields = body.fields
    title = str(fields.get("title") or body.summary).strip()
    summary = str(fields.get("summary") or body.summary).strip()
    content_md = str(fields.get("contentMd") or fields.get("content_md") or "")
    tags_value = fields.get("tags") or []
    tags = [str(item) for item in tags_value] if isinstance(tags_value, list) else []
    field_refs = fields.get("sourceRefs") or fields.get("source_refs") or []
    source_refs = [*body.source_refs]
    if isinstance(field_refs, list):
        source_refs.extend(str(item) for item in field_refs)
    wanted_slug = str(fields.get("slug") or "").strip() or slugify(title)
    now = now_iso()
    post_cursor = conn.execute(
        """INSERT INTO posts
           (owner_id,slug,title,summary,content_md,content_html,tags,status,published_at,
            revision,previewed_revision,withdrawn_at,source_refs,validation_json,created_at,updated_at)
           VALUES (?,?,?,?,?,?,?,'draft',NULL,1,NULL,NULL,?,'{}',?,?) RETURNING id""",
        (
            owner_id,
            _unique_slug(conn, owner_id, wanted_slug, None),
            title,
            summary,
            content_md,
            render_markdown(content_md),
            tags_to_json(tags),
            json.dumps(list(dict.fromkeys(source_refs)), ensure_ascii=False),
            now,
            now,
        ),
    )
    post_id = inserted_id(post_cursor)
    conn.execute(
        """INSERT INTO garden_agent_reviews
           (id, owner_id, post_id, agent_id, intent, request_hash, status, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, ?)""",
        (review_id, owner_id, post_id, identity.agent_id, body.intent, request_hash, now, now),
    )
    review, post = _load_review(conn, review_id, owner_id)
    request.state.garden_actor_id = f"agent:{identity.agent_id}"
    _snapshot(
        conn, post, actor=request.state.garden_actor_id,
        correlation_id=request.state.operation_context.correlation_id,
    )
    _event(
        conn, post, from_state=None, to_state="draft", actor=request.state.garden_actor_id,
        correlation_id=request.state.operation_context.correlation_id,
        detail="idempotent Agent capture",
    )
    return _review_envelope(review, post, _request_id(request))


@router.post("/nexus/commands", operation_id="execute_nexus_garden_command")
def execute_nexus_garden_command(
    command: NexusGardenCommand,
    request: Request,
    authorization: str | None = Header(default=None),
    owner_id: str = Depends(content_owner_id),
    conn: sqlite3.Connection = Depends(get_db),
):
    created = create_review(
        command.arguments, request, authorization, command.command_id, owner_id, conn
    )
    fields = created["fields"]
    return {
        "protocol": "shadow.execution-result.v1",
        "command_id": command.command_id,
        "capability_ref": command.capability_ref,
        "operation_id": command.operation_id,
        "status": "committed",
        "result_kind": "draft",
        "resource_ref": created["reference"],
        "receipt_ref": f"shadow://garden/operations/{command.command_id}",
        "completed_at": created["created_at"],
        "replayed": bool(created["replayed"]),
        "summary": "文章草稿已保存。",
        "fields": fields,
    }


@router.get("/nexus/reviews", operation_id="list_nexus_garden_reviews")
def list_reviews(
    request: Request,
    authorization: str | None = Header(default=None),
    owner_id: str = Depends(content_owner_id),
    conn: sqlite3.Connection = Depends(get_db),
):
    identity = require_agent(_authorization(authorization), scope="garden.posts.review")
    reviews = conn.execute(
        """SELECT * FROM garden_agent_reviews
           WHERE owner_id=? AND agent_id=? AND status='pending' ORDER BY created_at""",
        (owner_id, identity.agent_id),
    ).fetchall()
    items = []
    for review in reviews:
        _, post = _load_review(conn, review["id"], owner_id)
        items.append(_review_envelope(review, post, _request_id(request)))
    return {
        "protocol": "shadow.review.v1",
        "items": items,
        "truncated": False,
        "trace_id": _request_id(request),
    }


@router.post(
    "/nexus/reviews/{review_id}/commit",
    operation_id="commit_nexus_garden_review",
)
def commit_review(
    review_id: str,
    request: Request,
    authorization: str | None = Header(default=None),
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=200),
    confirmation: str = Header(alias="X-Shadow-Confirmation"),
    owner_id: str = Depends(content_owner_id),
    conn: sqlite3.Connection = Depends(get_db),
):
    identity = require_agent(_authorization(authorization), scope="garden.posts.publish")
    review, post = _load_review(conn, review_id, owner_id)
    request.state.garden_actor_id = f"agent:{identity.agent_id}"
    binding = ConfirmationBinding(
        audience="garden",
        plugin_id="shadow-garden",
        capability_id="garden.posts.publish",
        tool_name="garden.posts.publish",
        effect="publish",
        arguments={"review_id": review_id},
        resource_uri=f"shadow://garden/reviews/{review_id}",
    )
    if review["status"] == "rejected":
        raise HTTPException(409, "Rejected Garden review cannot be published")
    replayed = review["status"] == "published"
    if not replayed:
        if post["status"] in {"draft", "revision"}:
            post, validation = preview_transition(conn, post, request=request)
            if not validation["valid"]:
                raise HTTPException(409, {"code": "preview_failed", "validation": validation})
        try:
            _confirmation_verifier().verify_and_consume(
                confirmation, binding, idempotency_key=idempotency_key
            )
        except ConfirmationError as exc:
            raise HTTPException(403, str(exc)) from exc
        post = publish_transition(conn, post, request=request)
        now = now_iso()
        conn.execute(
            "UPDATE garden_agent_reviews SET status='published',updated_at=? WHERE id=? AND owner_id=?",
            (now, review_id, owner_id),
        )
    review, post = _load_review(conn, review_id, owner_id)
    return _review_envelope(
        review,
        post,
        _request_id(request),
        receipt=f"shadow://garden/posts/{post['id']}",
        replayed=replayed,
    )


@router.post(
    "/nexus/reviews/{review_id}/reject",
    operation_id="reject_nexus_garden_review",
)
def reject_review(
    review_id: str,
    request: Request,
    authorization: str | None = Header(default=None),
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=200),
    owner_id: str = Depends(content_owner_id),
    conn: sqlite3.Connection = Depends(get_db),
):
    del idempotency_key
    identity = require_agent(_authorization(authorization), scope="garden.posts.review")
    review, post = _load_review(conn, review_id, owner_id)
    request.state.garden_actor_id = f"agent:{identity.agent_id}"
    if review["status"] == "published":
        raise HTTPException(409, "Published Garden review cannot be rejected")
    replayed = review["status"] == "rejected"
    if not replayed:
        conn.execute(
            "UPDATE garden_agent_reviews SET status='rejected',updated_at=? WHERE id=? AND owner_id=?",
            (now_iso(), review_id, owner_id),
        )
    review, post = _load_review(conn, review_id, owner_id)
    return _review_envelope(
        review, post, _request_id(request), replayed=replayed
    )
