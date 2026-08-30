"""Versioned Garden database migrations.

Run ``python -m app.migrations upgrade`` before starting a release. Every migration is
recorded with a checksum. The baseline safely adopts pre-migration Garden databases;
later revisions add only missing columns before recording the migration head.
"""
from __future__ import annotations

import argparse
import hashlib
import inspect
import json
from dataclasses import dataclass
from typing import Callable

from .config import settings
from .db import connect, is_pg, now_iso


class MigrationError(RuntimeError):
    pass


@dataclass(frozen=True)
class Migration:
    version: str
    description: str
    apply: Callable[[object], None]

    @property
    def checksum(self) -> str:
        source = inspect.getsource(self.apply)
        return hashlib.sha256(
            f"{self.version}\0{self.description}\0{source}".encode()
        ).hexdigest()


LEGACY_COLUMNS = """
  slug TEXT NOT NULL UNIQUE, title TEXT NOT NULL, summary TEXT NOT NULL DEFAULT '',
  content_md TEXT NOT NULL DEFAULT '', content_html TEXT NOT NULL DEFAULT '',
  tags TEXT NOT NULL DEFAULT '[]', status TEXT NOT NULL DEFAULT 'draft', published_at TEXT,
  views INTEGER NOT NULL DEFAULT 0, waters INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL
"""

LEGACY_TABLES = {
    "posts": LEGACY_COLUMNS,
    "projects": """
  name TEXT NOT NULL, description TEXT NOT NULL DEFAULT '', tags TEXT NOT NULL DEFAULT '[]',
  link TEXT NOT NULL DEFAULT '', repo TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'active',
  sort_order INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
""",
    "food": """
  title TEXT NOT NULL, emoji TEXT NOT NULL DEFAULT '🍽️', rating INTEGER NOT NULL DEFAULT 5,
  location TEXT NOT NULL DEFAULT '', review TEXT NOT NULL DEFAULT '', photo TEXT NOT NULL DEFAULT '',
  photos TEXT NOT NULL DEFAULT '[]', tags TEXT NOT NULL DEFAULT '[]', eaten_on TEXT NOT NULL DEFAULT '',
  lat DOUBLE PRECISION, lng DOUBLE PRECISION, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
""",
    "trips": """
  title TEXT NOT NULL, destination TEXT NOT NULL DEFAULT '', start_date TEXT NOT NULL DEFAULT '',
  end_date TEXT NOT NULL DEFAULT '', summary TEXT NOT NULL DEFAULT '', content_md TEXT NOT NULL DEFAULT '',
  content_html TEXT NOT NULL DEFAULT '', photos TEXT NOT NULL DEFAULT '[]', lat DOUBLE PRECISION,
  lng DOUBLE PRECISION, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
""",
    "moments": """
  title TEXT NOT NULL DEFAULT '', kind TEXT NOT NULL DEFAULT 'note', content_md TEXT NOT NULL DEFAULT '',
  content_html TEXT NOT NULL DEFAULT '', photos TEXT NOT NULL DEFAULT '[]',
  collections TEXT NOT NULL DEFAULT '[]', created_at TEXT NOT NULL, updated_at TEXT NOT NULL
""",
}


def _identity_pk() -> str:
    return (
        "id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,"
        if is_pg()
        else "id INTEGER PRIMARY KEY AUTOINCREMENT,"
    )


