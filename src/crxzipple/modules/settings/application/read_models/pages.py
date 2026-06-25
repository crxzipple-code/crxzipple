from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from crxzipple.modules.settings.application.action_policy import (
    KIND_DESCRIPTIONS,
    KIND_TITLES,
    SUPPORTED_KINDS,
    kind_action_allowed,
    kind_actions,
    kind_policy_payload,
    overview_actions,
    resource_actions,
    resource_tabs,
)
from crxzipple.modules.settings.application.read_models.runtime_defaults import (
    runtime_defaults_read_model,
    runtime_defaults_validation_payload,
)
from crxzipple.modules.settings.application.redaction import redact_value
from crxzipple.modules.settings.application.services import SettingsQueryService
from crxzipple.modules.settings.domain import (
    SettingsActionAudit,
    SettingsNotFoundError,
    SettingsResource,
    SettingsResourceVersion,
)


def overview_payload(query: SettingsQueryService) -> dict[str, Any]:
    counts = resource_counts(query)
    total_resources = sum(
        count for kind, count in counts.items() if kind != "audit-logs"
    )
    missing = [
        kind
        for kind in ("access-assets", "event-registry", "backup-restore")
        if counts.get(kind, 0) == 0
    ]
    health_status = "warning" if missing else "ready"
    audits = tuple(query.list_audits())
    return {
        "resource": "overview",
        "title": "Settings Overview",
        "description": "Settings governance read model backed by the Settings application service.",
        "status": health_status,
        "health": {
            "status": health_status,
            "degraded": False,
            "source": "settings_application",
            "missing_resource_kinds": missing,
        },
        "counts": {
            "resources": total_resources,
            "kinds": len(SUPPORTED_KINDS),
            "audits": len(audits),
        },
        "resource_counts": [
            {
                "id": kind,
                "label": KIND_TITLES[kind],
                "value": count,
                "tone": "warning" if count == 0 else "success",
                "route": f"/settings/{kind}",
            }
            for kind, count in counts.items()
        ],
        "contract_summary": key_value_section(
            "Ownership",
            {
                "truth_owner": "settings",
                "provider": "settings_application",
                "bootstrap_source": "core.config.Settings",
            },
        ),
        "configuration_summary": key_value_section(
            "Configuration",
            {
                "resources": total_resources,
                "resource_kinds": len(SUPPORTED_KINDS),
                "audits": len(audits),
            },
        ),
        "configuration_health": {
            "title": "Configuration Health",
            "columns": ["Resource", "Count", "Status"],
            "rows": [
                {
                    "Resource": KIND_TITLES[kind],
                    "Count": count,
                    "Status": "pending import" if count == 0 else "ready",
                }
                for kind, count in counts.items()
            ],
        },
        "recent_changes": audit_table(audits[-10:]),
        "configuration_distribution": {
            "title": "Configuration Distribution",
            "kind": "bar",
            "series": [
                {"label": KIND_TITLES[kind], "value": count}
                for kind, count in counts.items()
            ],
        },
        "configuration_issues": {
            "title": "Configuration Issues",
            "columns": ["Resource", "Issue", "Severity"],
            "rows": [
                {
                    "Resource": KIND_TITLES[kind],
                    "Issue": "No Settings-owned resources imported yet.",
                    "Severity": "warning",
                }
                for kind in missing
            ],
        },
        "configuration_inheritance": key_value_section(
            "Resolution",
            {
                "default_source": "bootstrap",
                "workspace_override": "not_configured",
                "environment_override": "settings_overrides",
            },
        ),
        "sources_versioning": key_value_section(
            "Sources",
            {
                "bootstrap": "core.config.Settings",
                "versions": sum(len(query.list_versions(resource.id)) for resource in query.list_resources()),
                "latest_audit": audits[-1].id if audits else None,
            },
        ),
        "quick_actions": overview_actions(),
        "useful_links": [
            {"label": KIND_TITLES[kind], "route": f"/settings/{kind}"}
            for kind in SUPPORTED_KINDS
        ],
    }


def kind_payload(
    query: SettingsQueryService,
    kind: str,
    *,
    limit: int,
    offset: int,
) -> dict[str, Any]:
    resources = tuple(query.list_resources(resource_kind=kind))
    selected = resources[offset : offset + limit]
    summaries = [resource_summary_payload(query, resource) for resource in selected]
    audits = kind_audits(query, kind)
    policy = kind_policy_payload(kind)
    return {
        "resource": kind,
        "kind": kind,
        "title": KIND_TITLES[kind],
        "description": KIND_DESCRIPTIONS[kind],
        **policy,
        "status": "empty" if not resources else "ready",
        "health": {
            "status": "empty" if not resources else "ready",
            "degraded": False,
            "source": "settings_application",
        },
        "tabs": resource_tabs(kind),
        "active_tab": "overview",
        "resources": summaries,
        "list": {
            "title": KIND_TITLES[kind],
            "columns": ["Name", "ID", "Status", "Enabled", "Source", "Version"],
            "rows": [_resource_row(summary) for summary in summaries],
            "total": len(resources),
            "limit": limit,
            "offset": offset,
        },
        "detail": resource_detail_payload(query, selected[0]) if selected else None,
        "summary": [
            key_value_section(
                "Summary",
                {
                    "resources": len(resources),
                    "source": "settings_application",
                    "kind": kind,
                },
            ),
        ],
        "effective_configuration": effective_configuration_payload(kind, summaries),
        "validation": validation_payload("valid" if resources else "unknown"),
        "impact": impact_payload(kind, selected[0].id if selected else None),
        "audit": audit_summary_payload(audits),
        "danger_zone": danger_zone_payload(kind),
        "actions": kind_actions(kind),
    }


