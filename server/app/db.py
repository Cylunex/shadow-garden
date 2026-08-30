"""Small database adapter shared by SQLite and PostgreSQL.

Schema changes deliberately live in :mod:`app.migrations`. Application startup only
verifies the recorded migration head; it never improvises ``ALTER TABLE`` statements.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Iterator, List

from .config import settings


def is_pg() -> bool:
    return settings.db_url.startswith("postgres")


class _PgConnection:
    def __init__(self, url: str):
        import psycopg
        from psycopg.rows import dict_row

        self._conn = psycopg.connect(url, row_factory=dict_row)

    def execute(self, sql: str, params=()):
        return self._conn.execute(sql.replace("?", "%s"), params)

    def commit(self) -> None:
        self._conn.commit()

    def rollback(self) -> None:
        self._conn.rollback()

    def close(self) -> None:
        self._conn.close()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect():
    if is_pg():
        return _PgConnection(settings.db_url)
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(settings.db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def require_schema_current() -> None:
    from .migrations import assert_current

    conn = connect()
    try:
        assert_current(conn)
    finally:
        conn.close()


def get_db() -> Iterator:
    conn = connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        rollback = getattr(conn, "rollback", None)
        if rollback:
            rollback()
        raise
    finally:
        conn.close()


def inserted_id(cursor) -> int:
    return cursor.fetchone()["id"]


def tags_to_json(tags: List[str]) -> str:
    return json.dumps([t.strip() for t in tags if t.strip()], ensure_ascii=False)


def tags_from_json(raw: str) -> List[str]:
    try:
        value = json.loads(raw or "[]")
        return [str(item) for item in value] if isinstance(value, list) else []
    except (TypeError, ValueError):
        return []
