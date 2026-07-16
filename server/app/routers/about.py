import json
import sqlite3
from typing import List

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..auth import require_admin
from ..db import get_db, now_iso
from ..rendering import render_markdown

router = APIRouter(prefix="/api/about", tags=["about"])

DEFAULT_MD = "**Cylunex**，业余开发者。这里还没写自我介绍，去后台补一段吧。"


class LinkItem(BaseModel):
    label: str
    url: str


class AboutIn(BaseModel):
    content_md: str = ""
    links: List[LinkItem] = []


def _serialize(row: sqlite3.Row) -> dict:
    return {
        "content_md": row["content_md"],
        "content_html": row["content_html"],
        "links": json.loads(row["links"] or "[]"),
        "updated_at": row["updated_at"],
    }


def _ensure_row(conn: sqlite3.Connection) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM about WHERE id = 1").fetchone()
    if row is None:
        conn.execute(
            "INSERT INTO about (id, content_md, content_html, links, updated_at) VALUES (1, ?, ?, '[]', ?)",
            (DEFAULT_MD, render_markdown(DEFAULT_MD), now_iso()),
        )
        row = conn.execute("SELECT * FROM about WHERE id = 1").fetchone()
    return row


@router.get("")
def get_about(conn: sqlite3.Connection = Depends(get_db)):
    return _serialize(_ensure_row(conn))


@router.put("", dependencies=[Depends(require_admin)])
def update_about(body: AboutIn, conn: sqlite3.Connection = Depends(get_db)):
    _ensure_row(conn)
    conn.execute(
        "UPDATE about SET content_md=?, content_html=?, links=?, updated_at=? WHERE id=1",
        (
            body.content_md,
            render_markdown(body.content_md),
            json.dumps([l.model_dump() for l in body.links], ensure_ascii=False),
            now_iso(),
        ),
    )
    return _serialize(conn.execute("SELECT * FROM about WHERE id = 1").fetchone())
