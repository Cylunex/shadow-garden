from __future__ import annotations

import json

import pytest

from app.conformance import selected_capability_ids


def test_selected_capability_ids_follow_exact_platform_build(tmp_path):
    build_id = "a" * 64
    status = {
        "protocol": "shadow.capability-status.v1",
        "deployment_id": "shadow-production",
        "build_id": build_id,
        "capabilities": [
            {
                "plugin_id": "shadow-garden",
                "instance_id": "garden-production",
                "capability_id": "garden.summary.read",
                "selected": True,
            },
            {
                "plugin_id": "shadow-garden",
                "instance_id": "garden-production",
                "capability_id": "garden.posts.review",
                "selected": False,
            },
        ],
    }
    path = tmp_path / "status.json"
    path.write_text(json.dumps(status), encoding="utf-8")

    assert selected_capability_ids(
        path,
        deployment_id="shadow-production",
        build_id=build_id,
        instance_id="garden-production",
    ) == ("garden.summary.read",)


def test_selected_capability_ids_reject_cross_build_status(tmp_path):
    path = tmp_path / "status.json"
    path.write_text(
        json.dumps(
            {
                "protocol": "shadow.capability-status.v1",
                "deployment_id": "shadow-production",
                "build_id": "b" * 64,
                "capabilities": [],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="does not match"):
        selected_capability_ids(
            path,
            deployment_id="shadow-production",
            build_id="a" * 64,
            instance_id="garden-production",
        )
