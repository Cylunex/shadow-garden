import json
import sqlite3
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing_extensions import Literal

from ..auth import content_owner_id, require_admin, require_content_editor
from ..db import get_db, inserted_id, now_iso
from ..rendering import render_markdown

router = APIRouter(prefix="/api/moments", tags=["moments"])


class MomentIn(BaseModel):
    title: str = ""
    kind: Literal["note", "scenery"] = "note"
    content_md: str = ""
    photos: List[str] = []
    collections: List[str] = []


class MomentPatch(BaseModel):
    title: Optional[str] = None
    kind: Optional[Literal["note", "scenery"]] = None
    content_md: Optional[str] = None
    photos: Optional[List[str]] = None
    collections: Optional[List[str]] = None


def _json_list(raw: str) -> list:
    try:
        value = json.loads(raw or "[]")
        return value if isinstance(value, list) else []
    except (TypeError, ValueError):
        return []


def _validate(body: MomentIn) -> None:
    if not (body.title.strip() or body.content_md.strip() or body.photos):
        raise HTTPException(422, "标题、内容或照片至少填写一项")


def _serialize(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "title": row["title"],
        "kind": row["kind"],
        "content_md": row["content_md"],
        "content_html": row["content_html"],
        "photos": _json_list(row["photos"]),
        "collections": _json_list(row["collections"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


@router.get("")
def list_moments(
    limit: int = Query(default=50, ge=1, le=200),
    owner_id: str = Depends(content_owner_id),
    conn: sqlite3.Connection = Depends(get_db),
):
    rows = conn.execute(
        "SELECT * FROM moments WHERE owner_id=? ORDER BY created_at DESC,id DESC LIMIT ?", (owner_id, limit)
    ).fetchall()
    return {"items": [_serialize(r) for r in rows]}


@router.post("", dependencies=[Depends(require_content_editor)], status_code=201)
def create_moment(body: MomentIn, owner_id: str = Depends(content_owner_id), conn: sqlite3.Connection = Depends(get_db)):
    _validate(body)
    now = now_iso()
    cur = conn.execute(
        """INSERT INTO moments (owner_id, title, kind, content_md, content_html, photos,
                                collections, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) RETURNING id""",
        (
            owner_id, body.title, body.kind, body.content_md, render_markdown(body.content_md),
            json.dumps(body.photos, ensure_ascii=False),
            json.dumps(body.collections, ensure_ascii=False), now, now,
        ),
    )
    row = conn.execute("SELECT * FROM moments WHERE id=? AND owner_id=?", (inserted_id(cur), owner_id)).fetchone()
    return _serialize(row)


def _update_moment(moment_id: int, body: MomentIn, owner_id: str, conn) -> dict:
    _validate(body)
    cur = conn.execute(
        """UPDATE moments SET title=?, kind=?, content_md=?, content_html=?,
                              photos=?, collections=?, updated_at=? WHERE id=? AND owner_id=?""",
        (
            body.title, body.kind, body.content_md, render_markdown(body.content_md),
            json.dumps(body.photos, ensure_ascii=False),
            json.dumps(body.collections, ensure_ascii=False), now_iso(), moment_id, owner_id,
        ),
    )
    if cur.rowcount == 0:
        raise HTTPException(404, "日常记录不存在")
    row = conn.execute("SELECT * FROM moments WHERE id=? AND owner_id=?", (moment_id, owner_id)).fetchone()
    return _serialize(row)


@router.put("/{moment_id}", dependencies=[Depends(require_content_editor)])
def update_moment(moment_id: int, body: MomentIn, owner_id: str = Depends(content_owner_id), conn: sqlite3.Connection = Depends(get_db)):
    return _update_moment(moment_id, body, owner_id, conn)


@router.patch("/{moment_id}", dependencies=[Depends(require_content_editor)])
def patch_moment(
    moment_id: int,
    body: MomentPatch,
    owner_id: str = Depends(content_owner_id),
    conn: sqlite3.Connection = Depends(get_db),
):
    row = conn.execute("SELECT * FROM moments WHERE id=? AND owner_id=?", (moment_id, owner_id)).fetchone()
    if row is None:
        raise HTTPException(404, "日常记录不存在")
    current = _serialize(row)
    current.update(body.model_dump(exclude_unset=True))
    return _update_moment(moment_id, MomentIn(**current), owner_id, conn)


@router.delete("/{moment_id}", dependencies=[Depends(require_admin)])
def delete_moment(moment_id: int, owner_id: str = Depends(content_owner_id), conn: sqlite3.Connection = Depends(get_db)):
    cur = conn.execute("DELETE FROM moments WHERE id=? AND owner_id=?", (moment_id, owner_id))
    if cur.rowcount == 0:
        raise HTTPException(404, "日常记录不存在")
    return {"ok": True}
