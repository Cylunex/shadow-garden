import sqlite3
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..auth import require_admin
from ..db import get_db, inserted_id, now_iso, tags_from_json, tags_to_json

router = APIRouter(prefix="/api/food", tags=["food"])


class FoodIn(BaseModel):
    title: str = Field(min_length=1)
    emoji: str = "🍽️"
    rating: int = Field(default=5, ge=1, le=5)
    location: str = ""
    review: str = ""
    photo: str = ""
    tags: List[str] = []
    eaten_on: str = ""   # YYYY-MM-DD，留空表示未填


def _serialize(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "title": row["title"],
        "emoji": row["emoji"],
        "rating": row["rating"],
        "location": row["location"],
        "review": row["review"],
        "photo": row["photo"],
        "tags": tags_from_json(row["tags"]),
        "eaten_on": row["eaten_on"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


@router.get("")
def list_food(conn: sqlite3.Connection = Depends(get_db)):
    rows = conn.execute(
        "SELECT * FROM food ORDER BY CASE WHEN eaten_on = '' THEN created_at ELSE eaten_on END DESC"
    ).fetchall()
    return {"items": [_serialize(r) for r in rows]}


@router.post("", dependencies=[Depends(require_admin)], status_code=201)
def create_food(body: FoodIn, conn: sqlite3.Connection = Depends(get_db)):
    now = now_iso()
    cur = conn.execute(
        """INSERT INTO food (title, emoji, rating, location, review, photo,
                             tags, eaten_on, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) RETURNING id""",
        (
            body.title, body.emoji, body.rating, body.location, body.review,
            body.photo, tags_to_json(body.tags), body.eaten_on, now, now,
        ),
    )
    row = conn.execute("SELECT * FROM food WHERE id = ?", (inserted_id(cur),)).fetchone()
    return _serialize(row)


@router.put("/{food_id}", dependencies=[Depends(require_admin)])
def update_food(food_id: int, body: FoodIn, conn: sqlite3.Connection = Depends(get_db)):
    cur = conn.execute(
        """UPDATE food SET title=?, emoji=?, rating=?, location=?, review=?,
                           photo=?, tags=?, eaten_on=?, updated_at=?
           WHERE id=?""",
        (
            body.title, body.emoji, body.rating, body.location, body.review,
            body.photo, tags_to_json(body.tags), body.eaten_on, now_iso(), food_id,
        ),
    )
    if cur.rowcount == 0:
        raise HTTPException(404, "记录不存在")
    row = conn.execute("SELECT * FROM food WHERE id = ?", (food_id,)).fetchone()
    return _serialize(row)


@router.delete("/{food_id}", dependencies=[Depends(require_admin)])
def delete_food(food_id: int, conn: sqlite3.Connection = Depends(get_db)):
    cur = conn.execute("DELETE FROM food WHERE id = ?", (food_id,))
    if cur.rowcount == 0:
        raise HTTPException(404, "记录不存在")
    return {"ok": True}