def _baseline(conn) -> None:
    pk = _identity_pk()
    for name, columns in LEGACY_TABLES.items():
        conn.execute(f"CREATE TABLE IF NOT EXISTS {name} ({pk}{columns})")
    for statement in (
        """CREATE TABLE IF NOT EXISTS about (
          id INTEGER PRIMARY KEY CHECK (id = 1), content_md TEXT NOT NULL DEFAULT '',
          content_html TEXT NOT NULL DEFAULT '', links TEXT NOT NULL DEFAULT '[]', updated_at TEXT NOT NULL)""",
        """CREATE TABLE IF NOT EXISTS asset_files (
          id TEXT PRIMARY KEY, asset_id TEXT NOT NULL UNIQUE, version_id TEXT NOT NULL,
          reference_id TEXT NOT NULL UNIQUE, url TEXT NOT NULL UNIQUE, original_filename TEXT NOT NULL,
          content_type TEXT NOT NULL, size_bytes INTEGER NOT NULL, created_at TEXT NOT NULL)""",
        """CREATE TABLE IF NOT EXISTS asset_uploads_pending (
          id TEXT PRIMARY KEY, upload_session_id TEXT NOT NULL UNIQUE, original_filename TEXT NOT NULL,
          content_type TEXT NOT NULL, size_bytes INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
          expires_at TEXT NOT NULL, asset_id TEXT UNIQUE, version_id TEXT, reference_id TEXT UNIQUE,
          url TEXT, created_at TEXT NOT NULL, completed_at TEXT)""",
        """CREATE TABLE IF NOT EXISTS garden_agent_reviews (
          id TEXT PRIMARY KEY, post_id BIGINT NOT NULL UNIQUE, agent_id TEXT NOT NULL, intent TEXT NOT NULL,
          request_hash TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'pending',
          created_at TEXT NOT NULL, updated_at TEXT NOT NULL)""",
    ):
        conn.execute(statement)


def _column_names(conn, table: str) -> set[str]:
    if is_pg():
        rows = conn.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name=?",
            (table,),
        ).fetchall()
        return {row["column_name"] for row in rows}
    return {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}


def _add_columns(conn, declarations: dict[str, dict[str, str]]) -> None:
    for table, columns in declarations.items():
        present = _column_names(conn, table)
        for name, declaration in columns.items():
            if name not in present:
                if is_pg():
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {name} {declaration}")
                else:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {declaration}")


def _legacy_additions(conn) -> None:
    _add_columns(
        conn,
        {
            "posts": {"views": "INTEGER NOT NULL DEFAULT 0", "waters": "INTEGER NOT NULL DEFAULT 0"},
            "food": {
                "lat": "DOUBLE PRECISION", "lng": "DOUBLE PRECISION",
                "photos": "TEXT NOT NULL DEFAULT '[]'",
            },
            "trips": {"lat": "DOUBLE PRECISION", "lng": "DOUBLE PRECISION"},
            "moments": {
                "title": "TEXT NOT NULL DEFAULT ''", "kind": "TEXT NOT NULL DEFAULT 'note'",
                "photos": "TEXT NOT NULL DEFAULT '[]'", "collections": "TEXT NOT NULL DEFAULT '[]'",
            },
            "garden_agent_reviews": {"request_hash": "TEXT NOT NULL DEFAULT ''"},
        },
    )


def _workflow(conn) -> None:
    owner_default = settings.content_owner_id.replace("'", "''")
    owner_decl = f"TEXT NOT NULL DEFAULT '{owner_default}'"
    _add_columns(
        conn,
        {
            table: {"owner_id": owner_decl}
            for table in (
                "posts", "projects", "food", "trips", "moments", "about",
                "asset_files", "asset_uploads_pending", "garden_agent_reviews",
            )
        },
    )
    _add_columns(
        conn,
        {
            "posts": {
                "revision": "INTEGER NOT NULL DEFAULT 1", "previewed_revision": "INTEGER",
                "withdrawn_at": "TEXT", "source_refs": "TEXT NOT NULL DEFAULT '[]'",
                "validation_json": "TEXT NOT NULL DEFAULT '{}'", "rediscover_after": "TEXT",
            }
        },
    )
    pk = _identity_pk()
    for statement in (
        f"""CREATE TABLE IF NOT EXISTS post_revisions ({pk}
          post_id BIGINT NOT NULL, owner_id TEXT NOT NULL, revision INTEGER NOT NULL,
          state TEXT NOT NULL, title TEXT NOT NULL, slug TEXT NOT NULL, summary TEXT NOT NULL,
          content_md TEXT NOT NULL, content_html TEXT NOT NULL, tags TEXT NOT NULL,
          source_refs TEXT NOT NULL DEFAULT '[]', validation_json TEXT NOT NULL DEFAULT '{{}}',
          actor_id TEXT NOT NULL, correlation_id TEXT NOT NULL, created_at TEXT NOT NULL,
          UNIQUE(post_id, revision))""",
        f"""CREATE TABLE IF NOT EXISTS post_events ({pk}
          post_id BIGINT NOT NULL, owner_id TEXT NOT NULL, from_state TEXT,
          to_state TEXT NOT NULL, revision INTEGER NOT NULL, actor_id TEXT NOT NULL,
          correlation_id TEXT NOT NULL, detail TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL)""",
        """CREATE TABLE IF NOT EXISTS garden_suggestions (
          id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, subject_uri TEXT NOT NULL,
          kind TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'active', snoozed_until TEXT,
          created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
          UNIQUE(owner_id, subject_uri, kind))""",
    ):
        conn.execute(statement)
    for statement in (
        "CREATE INDEX IF NOT EXISTS idx_posts_owner_status ON posts(owner_id, status)",
        "CREATE INDEX IF NOT EXISTS idx_post_revisions_owner_post ON post_revisions(owner_id, post_id, revision)",
        "CREATE INDEX IF NOT EXISTS idx_post_events_owner_post ON post_events(owner_id, post_id, id)",
    ):
        conn.execute(statement)


