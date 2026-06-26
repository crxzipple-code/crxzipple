from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from crxzipple.modules.settings.application.action_policy import (
    KIND_DESCRIPTIONS,
    KIND_TITLES,
    kind_actions,
    kind_policy_payload,
    resource_actions,
    resource_tabs,
)
from crxzipple.modules.settings.application.read_models.runtime_defaults import (
    runtime_defaults_read_model,
    runtime_defaults_validation_payload,
)
from crxzipple.modules.settings.application.read_models.pages_audits import (
    audit_summary_payload,
    kind_audits,
    resource_audits,
)
from crxzipple.modules.settings.application.read_models.pages_common import (
    danger_zone_payload,
    effective_configuration_payload,
    format_datetime,
    impact_payload,
    key_value_section,
    validation_from_version,
    validation_payload,
)
from crxzipple.modules.settings.application.redaction import redact_value
from crxzipple.modules.settings.application.services import SettingsQueryService
from crxzipple.modules.settings.domain import (
    SettingsNotFoundError,
    SettingsResource,
)


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
