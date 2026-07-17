"""数据库层：默认 SQLite（本地开发/测试零依赖），配置 GARDEN_DB_URL 后走 PostgreSQL（生产）。

两个后端共用同一套 SQL 写法：
- 占位符统一写 '?'，PG 连接包装层自动替换为 %s
- 行对象都支持 row["col"] 取值，也能 dict(row)
- INSERT 一律 `RETURNING id` 拿新主键（SQLite ≥ 3.35 支持）
"""
import json
import sqlite3
from datetime import datetime, timezone
from typing import Iterator, List

from .config import settings

_COLUMNS = """
  slug         TEXT NOT NULL UNIQUE,
  title        TEXT NOT NULL,
  summary      TEXT NOT NULL DEFAULT '',
  content_md   TEXT NOT NULL DEFAULT '',
  content_html TEXT NOT NULL DEFAULT '',
  tags         TEXT NOT NULL DEFAULT '[]',
  status       TEXT NOT NULL DEFAULT 'draft',
  published_at TEXT,
  views        INTEGER NOT NULL DEFAULT 0,
  waters       INTEGER NOT NULL DEFAULT 0,
  created_at   TEXT NOT NULL,
  updated_at   TEXT NOT NULL
"""

_TABLES = {
    "posts": _COLUMNS,
    "projects": """
  name        TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  tags        TEXT NOT NULL DEFAULT '[]',
  link        TEXT NOT NULL DEFAULT '',
  repo        TEXT NOT NULL DEFAULT '',
  status      TEXT NOT NULL DEFAULT 'active',
  sort_order  INTEGER NOT NULL DEFAULT 0,
  created_at  TEXT NOT NULL,
  updated_at  TEXT NOT NULL
""",
    "food": """
  title      TEXT NOT NULL,
  emoji      TEXT NOT NULL DEFAULT '🍽️',
  rating     INTEGER NOT NULL DEFAULT 5,
  location   TEXT NOT NULL DEFAULT '',
  review     TEXT NOT NULL DEFAULT '',
  photo      TEXT NOT NULL DEFAULT '',
  tags       TEXT NOT NULL DEFAULT '[]',
  eaten_on   TEXT NOT NULL DEFAULT '',
  lat        DOUBLE PRECISION,
  lng        DOUBLE PRECISION,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
""",
    "trips": """
  title        TEXT NOT NULL,
  destination  TEXT NOT NULL DEFAULT '',
  start_date   TEXT NOT NULL DEFAULT '',
  end_date     TEXT NOT NULL DEFAULT '',
  summary      TEXT NOT NULL DEFAULT '',
  content_md   TEXT NOT NULL DEFAULT '',
  content_html TEXT NOT NULL DEFAULT '',
  photos       TEXT NOT NULL DEFAULT '[]',
  lat          DOUBLE PRECISION,
  lng          DOUBLE PRECISION,
  created_at   TEXT NOT NULL,
  updated_at   TEXT NOT NULL
""",
    "moments": """
  content_md   TEXT NOT NULL DEFAULT '',
  content_html TEXT NOT NULL DEFAULT '',
  created_at   TEXT NOT NULL,
  updated_at   TEXT NOT NULL
""",
}

_FIXED_TABLES = """
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
)
"""


def _schema(pg: bool) -> List[str]:
    pk = ("id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY," if pg
          else "id INTEGER PRIMARY KEY AUTOINCREMENT,")
    statements = [
        f"CREATE TABLE IF NOT EXISTS {name} ({pk}{cols})"
        for name, cols in _TABLES.items()
    ]
    statements += [s for s in _FIXED_TABLES.split(";") if s.strip()]
    return statements


def is_pg() -> bool:
    return settings.db_url.startswith("postgres")


class _PgConnection:
    """让 psycopg 连接用起来像 sqlite3：? 占位符、dict 行、同名方法。"""

    def __init__(self, url: str):
        import psycopg
        from psycopg.rows import dict_row

        self._conn = psycopg.connect(url, row_factory=dict_row)

    def execute(self, sql: str, params=()):
        return self._conn.execute(sql.replace("?", "%s"), params)

    def commit(self) -> None:
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect():
    if is_pg():
        return _PgConnection(settings.db_url)
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    # check_same_thread=False：FastAPI 的同步依赖与端点可能在线程池的不同线程执行；
    # 每个请求独享一个连接、顺序使用，跨线程是安全的。
    conn = sqlite3.connect(settings.db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


_MIGRATIONS = [
    ("posts", "views", "INTEGER NOT NULL DEFAULT 0"),
    ("posts", "waters", "INTEGER NOT NULL DEFAULT 0"),
    # lat/lng：地图功能已下线，列保留以免丢已录入的数据
    ("food", "lat", "DOUBLE PRECISION"),
    ("food", "lng", "DOUBLE PRECISION"),
    ("trips", "lat", "DOUBLE PRECISION"),
    ("trips", "lng", "DOUBLE PRECISION"),
]


def _migrate(conn) -> None:
    """已有库的增量迁移：老表补新列（幂等）。"""
    if is_pg():
        for table, col, decl in _MIGRATIONS:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {col} {decl}")
        return
    for table, col, decl in _MIGRATIONS:
        cols = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
        if col not in cols:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")


def init_db() -> None:
    conn = connect()
    try:
        for stmt in _schema(is_pg()):
            conn.execute(stmt)
        _migrate(conn)
        conn.commit()
    finally:
        conn.close()


def get_db() -> Iterator:
    """FastAPI 依赖：请求结束且无异常时提交。"""
    conn = connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def inserted_id(cursor) -> int:
    """配合 INSERT ... RETURNING id 使用。"""
    return cursor.fetchone()["id"]


def tags_to_json(tags: List[str]) -> str:
    return json.dumps([t.strip() for t in tags if t.strip()], ensure_ascii=False)


def tags_from_json(raw: str) -> List[str]:
    try:
        value = json.loads(raw or "[]")
        return value if isinstance(value, list) else []
    except ValueError:
        return []
