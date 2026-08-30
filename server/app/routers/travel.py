import json
import sqlite3
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..auth import content_owner_id, require_admin, require_content_editor
from ..db import get_db, inserted_id, now_iso
from ..rendering import render_markdown

router = APIRouter(prefix="/api/trips", tags=["travel"])


class TripIn(BaseModel):
    title: str = Field(min_length=1)
    destination: str = ""
    start_date: str = ""   # YYYY-MM-DD
    end_date: str = ""
    summary: str = ""
    content_md: str = ""
    photos: List[str] = []


class TripPatch(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1)
    destination: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    summary: Optional[str] = None
    content_md: Optional[str] = None
    photos: Optional[List[str]] = None


def _serialize(row: sqlite3.Row, with_content: bool = False) -> dict:
    trip = {
        "id": row["id"],
        "title": row["title"],
        "destination": row["destination"],
        "start_date": row["start_date"],
        "end_date": row["end_date"],
        "summary": row["summary"],
        "photos": json.loads(row["photos"] or "[]"),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }
    if with_content:
        trip["content_md"] = row["content_md"]
        trip["content_html"] = row["content_html"]
    return trip


@router.get("")
def list_trips(owner_id: str = Depends(content_owner_id), conn: sqlite3.Connection = Depends(get_db)):
    rows = conn.execute(
        "SELECT * FROM trips WHERE owner_id=? ORDER BY CASE WHEN start_date = '' THEN created_at ELSE start_date END DESC", (owner_id,)
    ).fetchall()
    return {"items": [_serialize(r) for r in rows]}


@router.get("/{trip_id}")
def get_trip(trip_id: int, owner_id: str = Depends(content_owner_id), conn: sqlite3.Connection = Depends(get_db)):
    row = conn.execute("SELECT * FROM trips WHERE id=? AND owner_id=?", (trip_id, owner_id)).fetchone()
    if row is None:
        raise HTTPException(404, "游记不存在")
    return _serialize(row, with_content=True)


@router.post("", dependencies=[Depends(require_content_editor)], status_code=201)
def create_trip(body: TripIn, owner_id: str = Depends(content_owner_id), conn: sqlite3.Connection = Depends(get_db)):
    now = now_iso()
    cur = conn.execute(
        """INSERT INTO trips (owner_id, title, destination, start_date, end_date, summary,
                              content_md, content_html, photos, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) RETURNING id""",
        (
            owner_id, body.title, body.destination, body.start_date, body.end_date,
            body.summary, body.content_md, render_markdown(body.content_md),
            json.dumps(body.photos, ensure_ascii=False), now, now,
        ),
    )
    row = conn.execute("SELECT * FROM trips WHERE id=? AND owner_id=?", (inserted_id(cur), owner_id)).fetchone()
    return _serialize(row, with_content=True)


def _update_trip(trip_id: int, body: TripIn, owner_id: str, conn: sqlite3.Connection) -> dict:
    cur = conn.execute(
        """UPDATE trips SET title=?, destination=?, start_date=?, end_date=?,
                            summary=?, content_md=?, content_html=?, photos=?, updated_at=?
           WHERE id=? AND owner_id=?""",
        (
            body.title, body.destination, body.start_date, body.end_date,
            body.summary, body.content_md, render_markdown(body.content_md),
            json.dumps(body.photos, ensure_ascii=False), now_iso(), trip_id, owner_id,
        ),
    )
    if cur.rowcount == 0:
        raise HTTPException(404, "游记不存在")
    row = conn.execute("SELECT * FROM trips WHERE id=? AND owner_id=?", (trip_id, owner_id)).fetchone()
    return _serialize(row, with_content=True)


@router.put("/{trip_id}", dependencies=[Depends(require_content_editor)])
def update_trip(trip_id: int, body: TripIn, owner_id: str = Depends(content_owner_id), conn: sqlite3.Connection = Depends(get_db)):
    return _update_trip(trip_id, body, owner_id, conn)


@router.patch("/{trip_id}", dependencies=[Depends(require_content_editor)])
def patch_trip(trip_id: int, body: TripPatch, owner_id: str = Depends(content_owner_id), conn: sqlite3.Connection = Depends(get_db)):
    row = conn.execute("SELECT * FROM trips WHERE id=? AND owner_id=?", (trip_id, owner_id)).fetchone()
    if row is None:
        raise HTTPException(404, "游记不存在")
    current = _serialize(row, with_content=True)
    current.update(body.model_dump(exclude_unset=True))
    return _update_trip(trip_id, TripIn(**current), owner_id, conn)


@router.delete("/{trip_id}", dependencies=[Depends(require_admin)])
def delete_trip(trip_id: int, owner_id: str = Depends(content_owner_id), conn: sqlite3.Connection = Depends(get_db)):
    cur = conn.execute("DELETE FROM trips WHERE id=? AND owner_id=?", (trip_id, owner_id))
    if cur.rowcount == 0:
        raise HTTPException(404, "游记不存在")
    return {"ok": True}
