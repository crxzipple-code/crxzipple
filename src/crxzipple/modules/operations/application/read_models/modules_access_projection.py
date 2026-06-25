from __future__ import annotations

from typing import Any

from crxzipple.modules.operations.application.read_models.modules_helpers import (
    as_dict,
    s,
)


def setup_available_count(targets: list[dict[str, Any]]) -> int:
    return sum(1 for target in targets if bool(target.get("setup_available")))


def access_target_row(target: dict[str, Any]) -> dict[str, str]:
    metadata = as_dict(target.get("metadata"))
    checks = [
        check
        for requirement_set in target.get("requirement_sets", [])
        if isinstance(requirement_set, dict)
        for check in requirement_set.get("checks", [])
        if isinstance(check, dict)
    ]
    first_missing = next(
        (check for check in checks if not bool(check.get("ready"))), None
    )
    status = (
        "Ready"
        if bool(target.get("ready"))
        else s(first_missing.get("status") if first_missing else "Missing")
    )
    return {
        "id": s(target.get("resource_id")),
        "key": s(target.get("display_name") or target.get("resource_id")),
        "name": s(target.get("display_name") or target.get("resource_id")),
        "asset": s(target.get("display_name") or target.get("resource_id")),
        "kind": s(metadata.get("asset_kind") or target.get("resource_type")),
        "status": status,
        "ready": s(target.get("ready")),
        "required_by": s(metadata.get("usage_types")),
        "affected": s(metadata.get("usage_count")),
        "impact": "High" if not bool(target.get("ready")) else "Low",
        "last_failed_at": "-",
        "setup_available": s(target.get("setup_available")),
        "actions": "Setup" if bool(target.get("setup_available")) else "Open",
    }
