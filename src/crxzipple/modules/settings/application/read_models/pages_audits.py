from __future__ import annotations

from typing import Any

from crxzipple.modules.settings.application.action_policy import (
    KIND_DESCRIPTIONS,
    KIND_TITLES,
    kind_policy_payload,
    resource_tabs,
)
from crxzipple.modules.settings.application.read_models.pages_common import (
    key_value_section,
    validation_payload,
)
from crxzipple.modules.settings.application.redaction import redact_value
from crxzipple.modules.settings.application.services import SettingsQueryService
from crxzipple.modules.settings.domain import SettingsActionAudit, SettingsResource


def audit_page(
    query: SettingsQueryService,
    *,
    limit: int,
    offset: int,
) -> dict[str, Any]:
    audits = tuple(reversed(tuple(query.list_audits())))
    selected = audits[offset : offset + limit]
    return {
        "resource": "audit-logs",
        "kind": "audit-logs",
        "title": KIND_TITLES["audit-logs"],
        "description": KIND_DESCRIPTIONS["audit-logs"],
        **kind_policy_payload("audit-logs"),
        "status": "ready",
        "health": {
            "status": "ready",
            "degraded": False,
            "source": "settings_application",
        },
        "tabs": resource_tabs("audit-logs"),
        "active_tab": "overview",
        "resources": [audit_payload(audit) for audit in selected],
        "list": {
            "title": "Settings Action Audits",
            "columns": ["Audit ID", "Action", "Target", "Status", "Actor", "Reason"],
            "rows": [_audit_row(audit) for audit in selected],
            "total": len(audits),
            "limit": limit,
            "offset": offset,
        },
        "detail": audit_payload(selected[0]) if selected else None,
        "summary": [
            key_value_section("Audit", {"records": len(audits), "reason_required": True}),
        ],
        "validation": validation_payload("valid"),
        "audit": audit_summary_payload(tuple(reversed(selected))),
        "actions": [],
    }


def kind_audits(query: SettingsQueryService, kind: str) -> tuple[SettingsActionAudit, ...]:
    return tuple(audit for audit in query.list_audits() if audit.target_type == kind)


def resource_audits(
    query: SettingsQueryService,
    resource: SettingsResource,
) -> tuple[SettingsActionAudit, ...]:
    return tuple(
        audit
        for audit in query.list_audits()
        if audit.target_type == resource.resource_kind and audit.target_id == resource.id
    )


def audit_by_id(query: SettingsQueryService, audit_id: str) -> SettingsActionAudit | None:
    for audit in query.list_audits():
        if audit.id == audit_id:
            return audit
    return None


def audit_summary_payload(audits: tuple[SettingsActionAudit, ...]) -> dict[str, Any]:
    return {
        "recent_changes": audit_table(audits[-10:]),
        "audit_history_route": "/settings/audit-logs",
        "reason_required": True,
    }


def audit_table(
    audits: tuple[SettingsActionAudit, ...] | list[SettingsActionAudit],
) -> dict[str, Any]:
    return {
        "title": "Recent Settings Changes",
        "columns": ["Audit ID", "Action", "Target", "Status", "Actor", "Reason"],
        "rows": [_audit_row(audit) for audit in reversed(tuple(audits))],
    }


def audit_payload(audit: SettingsActionAudit) -> dict[str, Any]:
    raw = audit.to_payload()
    return {
        "audit_id": raw["id"],
        "id": raw["id"],
        "action": _action_name_from_type(raw["action_type"]),
        "action_type": raw["action_type"],
        "kind": raw["target_type"],
        "resource_id": raw["target_id"],
        "actor": raw["actor"],
        "reason": raw["reason"],
        "risk": raw["risk"],
        "dry_run": raw["action_type"].endswith(".dry_run"),
        "status": raw["status"],
        "request_metadata": redact_value(raw["request_metadata"]),
        "result": redact_value(raw["result"]),
        "error": redact_value(raw["error"]),
        "created_at": raw["created_at"],
        "completed_at": raw["updated_at"],
    }


def _audit_row(audit: SettingsActionAudit) -> dict[str, Any]:
    payload = audit_payload(audit)
    return {
        "Audit ID": payload["audit_id"],
        "Action": payload["action"],
        "Target": f"{payload['kind']}/{payload['resource_id'] or '*'}",
        "Status": payload["status"],
        "Actor": payload["actor"],
        "Reason": payload["reason"] or "",
    }


def _action_name_from_type(action_type: str) -> str:
    return action_type.rsplit(".", maxsplit=1)[-1].replace("_", "-")
