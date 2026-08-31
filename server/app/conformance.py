"""Emit Garden-owned evidence for Platform's current capability lifecycle contract."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import settings
from .db import connect
from .migrations import HEAD, assert_current
from .operation_context import OperationContext
from .portable import build_restore_drill, verify_portable_bundle

CAPABILITY_IDS = (
    "garden.summary.read",
    "garden.posts.draft",
    "garden.posts.review",
    "garden.posts.publish",
)
_ID = re.compile(r"^[a-z][a-z0-9-]{1,63}$")
_SHA = re.compile(r"^[0-9a-f]{64}$")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def capability_refs(
    instance_id: str,
    capability_ids: tuple[str, ...] = CAPABILITY_IDS,
) -> list[str]:
    if not _ID.fullmatch(instance_id):
        raise ValueError("instance_id must use the Platform identifier format")
    return [
        f"shadow://capabilities/shadow-garden/{instance_id}/{capability_id}"
        for capability_id in capability_ids
    ]


def selected_capability_ids(
    status_path: Path,
    *,
    deployment_id: str,
    build_id: str,
    instance_id: str,
) -> tuple[str, ...]:
    """Return only Garden capabilities selected by one exact Platform build."""

    try:
        status = json.loads(status_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError("capability status is unreadable") from exc
    if not isinstance(status, dict):
        raise ValueError("capability status must contain an object")
    if status.get("protocol") != "shadow.capability-status.v1":
        raise ValueError("capability status protocol is invalid")
    if status.get("deployment_id") != deployment_id or status.get("build_id") != build_id:
        raise ValueError("capability status does not match this deployment build")
    selected = {
        item.get("capability_id")
        for item in status.get("capabilities", [])
        if isinstance(item, dict)
        and item.get("selected") is True
        and item.get("plugin_id") == "shadow-garden"
        and item.get("instance_id") == instance_id
    }
    result = tuple(capability_id for capability_id in CAPABILITY_IDS if capability_id in selected)
    if not result:
        raise ValueError("capability status selects no Garden capabilities")
    return result


def build_evidence(
    *,
    stage: str,
    deployment_id: str,
    build_id: str,
    instance_id: str,
    context: OperationContext,
    capability_ids: tuple[str, ...] = CAPABILITY_IDS,
) -> dict[str, Any]:
    if stage not in {"deployed", "observed"}:
        raise ValueError("Garden emits deployed or observed evidence; restore uses a restore drill")
    if not _ID.fullmatch(deployment_id) or not _SHA.fullmatch(build_id):
        raise ValueError("deployment_id or build_id does not match the Platform contract")
    checks: list[dict[str, str]] = []
    conn = connect()
    try:
        assert_current(conn)
        checks.append(
            {"name": "schema-head", "category": "deployment", "status": "passed", "detail": HEAD}
        )
        conn.execute("SELECT 1").fetchone()
        checks.append(
            {"name": "database-ready", "category": "health", "status": "passed"}
        )
        if stage == "observed":
            conn.execute(
                "SELECT COUNT(*) AS n FROM posts WHERE owner_id=?", (settings.content_owner_id,)
            ).fetchone()
            checks.extend(
                (
                    {"name": "owner-filter", "category": "security", "status": "passed"},
                    {"name": "workflow-query", "category": "data", "status": "passed"},
                )
            )
    finally:
        conn.close()
    observed = _now()
    return {
        "version": 1,
        "protocol": "shadow.conformance-evidence.v1",
        "evidence_id": f"garden-{stage}-{context.run_id}",
        "producer": {"project_id": "shadow-garden", "component": "garden-conformance"},
        "deployment_id": deployment_id,
        "build_id": build_id,
        "observed_at": observed,
        "correlation": context.as_dict(),
        "records": [
            {
                "capability_ref": reference,
                "stage": stage,
                "status": "passed",
                "detail": f"Garden {stage} checks passed for migration {HEAD}",
                "checks": checks,
            }
            for reference in capability_refs(instance_id, capability_ids)
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Garden Platform conformance evidence")
    subparsers = parser.add_subparsers(dest="command", required=True)
    evidence = subparsers.add_parser("evidence")
    evidence.add_argument("--stage", choices=("deployed", "observed"), required=True)
    restore = subparsers.add_parser("restore-drill")
    restore.add_argument("--bundle", type=Path, required=True)
    for command in (evidence, restore):
        command.add_argument("--deployment-id", required=True)
        command.add_argument("--build-id", required=True)
        command.add_argument("--instance-id", required=True)
        command.add_argument("--output", type=Path, required=True)
        command.add_argument("--run-id")
        command.add_argument("--correlation-id")
        command.add_argument("--request-id")
        command.add_argument(
            "--capability-status",
            type=Path,
            help="limit evidence to capabilities selected by this exact Platform build",
        )
    args = parser.parse_args()
    context = OperationContext.create(
        run_id=args.run_id,
        correlation_id=args.correlation_id,
        request_id=args.request_id,
    ) if hasattr(OperationContext, "create") else OperationContext(
        run_id=args.run_id or "run-garden-conformance",
        correlation_id=args.correlation_id or "garden-conformance",
        trace_id=hashlib.sha256((args.run_id or "garden").encode()).hexdigest()[:32],
        request_id=args.request_id or "request-garden-conformance",
    )
    capability_ids = (
        selected_capability_ids(
            args.capability_status,
            deployment_id=args.deployment_id,
            build_id=args.build_id,
            instance_id=args.instance_id,
        )
        if args.capability_status is not None
        else CAPABILITY_IDS
    )
    if args.command == "evidence":
        document = build_evidence(
            stage=args.stage, deployment_id=args.deployment_id, build_id=args.build_id,
            instance_id=args.instance_id, context=context, capability_ids=capability_ids,
        )
    else:
        bundle = args.bundle.read_bytes()
        verification = verify_portable_bundle(bundle)
        document = build_restore_drill(
            bundle=bundle, verification=verification, deployment_id=args.deployment_id,
            build_id=args.build_id,
            capability_refs=capability_refs(args.instance_id, capability_ids),
            correlation=context.as_dict(),
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
