"""SQLite 连接与建表。每个请求一个连接，成功即提交。"""
import json
import sqlite3
from datetime import datetime, timezone
from typing import Iterator, List

from .config import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS posts (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  slug         TEXT NOT NULL UNIQUE,
  title        TEXT NOT NULL,
  summary      TEXT NOT NULL DEFAULT '',
  content_md   TEXT NOT NULL DEFAULT '',
  content_html TEXT NOT NULL DEFAULT '',
  tags         TEXT NOT NULL DEFAULT '[]',
  status       TEXT NOT NULL DEFAULT 'draft',
  published_at TEXT,
  views        INTEGER NOT NULL DEFAULT 0,
  created_at   TEXT NOT NULL,
  updated_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS projects (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  name        TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  tags        TEXT NOT NULL DEFAULT '[]',
  link        TEXT NOT NULL DEFAULT '',
  repo        TEXT NOT NULL DEFAULT '',
  status      TEXT NOT NULL DEFAULT 'active',
  sort_order  INTEGER NOT NULL DEFAULT 0,
  created_at  TEXT NOT NULL,
  updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS food (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  title      TEXT NOT NULL,
  emoji      TEXT NOT NULL DEFAULT '🍽️',
  rating     INTEGER NOT NULL DEFAULT 5,
  location   TEXT NOT NULL DEFAULT '',
  review     TEXT NOT NULL DEFAULT '',
  photo      TEXT NOT NULL DEFAULT '',
  tags       TEXT NOT NULL DEFAULT '[]',
  eaten_on   TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS trips (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  title        TEXT NOT NULL,
  destination  TEXT NOT NULL DEFAULT '',
  start_date   TEXT NOT NULL DEFAULT '',
  end_date     TEXT NOT NULL DEFAULT '',
  summary      TEXT NOT NULL DEFAULT '',
  content_md   TEXT NOT NULL DEFAULT '',
  content_html TEXT NOT NULL DEFAULT '',
  photos       TEXT NOT NULL DEFAULT '[]',
  created_at   TEXT NOT NULL,
  updated_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS moments (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  content_md   TEXT NOT NULL DEFAULT '',
  content_html TEXT NOT NULL DEFAULT '',
  created_at   TEXT NOT NULL,
  updated_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS about (
  id           INTEGER PRIMARY KEY CHECK (id = 1),
  content_md   TEXT NOT NULL DEFAULT '',
  content_html TEXT NOT NULL DEFAULT '',
  links        TEXT NOT NULL DEFAULT '[]',
  updated_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
  token      TEXT PRIMARY KEY,
  created_at TEXT NOT NULL,
  expires_at TEXT NOT NULL
);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect() -> sqlite3.Connection:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    # check_same_thread=False：FastAPI 的同步依赖与端点可能在线程池的不同线程执行；
    # 每个请求独享一个连接、顺序使用，跨线程是安全的。
    conn = sqlite3.connect(settings.db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def _migrate(conn: sqlite3.Connection) -> None:
    """已有库的增量迁移：老表补新列。"""
    post_cols = {r["name"] for r in conn.execute("PRAGMA table_info(posts)")}
    if "views" not in post_cols:
        conn.execute("ALTER TABLE posts ADD COLUMN views INTEGER NOT NULL DEFAULT 0")


def init_db() -> None:
    conn = connect()
    try:
        conn.executescript(SCHEMA)
        _migrate(conn)
        conn.commit()
    finally:
        conn.close()


def get_db() -> Iterator[sqlite3.Connection]:
    """FastAPI 依赖：请求结束且无异常时提交。"""
    conn = connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def tags_to_json(tags: List[str]) -> str:
    return json.dumps([t.strip() for t in tags if t.strip()], ensure_ascii=False)


def tags_from_json(raw: str) -> List[str]:
    try:
        value = json.loads(raw or "[]")
        return value if isinstance(value, list) else []
    except ValueError:
        return []
