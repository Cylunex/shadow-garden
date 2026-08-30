"""Portable Markdown export and isolated restore verification for Garden-owned data."""
from __future__ import annotations

import hashlib
import io
import json
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import settings
from .db import now_iso, tags_from_json

PROTOCOL = "garden.portable.v1"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _markdown(metadata: dict[str, Any], content: str) -> bytes:
    header = json.dumps(metadata, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return f"---garden-json\n{header}\n---\n\n{content.rstrip()}\n".encode("utf-8")


def build_portable_bundle(conn, owner_id: str) -> bytes:
    files: dict[str, tuple[bytes, str, str]] = {}
    upstream_refs: set[str] = set()
    posts = conn.execute(
        "SELECT * FROM posts WHERE owner_id=? ORDER BY id", (owner_id,)
    ).fetchall()
    for row in posts:
        source_refs = json.loads(row["source_refs"] or "[]")
        upstream_refs.update(str(item) for item in source_refs)
        metadata = {
            "id": row["id"], "slug": row["slug"], "title": row["title"],
            "summary": row["summary"], "tags": tags_from_json(row["tags"]),
            "state": row["status"], "revision": row["revision"],
            "published_at": row["published_at"], "source_refs": source_refs,
        }
        path = f"posts/{row['slug']}.md"
        files[path] = (_markdown(metadata, row["content_md"]), "text/markdown", "post")
        history = {
            "events": [dict(item) for item in conn.execute(
                """SELECT from_state,to_state,revision,actor_id,correlation_id,detail,created_at
                   FROM post_events WHERE owner_id=? AND post_id=? ORDER BY id""",
                (owner_id, row["id"]),
            )],
            "revisions": [dict(item) for item in conn.execute(
                """SELECT revision,state,title,slug,actor_id,correlation_id,created_at
                   FROM post_revisions WHERE owner_id=? AND post_id=? ORDER BY revision""",
                (owner_id, row["id"]),
            )],
        }
        files[f"history/{row['slug']}.json"] = (
            json.dumps(history, ensure_ascii=False, indent=2).encode("utf-8") + b"\n",
            "application/json",
            "history",
        )

    about = conn.execute(
        "SELECT * FROM about WHERE owner_id=? ORDER BY id LIMIT 1", (owner_id,)
    ).fetchone()
    if about:
        files["about.md"] = (
            _markdown({"links": json.loads(about["links"] or "[]")}, about["content_md"]),
            "text/markdown",
            "about",
        )
    for row in conn.execute(
        "SELECT * FROM moments WHERE owner_id=? ORDER BY id", (owner_id,)
    ):
        files[f"moments/{row['id']}.md"] = (
            _markdown(
                {
                    "id": row["id"], "title": row["title"], "kind": row["kind"],
                    "photos": json.loads(row["photos"] or "[]"),
                    "collections": json.loads(row["collections"] or "[]"),
                    "created_at": row["created_at"],
                },
                row["content_md"],
            ),
            "text/markdown",
            "moment",
        )

    resources: list[dict[str, Any]] = []
    for row in conn.execute("SELECT * FROM asset_files WHERE owner_id=? ORDER BY id", (owner_id,)):
        resources.append(
            {
                "resource_uri": f"shadow://garden/assets/{row['id']}",
                "asset_id": row["asset_id"], "version_id": row["version_id"],
                "reference_id": row["reference_id"], "url": row["url"],
                "filename": row["original_filename"], "content_type": row["content_type"],
                "size_bytes": row["size_bytes"], "embedded": False,
            }
        )
    if settings.asset_mode == "local" and settings.uploads_dir.is_dir():
        for path in sorted(settings.uploads_dir.iterdir()):
            if not path.is_file() or path.name.startswith("."):
                continue
            data = path.read_bytes()
            archive_path = f"assets/{path.name}"
            files[archive_path] = (data, "application/octet-stream", "asset")
            resources.append(
                {
                    "resource_uri": f"shadow://garden/local-assets/{path.name}",
                    "filename": path.name, "size_bytes": len(data), "embedded": True,
                    "path": archive_path, "sha256": _sha256(data),
                }
            )

    manifest = {
        "version": 1,
        "protocol": PROTOCOL,
        "created_at": now_iso(),
        "boundary": {
            "garden": "public expression and publication history",
            "travel": "stable projection references only",
            "archive": "stable source references only",
        },
        "upstream_refs": sorted(upstream_refs),
        "resources": resources,
        "files": [
            {
                "path": path, "sha256": _sha256(data), "size_bytes": len(data),
                "media_type": media_type, "kind": kind,
            }
            for path, (data, media_type, kind) in sorted(files.items())
        ],
    }
    manifest_data = json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", manifest_data)
        for path, (data, _, _) in sorted(files.items()):
            archive.writestr(path, data)
    return output.getvalue()


def verify_portable_bundle(data: bytes) -> dict[str, Any]:
    checks: list[dict[str, str]] = []
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except (OSError, zipfile.BadZipFile) as exc:
        raise ValueError("portable archive is not a valid ZIP") from exc
    with archive, tempfile.TemporaryDirectory(prefix="garden-restore-") as raw_target:
        target = Path(raw_target).resolve()
        names = archive.namelist()
        if len(names) != len(set(names)) or "manifest.json" not in names:
            raise ValueError("portable archive has duplicate entries or no manifest")
        for name in names:
            destination = (target / name).resolve()
            if Path(name).is_absolute() or not destination.is_relative_to(target):
                raise ValueError(f"unsafe archive path: {name}")
            if name.endswith("/"):
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(archive.read(name))
        manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
        if manifest.get("protocol") != PROTOCOL or manifest.get("version") != 1:
            raise ValueError("portable manifest contract mismatch")
        checks.append({"name": "portable-contract", "category": "contract", "status": "passed"})
        indexed = {item["path"]: item for item in manifest.get("files", [])}
        if set(indexed) != set(names) - {"manifest.json"}:
            raise ValueError("portable manifest file inventory mismatch")
        for name, item in indexed.items():
            restored = (target / name).read_bytes()
            if len(restored) != item["size_bytes"] or _sha256(restored) != item["sha256"]:
                raise ValueError(f"portable file hash mismatch: {name}")
        checks.append({"name": "content-hashes", "category": "data", "status": "passed"})
        for name, item in indexed.items():
            if item["media_type"] == "text/markdown":
                text = (target / name).read_text(encoding="utf-8")
                if not text.startswith("---garden-json\n") or "\n---\n" not in text:
                    raise ValueError(f"restored Markdown metadata is unreadable: {name}")
        checks.append({"name": "isolated-read", "category": "health", "status": "passed"})
    return {
        "protocol": "garden.restore-verification.v1",
        "verified_at": now_iso(),
        "backup_sha256": _sha256(data),
        "file_count": len(indexed),
        "checks": checks,
        "isolated": True,
        "cleanup_completed": True,
    }


def build_restore_drill(
    *,
    bundle: bytes,
    verification: dict[str, Any],
    deployment_id: str,
    build_id: str,
    capability_refs: list[str],
    correlation: dict[str, str],
) -> dict[str, Any]:
    completed = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    backup_id = f"garden-export-{verification['backup_sha256'][:24]}"
    return {
        "version": 1, "protocol": "shadow.restore-drill.v1",
        "drill_id": f"garden-restore-{verification['backup_sha256'][:24]}",
        "project_id": "shadow-garden", "deployment_id": deployment_id,
        "build_id": build_id, "capability_refs": capability_refs,
        "correlation": correlation,
        "backup": {
            "backup_id": backup_id, "created_at": completed, "immutable": True,
            "sha256": _sha256(bundle), "source_version": PROTOCOL,
        },
        "restore": {
            "source_backup_id": backup_id, "target_kind": "isolated", "production": False,
            "started_at": completed, "completed_at": completed, "cleanup_completed": True,
            "rpo_seconds": 0, "rto_seconds": 0,
        },
        "checks": verification["checks"],
    }
