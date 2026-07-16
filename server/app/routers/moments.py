import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ..auth import require_admin
from ..db import get_db, inserted_id, now_iso
from ..rendering import render_markdown

router = APIRouter(prefix="/api/moments", tags=["moments"])


class MomentIn(BaseModel):
    content_md: str = Field(min_length=1)


def _serialize(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "content_md": row["content_md"],
        "content_html": row["content_html"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


@router.get("")
def list_moments(
    limit: int = Query(default=50, ge=1, le=200),
    conn: sqlite3.Connection = Depends(get_db),
):
    rows = conn.execute(
        "SELECT * FROM moments ORDER BY created_at DESC, id DESC LIMIT ?", (limit,)
    ).fetchall()
    return {"items": [_serialize(r) for r in rows]}


@router.post("", dependencies=[Depends(require_admin)], status_code=201)
def create_moment(body: MomentIn, conn: sqlite3.Connection = Depends(get_db)):
    now = now_iso()
    cur = conn.execute(
        "INSERT INTO moments (content_md, content_html, created_at, updated_at) VALUES (?, ?, ?, ?) RETURNING id",
        (body.content_md, render_markdown(body.content_md), now, now),
    )
    row = conn.execute("SELECT * FROM moments WHERE id = ?", (inserted_id(cur),)).fetchone()
    return _serialize(row)


@router.put("/{moment_id}", dependencies=[Depends(require_admin)])
def update_moment(moment_id: int, body: MomentIn, conn: sqlite3.Connection = Depends(get_db)):
    cur = conn.execute(
        "UPDATE moments SET content_md=?, content_html=?, updated_at=? WHERE id=?",
        (body.content_md, render_markdown(body.content_md), now_iso(), moment_id),
    )
    if cur.rowcount == 0:
        raise HTTPException(404, "说说不存在")
    row = conn.execute("SELECT * FROM moments WHERE id = ?", (moment_id,)).fetchone()
    return _serialize(row)


@router.delete("/{moment_id}", dependencies=[Depends(require_admin)])
def delete_moment(moment_id: int, conn: sqlite3.Connection = Depends(get_db)):
    cur = conn.execute("DELETE FROM moments WHERE id = ?", (moment_id,))
    if cur.rowcount == 0:
        raise HTTPException(404, "说说不存在")
    return {"ok": True}
