from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from crxzipple.modules.settings.application.action_policy import (
    KIND_TITLES,
    kind_action_allowed,
)
from crxzipple.modules.settings.domain import SettingsResourceVersion


def key_value_section(title: str, values: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "title": title,
        "items": [
            {"label": key.replace("_", " ").title(), "value": value}
            for key, value in values.items()
        ],
    }


def validation_payload(status_value: str) -> dict[str, Any]:
    return {
        "status": status_value,
        "checks": {
            "title": "Validation",
            "columns": ["Check", "Result"],
            "rows": [
                {
                    "Check": "schema",
                    "Result": "pass" if status_value in {"valid", "unknown"} else status_value,
                },
                {
                    "Check": "secrets",
                    "Result": "redacted",
                },
            ],
        },
        "last_validated_at": format_datetime(datetime.now(timezone.utc)),
        "actions": [],
    }


def validation_from_version(version: SettingsResourceVersion | None) -> dict[str, Any]:
    if version is None:
        return validation_payload("unknown")
    status_value = "valid" if version.validation.ok else "invalid"
    payload = validation_payload(status_value)
    payload["result"] = version.validation.to_payload()
    payload["last_validated_at"] = format_datetime(version.created_at)
    return payload


def impact_payload(kind: str, resource_id: str | None) -> dict[str, Any]:
    payload = {
        "level": "info",
        "summary": key_value_section(
            "Impact",
            {
                "resource": kind,
                "resource_id": resource_id,
                "estimated_runtime_mutation": "requires consuming module refresh",
            },
        ),
        "affected_entities": {
            "title": "Affected Entities",
            "columns": ["Entity", "Effect"],
            "rows": [],
        },
        "dry_run_action": None,
    }
    if kind_action_allowed(kind, "dry-run"):
        payload["dry_run_action"] = {
            "id": f"settings.{kind}.dry_run",
            "label": "Dry Run",
            "method": "POST",
            "route": (
                f"/settings/{kind}/{resource_id}/actions/dry-run"
                if resource_id
                else f"/settings/{kind}/actions/dry-run"
            ),
            "requires_reason": False,
            "risk": "low",
        }
    return payload


def effective_configuration_payload(
    kind: str,
    resources: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "title": f"{KIND_TITLES[kind]} Effective Configuration",
        "values": {
            "title": "Effective Values",
            "columns": ["Resource", "Source", "Version"],
            "rows": [
                {
                    "Resource": item["resource_id"],
                    "Source": item["source"],
                    "Version": item["version"],
                }
                for item in resources
            ],
        },
        "resolution_trace": {
            "title": "Resolution Trace",
            "columns": ["Resource", "Source", "Overrides"],
            "rows": [
                {
                    "Resource": item["resource_id"],
                    "Source": item["source"],
                    "Overrides": len(item["resolution"]["override_trace"]),
                }
                for item in resources
            ],
        },
        "export_actions": [],
    }


def danger_zone_payload(kind: str) -> dict[str, Any]:
    actions = [
        {
            "id": f"settings.{kind}.{action}",
            "label": action.replace("-", " ").title(),
            "method": "POST",
            "route": f"/settings/{kind}/actions/{action}",
            "requires_reason": True,
            "risk": "medium",
        }
        for action in ("publish", "rollback", "enable", "disable")
        if kind_action_allowed(kind, action)
    ]
    return {
        "title": "Danger Zone",
        "description": "Publishing, rollback, enable, and disable actions require an audit reason.",
        "actions": actions,
    }


def format_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