def resource_detail_payload(
    query: SettingsQueryService,
    resource: SettingsResource,
) -> dict[str, Any]:
    summary = resource_summary_payload(query, resource)
    versions = query.list_versions(resource.id)
    latest = versions[-1] if versions else None
    audits = resource_audits(query, resource)
    policy = kind_policy_payload(resource.resource_kind)
    effective_config = (
        summary["effective_config"]
        if isinstance(summary["effective_config"], Mapping)
        else {}
    )
    validation = (
        runtime_defaults_validation_payload(effective_config)
        if resource.resource_kind == "runtime-defaults"
        else validation_from_version(latest)
    )
    payload = {
        "resource": resource.resource_kind,
        "kind": resource.resource_kind,
        "id": resource.id,
        "resource_id": resource.id,
        "title": resource.display_name or resource.id,
        **policy,
        "status": resource.status.value,
        "enabled": resource.enabled,
        "version": latest.version_number if latest is not None else None,
        "source": latest.source if latest is not None else None,
        "payload": redact_value(latest.payload if latest is not None else {}),
        "effective_config": summary["effective_config"],
        "resolution": summary["resolution"],
        "detail": {
            "id": resource.id,
            "title": resource.display_name or resource.id,
            "status": resource.status.value,
            "tabs": resource_tabs(resource.resource_kind),
            "active_tab": "overview",
            "sections": [
                key_value_section(
                    "Resource",
                    {
                        "kind": resource.resource_kind,
                        "owner_module": resource.owner_module,
                        "version": latest.version_number if latest else None,
                        "enabled": resource.enabled,
                    },
                ),
            ],
            "actions": resource_actions(resource.resource_kind, resource.id),
        },
        "validation": validation,
        "impact": impact_payload(resource.resource_kind, resource.id),
        "audit": audit_summary_payload(audits),
        "actions": resource_actions(resource.resource_kind, resource.id),
        "versions": [redact_value(version.to_payload()) for version in versions],
    }
    if resource.resource_kind == "runtime-defaults":
        payload["runtime_defaults"] = runtime_defaults_read_model(
            resource=resource,
            latest=latest,
            effective_config=effective_config,
            summary=summary,
        )
    return payload


def resource_summary_payload(
    query: SettingsQueryService,
    resource: SettingsResource,
) -> dict[str, Any]:
    versions = query.list_versions(resource.id)
    latest = versions[-1] if versions else None
    resolution = query.get_effective(resource.id)
    effective_config = redact_value(deepcopy(resolution.effective_value))
    return {
        "id": resource.id,
        "resource_id": resource.id,
        "kind": resource.resource_kind,
        "display_name": resource.display_name or resource.id,
        "status": resource.status.value,
        "enabled": resource.enabled,
        "source": latest.source if latest is not None else "resource_state",
        "version": latest.version_number if latest is not None else None,
        "updated_at": format_datetime(resource.updated_at),
        **kind_policy_payload(resource.resource_kind),
        "metadata": redact_value(resource.metadata),
        "effective_config": effective_config,
        "resolution": resolution_payload(resolution),
    }


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


def resource_counts(query: SettingsQueryService) -> dict[str, int]:
    return {
        kind: (
            len(query.list_audits())
            if kind == "audit-logs"
            else len(query.list_resources(resource_kind=kind))
        )
        for kind in SUPPORTED_KINDS
    }


def resource_by_kind(
    query: SettingsQueryService,
    kind: str,
    resource_id: str,
) -> SettingsResource | None:
    try:
        resource = query.get_resource(resource_id)
    except SettingsNotFoundError:
        return None
    if resource.resource_kind != kind:
        return None
    return resource


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


def resolution_payload(resolution: Any) -> dict[str, Any]:
    sources = [_source_payload(source) for source in resolution.sources]
    primary = sources[0] if sources else {"kind": "resource_state", "name": "resource_state"}
    return {
        "resource_ref": {
            "kind": resolution.resource.resource_kind,
            "id": resolution.resource.resource_id,
        },
        "value": redact_value(resolution.effective_value),
        "source": primary,
        "sources": sources,
        "override_trace": [_source_payload(source) for source in resolution.overrides],
        "snapshot_id": resolution.snapshot_id,
        "resolved_at": resolution.resolved_at,
        "validation": dict(resolution.validation),
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


def key_value_section(title: str, values: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "title": title,
        "items": [
            {"label": key.replace("_", " ").title(), "value": value}
            for key, value in values.items()
        ],
    }


def validation_from_version(version: SettingsResourceVersion | None) -> dict[str, Any]:
    if version is None:
        return validation_payload("unknown")
    status_value = "valid" if version.validation.ok else "invalid"
    payload = validation_payload(status_value)
    payload["result"] = version.validation.to_payload()
    payload["last_validated_at"] = format_datetime(version.created_at)
    return payload


def format_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _resource_row(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "Name": summary["display_name"],
        "ID": summary["resource_id"],
        "Status": summary["status"],
        "Enabled": summary["enabled"],
        "Source": summary["source"],
        "Version": summary["version"],
    }


def _source_payload(source: Any) -> dict[str, Any]:
    metadata = dict(source.metadata)
    source_name = str(metadata.get("source") or source.source_id)
    source_kind = "bootstrap" if source_name.startswith("bootstrap:") else source.source_kind
    return {
        "kind": source_kind,
        "name": source_name,
        "source_id": source.source_id,
        "version": metadata.get("version_number"),
        "version_id": source.version_id,
        "override_id": source.override_id,
        "applied": source.applied,
        "reason": source.reason,
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
