import sqlite3
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing_extensions import Literal

from ..auth import require_admin
from ..db import get_db, now_iso, tags_from_json, tags_to_json

router = APIRouter(prefix="/api/projects", tags=["projects"])

STATUS_LABELS = {"active": "进行中", "done": "已完成", "planned": "计划中", "paused": "搁置"}


class ProjectIn(BaseModel):
    name: str = Field(min_length=1)
    description: str = ""
    tags: List[str] = []
    link: str = ""
    repo: str = ""
    status: Literal["active", "done", "planned", "paused"] = "active"
    sort_order: int = 0


def _serialize(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "name": row["name"],
        "description": row["description"],
        "tags": tags_from_json(row["tags"]),
        "link": row["link"],
        "repo": row["repo"],
        "status": row["status"],
        "status_label": STATUS_LABELS.get(row["status"], row["status"]),
        "sort_order": row["sort_order"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


@router.get("")
def list_projects(conn: sqlite3.Connection = Depends(get_db)):
    rows = conn.execute(
        "SELECT * FROM projects ORDER BY sort_order DESC, created_at DESC"
    ).fetchall()
    return {"items": [_serialize(r) for r in rows]}


@router.post("", dependencies=[Depends(require_admin)], status_code=201)
def create_project(body: ProjectIn, conn: sqlite3.Connection = Depends(get_db)):
    now = now_iso()
    cur = conn.execute(
        """INSERT INTO projects (name, description, tags, link, repo, status,
                                 sort_order, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            body.name, body.description, tags_to_json(body.tags), body.link,
            body.repo, body.status, body.sort_order, now, now,
        ),
    )
    row = conn.execute("SELECT * FROM projects WHERE id = ?", (cur.lastrowid,)).fetchone()
    return _serialize(row)


@router.put("/{project_id}", dependencies=[Depends(require_admin)])
def update_project(
    project_id: int, body: ProjectIn, conn: sqlite3.Connection = Depends(get_db)
):
    cur = conn.execute(
        """UPDATE projects SET name=?, description=?, tags=?, link=?, repo=?,
                               status=?, sort_order=?, updated_at=?
           WHERE id=?""",
        (
            body.name, body.description, tags_to_json(body.tags), body.link,
            body.repo, body.status, body.sort_order, now_iso(), project_id,
        ),
    )
    if cur.rowcount == 0:
        raise HTTPException(404, "项目不存在")
    row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    return _serialize(row)


@router.delete("/{project_id}", dependencies=[Depends(require_admin)])
def delete_project(project_id: int, conn: sqlite3.Connection = Depends(get_db)):
    cur = conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
    if cur.rowcount == 0:
        raise HTTPException(404, "项目不存在")
    return {"ok": True}