MIGRATIONS = (
    Migration("20260830_0001", "adopt legacy Garden schema", _baseline),
    Migration("20260830_0002", "adopt historical additive columns", _legacy_additions),
    Migration("20260830_0003", "owner-scoped traceable publishing workflow", _workflow),
)
HEAD = MIGRATIONS[-1].version


def _ensure_ledger(conn) -> None:
    conn.execute(
        """CREATE TABLE IF NOT EXISTS schema_migrations (
          version TEXT PRIMARY KEY, description TEXT NOT NULL, checksum TEXT NOT NULL,
          applied_at TEXT NOT NULL)"""
    )


def upgrade(conn=None) -> list[str]:
    owned = conn is None
    conn = conn or connect()
    applied_now: list[str] = []
    try:
        _ensure_ledger(conn)
        known = {row["version"]: row for row in conn.execute("SELECT * FROM schema_migrations")}
        for migration in MIGRATIONS:
            recorded = known.get(migration.version)
            if recorded:
                if recorded["checksum"] != migration.checksum:
                    raise MigrationError(f"migration checksum changed: {migration.version}")
                continue
            migration.apply(conn)
            conn.execute(
                "INSERT INTO schema_migrations (version, description, checksum, applied_at) VALUES (?, ?, ?, ?)",
                (migration.version, migration.description, migration.checksum, now_iso()),
            )
            applied_now.append(migration.version)
        conn.commit()
        return applied_now
    except Exception:
        rollback = getattr(conn, "rollback", None)
        if rollback:
            rollback()
        raise
    finally:
        if owned:
            conn.close()


def assert_current(conn) -> None:
    try:
        rows = conn.execute("SELECT version, checksum FROM schema_migrations").fetchall()
    except Exception as exc:
        raise MigrationError(
            "Garden schema is not migrated; run `python -m app.migrations upgrade`"
        ) from exc
    applied = {row["version"]: row["checksum"] for row in rows}
    for migration in MIGRATIONS:
        if applied.get(migration.version) != migration.checksum:
            raise MigrationError(
                f"Garden schema is behind {HEAD}; run `python -m app.migrations upgrade`"
            )


def status() -> dict[str, object]:
    conn = connect()
    try:
        _ensure_ledger(conn)
        applied = {row["version"] for row in conn.execute("SELECT version FROM schema_migrations")}
        return {
            "head": HEAD,
            "current": HEAD if HEAD in applied else None,
            "pending": [m.version for m in MIGRATIONS if m.version not in applied],
        }
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Garden schema migration runner")
    parser.add_argument("command", choices=("upgrade", "status"))
    args = parser.parse_args()
    result = {"applied": upgrade(), **status()} if args.command == "upgrade" else status()
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
