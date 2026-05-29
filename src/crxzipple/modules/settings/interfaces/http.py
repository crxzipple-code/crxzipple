from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from enum import Enum
import re
from pathlib import Path
from typing import Annotated, Any, Literal
from urllib.parse import SplitResult, urlsplit, urlunsplit

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from crxzipple.interfaces.runtime_container import AppContainer, AppKey
from crxzipple.interfaces.http.dependencies import get_container
from crxzipple.modules.access.application.importer import AccessSettingsBootstrapImporter
from crxzipple.modules.settings.application import (
    CreateSettingsResourceInput,
    PublishSettingsVersionInput,
    RollbackSettingsResourceInput,
    SettingsActionService,
    SettingsQueryService,
    UpdateSettingsResourceInput,
    import_core_settings_resources,
)
from crxzipple.modules.settings.domain import (
    SettingsActionAudit,
    SettingsAlreadyExistsError,
    SettingsError,
    SettingsNotFoundError,
    SettingsResource,
    SettingsResourceVersion,
)


router = APIRouter()

SettingsActionName = Literal[
    "dry-run",
    "validate",
    "publish",
    "rollback",
    "enable",
    "disable",
    "create",
    "update",
]

_WRITE_ACTIONS = frozenset(
    {"publish", "rollback", "enable", "disable", "create", "update"},
)
_ALL_ACTIONS = (
    "dry-run",
    "validate",
    "publish",
    "rollback",
    "enable",
    "disable",
    "create",
    "update",
)
_SUPPORTED_KINDS = (
    "agent-profiles",
    "llm-profiles",
    "tool-catalog",
    "skill-catalog",
    "memory-config",
    "access-assets",
    "channel-profiles",
    "event-registry",
    "runtime-defaults",
    "environment",
    "audit-logs",
    "backup-restore",
)
_KIND_ALIASES = {
    "agent": "agent-profiles",
    "agents": "agent-profiles",
    "agent_profiles": "agent-profiles",
    "llm": "llm-profiles",
    "llms": "llm-profiles",
    "llm_profiles": "llm-profiles",
    "tool": "tool-catalog",
    "tools": "tool-catalog",
    "tool_providers": "tool-catalog",
    "skill": "skill-catalog",
    "skills": "skill-catalog",
    "memory": "memory-config",
    "memory_config": "memory-config",
    "access": "access-assets",
    "access_assets": "access-assets",
    "channel": "channel-profiles",
    "channels": "channel-profiles",
    "channel_profiles": "channel-profiles",
    "event": "event-registry",
    "events": "event-registry",
    "event-contracts": "event-registry",
    "event_registry": "event-registry",
    "runtime": "runtime-defaults",
    "runtime_defaults": "runtime-defaults",
    "audit": "audit-logs",
    "audits": "audit-logs",
    "audit_logs": "audit-logs",
    "backup": "backup-restore",
    "backup_restore": "backup-restore",
}
_KIND_TITLES = {
    "agent-profiles": "Agent Profiles",
    "llm-profiles": "LLM Profiles",
    "tool-catalog": "Tool Catalog",
    "skill-catalog": "Skill Catalog",
    "memory-config": "Memory Config",
    "access-assets": "Access Assets",
    "channel-profiles": "Channel Profiles",
    "event-registry": "Event Registry",
    "runtime-defaults": "Runtime Defaults",
    "environment": "Environment",
    "audit-logs": "Audit Logs",
    "backup-restore": "Backup / Restore",
}
_KIND_DESCRIPTIONS = {
    "agent-profiles": (
        "Governance and validation view for Agent-owned profiles. Profile writes "
        "must go through the Agent module API."
    ),
    "llm-profiles": (
        "Governance and validation view for LLM-owned profiles. Profile writes "
        "must go through the LLM module API."
    ),
    "tool-catalog": "Tool provider, MCP provider, and local root configuration imported from bootstrap settings.",
    "skill-catalog": (
        "Governance entry for Skills-owned sources, packages, enablement "
        "policies, and readiness. Writes go through the Skills module API."
    ),
    "memory-config": "Memory retrieval and vector configuration imported from bootstrap settings.",
    "access-assets": "Settings-owned access configuration resources. Access runtime readiness remains owned by Access.",
    "channel-profiles": (
        "Governance and validation view for Channels-owned profiles. Profile "
        "writes must go through the Channels module API."
    ),
    "event-registry": (
        "Read-only Settings placeholder. Event contract definitions remain owned by the "
        "Events registry until Settings-owned registry resources are imported."
    ),
    "runtime-defaults": "Runtime defaults imported from bootstrap settings.",
    "environment": (
        "Read-only redacted environment snapshot imported from bootstrap settings. "
        "Environment override workflows are not implemented by Settings yet."
    ),
    "audit-logs": "Settings action audit records captured by the Settings action service.",
    "backup-restore": (
        "Unavailable Settings placeholder. Backup and restore workflows are not implemented "
        "by the Settings module yet."
    ),
}
_SETTINGS_OWNED_ACTIONS = _ALL_ACTIONS
_MODULE_OWNED_PROFILE_ACTIONS: tuple[str, ...] = ()
_READ_ONLY_PLACEHOLDER_ACTIONS: tuple[str, ...] = ()
_KIND_ACTION_POLICY_REGISTRY: dict[str, dict[str, Any]] = {
    "agent-profiles": {
        "owner_module": "agent",
        "truth_owner": "agent",
        "truth_source": "agent_application_service",
        "allowed_actions": _MODULE_OWNED_PROFILE_ACTIONS,
        "owner_api": "/agents",
        "message": (
            "Agent profiles are owned by the Agent module. Use the Agent module API "
            "for create, update, publish, rollback, enable, or disable operations."
        ),
        "apply_policy": {
            "mode": "owner_module_api",
            "owner_module": "agent",
            "hot_apply": False,
            "requires_owner_api": True,
        },
    },
    "llm-profiles": {
        "owner_module": "llm",
        "truth_owner": "llm",
        "truth_source": "llm_application_service",
        "allowed_actions": _MODULE_OWNED_PROFILE_ACTIONS,
        "owner_api": "/llms",
        "message": (
            "LLM profiles are owned by the LLM module. Use the LLM module API "
            "for create, update, publish, rollback, enable, or disable operations."
        ),
        "apply_policy": {
            "mode": "owner_module_api",
            "owner_module": "llm",
            "hot_apply": False,
            "requires_owner_api": True,
        },
    },
    "channel-profiles": {
        "owner_module": "channels",
        "truth_owner": "channels",
        "truth_source": "channel_profile_application_service",
        "allowed_actions": _MODULE_OWNED_PROFILE_ACTIONS,
        "owner_api": "/channels",
        "message": (
            "Channel profiles are owned by the Channels module. Use the Channels "
            "module API for create, update, publish, rollback, enable, or disable "
            "operations."
        ),
        "apply_policy": {
            "mode": "owner_module_api",
            "owner_module": "channels",
            "hot_apply": False,
            "requires_owner_api": True,
        },
    },
    "audit-logs": {
        "owner_module": "settings",
        "truth_owner": "settings",
        "truth_source": "settings_action_audit_repository",
        "allowed_actions": (),
        "owner_api": "/settings/audit-logs",
        "message": "Audit logs are read-only Settings action records.",
        "apply_policy": {
            "mode": "read_only",
            "hot_apply": False,
            "requires_owner_api": False,
        },
    },
    "event-registry": {
        "owner_module": "events",
        "truth_owner": "events",
        "truth_source": "events_contract_registry",
        "allowed_actions": _READ_ONLY_PLACEHOLDER_ACTIONS,
        "owner_api": "/operations/events",
        "message": (
            "Event registry resources are read-only placeholders in Settings. "
            "Event contracts remain owned by the Events module."
        ),
        "apply_policy": {
            "mode": "read_only_placeholder",
            "owner_module": "events",
            "hot_apply": False,
            "requires_owner_api": True,
        },
    },
    "backup-restore": {
        "owner_module": "settings",
        "truth_owner": "settings",
        "truth_source": "not_implemented",
        "allowed_actions": (),
        "owner_api": None,
        "message": "Backup and restore workflows are not implemented by Settings yet.",
        "apply_policy": {
            "mode": "unavailable",
            "hot_apply": False,
            "requires_owner_api": False,
        },
    },
    "environment": {
        "owner_module": "settings",
        "truth_owner": "settings",
        "truth_source": "runtime_environment_snapshot",
        "allowed_actions": _READ_ONLY_PLACEHOLDER_ACTIONS,
        "owner_api": "/settings/environment",
        "message": (
            "Environment resources are redacted runtime snapshots in Settings. "
            "Create, update, publish, rollback, enable, and disable are blocked "
            "until an explicit override workflow exists."
        ),
        "apply_policy": {
            "mode": "read_only_environment_snapshot",
            "owner_module": "settings",
            "hot_apply": False,
            "requires_owner_api": False,
        },
    },
}
_REDACTED_VALUE = "***"
_SECRET_KEY_PARTS = (
    "api_key",
    "apikey",
    "token",
    "secret",
    "password",
    "credential",
    "private_key",
    "privatekey",
)
_DATABASE_URL_KEY_PARTS = (
    "database_url",
    "databaseurl",
)
_SENSITIVE_ASSIGNMENT_RE = re.compile(
    r"(\b(?:api[_-]?key|token|secret|password|credential|private[_-]?key|pwd|pass)\s*=\s*)"
    r"([^&;\s]+)",
    re.IGNORECASE,
)
_RUNTIME_DEFAULT_TOP_LEVEL_KEYS = frozenset(
    {"config_id", "id", "enabled", "orchestration", "tool_worker", "metadata"},
)
_RUNTIME_DEFAULT_GROUP_KEYS = {
    "orchestration": frozenset(
        {
            "run_lease_seconds",
            "run_heartbeat_seconds",
            "executor_max_concurrent_assignments",
            "auto_compaction_enabled",
            "auto_compaction_reserve_tokens",
            "auto_compaction_soft_threshold_tokens",
        },
    ),
    "tool_worker": frozenset(
        {
            "run_max_attempts",
            "run_lease_seconds",
            "run_heartbeat_seconds",
            "max_in_flight",
            "default_run_concurrency",
            "image_run_concurrency",
            "shared_state_run_concurrency",
            "remote_default_max_concurrency",
        },
    ),
}
_RUNTIME_DEFAULT_NUMERIC_FIELDS = frozenset(
    {
        "orchestration.run_lease_seconds",
        "orchestration.run_heartbeat_seconds",
        "orchestration.executor_max_concurrent_assignments",
        "orchestration.auto_compaction_reserve_tokens",
        "orchestration.auto_compaction_soft_threshold_tokens",
        "tool_worker.run_max_attempts",
        "tool_worker.run_lease_seconds",
        "tool_worker.run_heartbeat_seconds",
        "tool_worker.max_in_flight",
        "tool_worker.default_run_concurrency",
        "tool_worker.image_run_concurrency",
        "tool_worker.shared_state_run_concurrency",
        "tool_worker.remote_default_max_concurrency",
    },
)
_RUNTIME_DEFAULT_BOOL_FIELDS = frozenset({"orchestration.auto_compaction_enabled"})
_RUNTIME_DEFAULT_FIELD_SPECS = (
    {
        "path": "orchestration.run_lease_seconds",
        "group": "orchestration",
        "unit": "seconds",
        "default": 30,
        "minimum": 1,
        "apply_requirement": "orchestration_restart",
        "consumer": "orchestration",
    },
    {
        "path": "orchestration.run_heartbeat_seconds",
        "group": "orchestration",
        "unit": "seconds",
        "default": 5.0,
        "minimum": 0.1,
        "apply_requirement": "orchestration_restart",
        "consumer": "orchestration",
    },
    {
        "path": "orchestration.executor_max_concurrent_assignments",
        "group": "orchestration",
        "unit": "assignments",
        "default": 4,
        "minimum": 1,
        "apply_requirement": "executor_restart",
        "consumer": "orchestration_executor",
    },
    {
        "path": "orchestration.auto_compaction_enabled",
        "group": "compaction",
        "unit": "boolean",
        "default": True,
        "apply_requirement": "orchestration_restart",
        "consumer": "orchestration",
    },
    {
        "path": "orchestration.auto_compaction_reserve_tokens",
        "group": "compaction",
        "unit": "tokens",
        "default": 20_000,
        "minimum": 1,
        "apply_requirement": "orchestration_restart",
        "consumer": "orchestration",
    },
    {
        "path": "orchestration.auto_compaction_soft_threshold_tokens",
        "group": "compaction",
        "unit": "tokens",
        "default": 4_000,
        "minimum": 1,
        "apply_requirement": "orchestration_restart",
        "consumer": "orchestration",
    },
    {
        "path": "tool_worker.run_max_attempts",
        "group": "tool_worker",
        "unit": "attempts",
        "default": 3,
        "minimum": 1,
        "apply_requirement": "tool_worker_restart",
        "consumer": "tool_worker",
    },
    {
        "path": "tool_worker.run_lease_seconds",
        "group": "tool_worker",
        "unit": "seconds",
        "default": 30,
        "minimum": 1,
        "apply_requirement": "tool_worker_restart",
        "consumer": "tool_worker",
    },
    {
        "path": "tool_worker.run_heartbeat_seconds",
        "group": "tool_worker",
        "unit": "seconds",
        "default": 5.0,
        "minimum": 0.1,
        "apply_requirement": "tool_worker_restart",
        "consumer": "tool_worker",
    },
    {
        "path": "tool_worker.max_in_flight",
        "group": "tool_worker",
        "unit": "runs",
        "default": 4,
        "minimum": 1,
        "apply_requirement": "tool_worker_restart",
        "consumer": "tool_worker",
    },
    {
        "path": "tool_worker.default_run_concurrency",
        "group": "tool_worker",
        "unit": "runs",
        "default": 4,
        "minimum": 1,
        "apply_requirement": "tool_runtime_restart",
        "consumer": "tool_runtime",
    },
    {
        "path": "tool_worker.image_run_concurrency",
        "group": "tool_worker",
        "unit": "runs",
        "default": 4,
        "minimum": 1,
        "apply_requirement": "tool_runtime_restart",
        "consumer": "tool_runtime",
    },
    {
        "path": "tool_worker.shared_state_run_concurrency",
        "group": "tool_worker",
        "unit": "runs",
        "default": 1,
        "minimum": 1,
        "apply_requirement": "tool_runtime_restart",
        "consumer": "tool_runtime",
    },
    {
        "path": "tool_worker.remote_default_max_concurrency",
        "group": "tool_worker",
        "unit": "calls",
        "default": 16,
        "minimum": 1,
        "apply_requirement": "tool_runtime_restart",
        "consumer": "tool_runtime",
    },
)
_RUNTIME_DEFAULT_APPLY_REQUIREMENTS = (
    {
        "id": "orchestration_restart",
        "mode": "restart_required",
        "owner": "orchestration",
        "applies_after": "API/daemon or orchestration executor restart",
    },
    {
        "id": "executor_restart",
        "mode": "restart_required",
        "owner": "daemon",
        "applies_after": "daemon spec refresh and executor process restart",
    },
    {
        "id": "tool_worker_restart",
        "mode": "restart_required",
        "owner": "tool",
        "applies_after": "tool worker process restart",
    },
    {
        "id": "tool_runtime_restart",
        "mode": "restart_required",
        "owner": "tool",
        "applies_after": "tool runtime service re-assembly or worker restart",
    },
)


class SettingsActionRequest(BaseModel):
    resource_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    reason: str | None = None
    actor: str | None = None
    risk: str | None = None
    dry_run: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


@router.get("")
def get_settings_overview(
    container: Annotated[AppContainer, Depends(get_container)],
) -> dict[str, Any]:
    return _overview_payload(_settings_query_service(container))


@router.get("/{kind}")
def list_settings_resources(
    kind: str,
    container: Annotated[AppContainer, Depends(get_container)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict[str, Any]:
    resolved_kind = _require_kind(kind)
    query = _settings_query_service(container)
    if resolved_kind == "audit-logs":
        return _audit_page(query, limit=limit, offset=offset)
    return _kind_payload(query, resolved_kind, limit=limit, offset=offset)


@router.get("/{kind}/{resource_id}")
def get_settings_resource_detail(
    kind: str,
    resource_id: str,
    container: Annotated[AppContainer, Depends(get_container)],
) -> dict[str, Any]:
    resolved_kind = _require_kind(kind)
    query = _settings_query_service(container)
    if resolved_kind == "audit-logs":
        audit = _audit_by_id(query, resource_id)
        if audit is None:
            raise HTTPException(status_code=404, detail="Settings audit record not found.")
        return _audit_payload(audit)
    resource = _resource_by_kind(query, resolved_kind, resource_id)
    if resource is None:
        raise HTTPException(status_code=404, detail="Settings resource not found.")
    return _resource_detail_payload(query, resource)


@router.post(
    "/{kind}/actions/{action}",
    status_code=status.HTTP_202_ACCEPTED,
)
def run_kind_settings_action(
    kind: str,
    action: SettingsActionName,
    payload: SettingsActionRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> dict[str, Any]:
    return _run_settings_action(
        container,
        action=action,
        kind=kind,
        resource_id=payload.resource_id,
        payload=payload,
    )


@router.post(
    "/{kind}/{resource_id}/actions/{action}",
    status_code=status.HTTP_202_ACCEPTED,
)
def run_resource_settings_action(
    kind: str,
    resource_id: str,
    action: SettingsActionName,
    payload: SettingsActionRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> dict[str, Any]:
    return _run_settings_action(
        container,
        action=action,
        kind=kind,
        resource_id=resource_id,
        payload=payload,
    )


@router.post("/bootstrap-import", status_code=status.HTTP_202_ACCEPTED)
def bootstrap_import_settings(
    payload: SettingsActionRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> dict[str, Any]:
    if not payload.reason:
        raise HTTPException(status_code=400, detail="Settings bootstrap import requires a reason.")
    core_result = import_core_settings_resources(
        container.require(AppKey.CORE_SETTINGS),
        actions=_settings_action_service(container),
        queries=_settings_query_service(container),
        actor=payload.actor,
        reason=payload.reason,
    )
    access_result = AccessSettingsBootstrapImporter(
        action_service=_settings_action_service(container),
        query_service=_settings_query_service(container),
    ).import_from_legacy_container(
        container,
        actor=payload.actor,
        reason=payload.reason,
    )
    imported_counts = dict(core_result.imported_counts)
    imported_counts["access-assets"] = imported_counts.get(
        "access-assets",
        0,
    ) + int(access_result.imported_counts.get("access-assets", 0))
    return {
        "action": "bootstrap-import",
        "status": "succeeded",
        "result": {
            "core": core_result.to_payload(),
            "access": access_result.to_payload(),
        },
        "imported_counts": imported_counts,
    }


def _overview_payload(query: SettingsQueryService) -> dict[str, Any]:
    counts = _resource_counts(query)
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
            "kinds": len(_SUPPORTED_KINDS),
            "audits": len(audits),
        },
        "resource_counts": [
            {
                "id": kind,
                "label": _KIND_TITLES[kind],
                "value": count,
                "tone": "warning" if count == 0 else "success",
                "route": f"/settings/{kind}",
            }
            for kind, count in counts.items()
        ],
        "contract_summary": _key_value_section(
            "Ownership",
            {
                "truth_owner": "settings",
                "provider": "settings_application",
                "bootstrap_source": "core.config.Settings",
            },
        ),
        "configuration_summary": _key_value_section(
            "Configuration",
            {
                "resources": total_resources,
                "resource_kinds": len(_SUPPORTED_KINDS),
                "audits": len(audits),
            },
        ),
        "configuration_health": {
            "title": "Configuration Health",
            "columns": ["Resource", "Count", "Status"],
            "rows": [
                {
                    "Resource": _KIND_TITLES[kind],
                    "Count": count,
                    "Status": "pending import" if count == 0 else "ready",
                }
                for kind, count in counts.items()
            ],
        },
        "recent_changes": _audit_table(audits[-10:]),
        "configuration_distribution": {
            "title": "Configuration Distribution",
            "kind": "bar",
            "series": [
                {"label": _KIND_TITLES[kind], "value": count}
                for kind, count in counts.items()
            ],
        },
        "configuration_issues": {
            "title": "Configuration Issues",
            "columns": ["Resource", "Issue", "Severity"],
            "rows": [
                {
                    "Resource": _KIND_TITLES[kind],
                    "Issue": "No Settings-owned resources imported yet.",
                    "Severity": "warning",
                }
                for kind in missing
            ],
        },
        "configuration_inheritance": _key_value_section(
            "Resolution",
            {
                "default_source": "bootstrap",
                "workspace_override": "not_configured",
                "environment_override": "settings_overrides",
            },
        ),
        "sources_versioning": _key_value_section(
            "Sources",
            {
                "bootstrap": "core.config.Settings",
                "versions": sum(len(query.list_versions(resource.id)) for resource in query.list_resources()),
                "latest_audit": audits[-1].id if audits else None,
            },
        ),
        "quick_actions": _overview_actions(),
        "useful_links": [
            {"label": _KIND_TITLES[kind], "route": f"/settings/{kind}"}
            for kind in _SUPPORTED_KINDS
        ],
    }


def _kind_payload(
    query: SettingsQueryService,
    kind: str,
    *,
    limit: int,
    offset: int,
) -> dict[str, Any]:
    resources = tuple(query.list_resources(resource_kind=kind))
    selected = resources[offset : offset + limit]
    summaries = [_resource_summary_payload(query, resource) for resource in selected]
    audits = _kind_audits(query, kind)
    policy = _kind_policy_payload(kind)
    return {
        "resource": kind,
        "kind": kind,
        "title": _KIND_TITLES[kind],
        "description": _KIND_DESCRIPTIONS[kind],
        **policy,
        "status": "empty" if not resources else "ready",
        "health": {
            "status": "empty" if not resources else "ready",
            "degraded": False,
            "source": "settings_application",
        },
        "tabs": _resource_tabs(kind),
        "active_tab": "overview",
        "resources": summaries,
        "list": {
            "title": _KIND_TITLES[kind],
            "columns": ["Name", "ID", "Status", "Enabled", "Source", "Version"],
            "rows": [_resource_row(summary) for summary in summaries],
            "total": len(resources),
            "limit": limit,
            "offset": offset,
        },
        "detail": _resource_detail_payload(query, selected[0]) if selected else None,
        "summary": [
            _key_value_section(
                "Summary",
                {
                    "resources": len(resources),
                    "source": "settings_application",
                    "kind": kind,
                },
            ),
        ],
        "effective_configuration": _effective_configuration_payload(kind, summaries),
        "validation": _validation_payload("valid" if resources else "unknown"),
        "impact": _impact_payload(kind, selected[0].id if selected else None),
        "audit": _audit_summary_payload(audits),
        "danger_zone": _danger_zone_payload(kind),
        "actions": _kind_actions(kind),
    }


def _resource_detail_payload(
    query: SettingsQueryService,
    resource: SettingsResource,
) -> dict[str, Any]:
    summary = _resource_summary_payload(query, resource)
    versions = query.list_versions(resource.id)
    latest = versions[-1] if versions else None
    audits = _resource_audits(query, resource)
    policy = _kind_policy_payload(resource.resource_kind)
    effective_config = (
        summary["effective_config"]
        if isinstance(summary["effective_config"], Mapping)
        else {}
    )
    validation = (
        _runtime_defaults_validation_payload(effective_config)
        if resource.resource_kind == "runtime-defaults"
        else _validation_from_version(latest)
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
        "payload": _redact_value(latest.payload if latest is not None else {}),
        "effective_config": summary["effective_config"],
        "resolution": summary["resolution"],
        "detail": {
            "id": resource.id,
            "title": resource.display_name or resource.id,
            "status": resource.status.value,
            "tabs": _resource_tabs(resource.resource_kind),
            "active_tab": "overview",
            "sections": [
                _key_value_section(
                    "Resource",
                    {
                        "kind": resource.resource_kind,
                        "owner_module": resource.owner_module,
                        "version": latest.version_number if latest else None,
                        "enabled": resource.enabled,
                    },
                ),
            ],
            "actions": _resource_actions(resource.resource_kind, resource.id),
        },
        "validation": validation,
        "impact": _impact_payload(resource.resource_kind, resource.id),
        "audit": _audit_summary_payload(audits),
        "actions": _resource_actions(resource.resource_kind, resource.id),
        "versions": [_redact_value(version.to_payload()) for version in versions],
    }
    if resource.resource_kind == "runtime-defaults":
        payload["runtime_defaults"] = _runtime_defaults_read_model(
            resource=resource,
            latest=latest,
            effective_config=effective_config,
            summary=summary,
        )
    return payload


def _resource_summary_payload(
    query: SettingsQueryService,
    resource: SettingsResource,
) -> dict[str, Any]:
    versions = query.list_versions(resource.id)
    latest = versions[-1] if versions else None
    resolution = query.get_effective(resource.id)
    effective_config = _redact_value(deepcopy(resolution.effective_value))
    return {
        "id": resource.id,
        "resource_id": resource.id,
        "kind": resource.resource_kind,
        "display_name": resource.display_name or resource.id,
        "status": resource.status.value,
        "enabled": resource.enabled,
        "source": latest.source if latest is not None else "resource_state",
        "version": latest.version_number if latest is not None else None,
        "updated_at": _format_datetime(resource.updated_at),
        **_kind_policy_payload(resource.resource_kind),
        "metadata": _redact_value(resource.metadata),
        "effective_config": effective_config,
        "resolution": _resolution_payload(resolution),
    }


def _audit_page(
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
        "title": _KIND_TITLES["audit-logs"],
        "description": _KIND_DESCRIPTIONS["audit-logs"],
        **_kind_policy_payload("audit-logs"),
        "status": "ready",
        "health": {
            "status": "ready",
            "degraded": False,
            "source": "settings_application",
        },
        "tabs": _resource_tabs("audit-logs"),
        "active_tab": "overview",
        "resources": [_audit_payload(audit) for audit in selected],
        "list": {
            "title": "Settings Action Audits",
            "columns": ["Audit ID", "Action", "Target", "Status", "Actor", "Reason"],
            "rows": [_audit_row(audit) for audit in selected],
            "total": len(audits),
            "limit": limit,
            "offset": offset,
        },
        "detail": _audit_payload(selected[0]) if selected else None,
        "summary": [
            _key_value_section("Audit", {"records": len(audits), "reason_required": True}),
        ],
        "validation": _validation_payload("valid"),
        "audit": _audit_summary_payload(tuple(reversed(selected))),
        "actions": [],
    }


def _run_settings_action(
    container: AppContainer,
    *,
    action: str,
    kind: str,
    resource_id: str | None,
    payload: SettingsActionRequest,
) -> dict[str, Any]:
    resolved_kind = _require_kind(kind)
    query = _settings_query_service(container)
    actions = _settings_action_service(container)
    resolved_id = resource_id or payload.resource_id
    try:
        if not _kind_action_allowed(resolved_kind, action):
            audit = _record_failed_action(
                actions,
                action=action,
                kind=resolved_kind,
                resource_id=resolved_id,
                actor=payload.actor,
                risk=payload.risk,
                request_payload=payload,
                error={
                    "code": "settings_action_not_allowed_for_kind",
                    "action": action,
                    "kind": resolved_kind,
                },
                default_reason="settings action rejected by ownership policy",
            )
            policy = _kind_policy_payload(resolved_kind)
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "settings_action_not_allowed_for_kind",
                    "message": _kind_action_rejection_message(resolved_kind, action),
                    "action": action,
                    "kind": resolved_kind,
                    "resource_id": resolved_id,
                    "allowed_actions": policy["action_policy"]["allowed_actions"],
                    "blocked_actions": policy["action_policy"]["blocked_actions"],
                    "owner_module": policy["ownership"]["owner_module"],
                    "owner_api": policy["action_policy"]["owner_api"],
                    "ownership": policy["ownership"],
                    "action_policy": policy["action_policy"],
                    "apply_policy": policy["apply_policy"],
                    "audit": _audit_payload(audit),
                },
            )
        if action in _WRITE_ACTIONS and not payload.reason:
            audit = _record_failed_action(
                actions,
                action=action,
                kind=resolved_kind,
                resource_id=resolved_id,
                actor=payload.actor,
                risk=payload.risk,
                request_payload=payload,
                error={"code": "settings_action_reason_required"},
            )
            raise HTTPException(
                status_code=400,
                detail={
                    "message": "Settings write actions require a reason.",
                    "audit": _audit_payload(audit),
                },
            )
        if action in {"dry-run", "validate"}:
            if resolved_id is None:
                raise ValueError(f"{action} action requires a resource_id.")
            resource = _require_resource_for_action(query, resolved_kind, resolved_id)
            effective_config = dict(query.get_effective(resource.id).effective_value)
            validation = (
                _runtime_defaults_validation_payload(effective_config)
                if resolved_kind == "runtime-defaults"
                else _validation_payload("valid")
            )
            audit = actions.record_operator_attempt(
                action_type=_action_type(action),
                target_type=resolved_kind,
                target_id=resolved_id,
                reason=payload.reason or f"{action} settings resource",
                actor=payload.actor,
                risk=payload.risk,
                request_metadata=_request_metadata(payload),
            )
            result = {
                "resource_id": resource.id,
                "mutation": action,
                "applied": False,
                "validation": validation,
                "impact": _impact_payload(resolved_kind, resource.id),
            }
            if resolved_kind == "runtime-defaults":
                result["apply_requirement"] = list(_RUNTIME_DEFAULT_APPLY_REQUIREMENTS)
            audit = actions.mark_operator_attempt_succeeded(audit.id, result=result)
            return _action_response(action, resolved_kind, resource.id, audit, result)
        if action == "create":
            resolved_id = resolved_id or _resource_id_from_payload(payload.payload)
            if resolved_id is None:
                raise ValueError("Create action requires resource_id or payload.id.")
            if resolved_kind == "runtime-defaults":
                _ensure_runtime_defaults_payload_is_valid(
                    actions,
                    action=action,
                    kind=resolved_kind,
                    resource_id=resolved_id,
                    actor=payload.actor,
                    risk=payload.risk,
                    request_payload=payload,
                    candidate=payload.payload,
                )
            result = actions.create_resource(
                CreateSettingsResourceInput(
                    resource_id=resolved_id,
                    resource_kind=resolved_kind,
                    owner_module=_owner_module_for_kind(resolved_kind),
                    payload=payload.payload,
                    display_name=_display_name_from_payload(
                        payload.payload,
                        default=resolved_id,
                    ),
                    actor=payload.actor,
                    reason=payload.reason or "create settings resource",
                    publish=True,
                    source="settings_action",
                    metadata=payload.metadata,
                ),
            )
            return _result_response(action, resolved_kind, result, mutation="create")
        if resolved_id is None:
            raise ValueError(f"{action} action requires a resource_id.")
        resource = _require_resource_for_action(query, resolved_kind, resolved_id)
        if action == "update":
            merged = _deep_merge(
                dict(query.get_effective(resource.id).effective_value),
                payload.payload,
            )
            if resolved_kind == "runtime-defaults":
                _ensure_runtime_defaults_payload_is_valid(
                    actions,
                    action=action,
                    kind=resolved_kind,
                    resource_id=resource.id,
                    actor=payload.actor,
                    risk=payload.risk,
                    request_payload=payload,
                    candidate=merged,
                )
            result = actions.update_resource(
                UpdateSettingsResourceInput(
                    resource_id=resource.id,
                    payload=merged,
                    actor=payload.actor,
                    reason=payload.reason or "update settings resource",
                    publish=True,
                    source="settings_action",
                    metadata=payload.metadata,
                ),
            )
            return _result_response(action, resolved_kind, result, mutation="update")
        if action == "publish":
            result = actions.publish_version(
                PublishSettingsVersionInput(
                    resource_id=resource.id,
                    version_id=_optional_payload_text(payload.payload, "version_id"),
                    actor=payload.actor,
                    reason=payload.reason or "publish settings version",
                ),
            )
            return _result_response(action, resolved_kind, result, mutation="publish")
        if action == "rollback":
            result = actions.rollback_resource(
                RollbackSettingsResourceInput(
                    resource_id=resource.id,
                    target_version_id=_rollback_target_version_id(query, resource, payload.payload),
                    actor=payload.actor,
                    reason=payload.reason or "rollback settings resource",
                ),
            )
            return _result_response(action, resolved_kind, result, mutation="rollback")
        if action == "enable":
            result = actions.enable_resource(
                resource.id,
                actor=payload.actor,
                reason=payload.reason or "enable settings resource",
            )
            return _result_response(action, resolved_kind, result, mutation="enable")
        if action == "disable":
            result = actions.disable_resource(
                resource.id,
                actor=payload.actor,
                reason=payload.reason or "disable settings resource",
            )
            return _result_response(action, resolved_kind, result, mutation="disable")
    except HTTPException:
        raise
    except SettingsNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SettingsAlreadyExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (SettingsError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    raise HTTPException(status_code=400, detail=f"Unsupported Settings action: {action}.")


def _result_response(
    action: str,
    kind: str,
    result: Any,
    *,
    mutation: str,
) -> dict[str, Any]:
    resource_id = result.resource.id if result.resource is not None else None
    payload = {
        "resource_id": resource_id,
        "mutation": mutation,
        "applied": result.status == "succeeded",
        "resource": (
            _redact_value(result.resource.to_payload())
            if result.resource is not None
            else None
        ),
        "version": (
            _redact_value(result.version.to_payload())
            if result.version is not None
            else None
        ),
        "validation": result.validation.to_payload(),
    }
    if result.resolution is not None:
        payload["resolution"] = _resolution_payload(result.resolution)
    if kind == "runtime-defaults" and result.resource is not None:
        effective_config = (
            result.resolution.effective_value
            if result.resolution is not None
            else result.version.payload if result.version is not None else {}
        )
        if isinstance(effective_config, Mapping):
            payload["runtime_defaults"] = _runtime_defaults_read_model(
                resource=result.resource,
                latest=result.version,
                effective_config=effective_config,
                summary={
                    "source": result.version.source if result.version is not None else None,
                    "version": result.version.version_number if result.version is not None else None,
                    "resolution": payload.get("resolution", {}),
                },
            )
            payload["validation"] = _runtime_defaults_validation_payload(effective_config)
        payload["apply_requirement"] = list(_RUNTIME_DEFAULT_APPLY_REQUIREMENTS)
    return _action_response(action, kind, resource_id, result.audit, payload, status=result.status)


def _action_response(
    action: str,
    kind: str,
    resource_id: str | None,
    audit: SettingsActionAudit,
    result: dict[str, Any],
    *,
    status: str = "succeeded",
) -> dict[str, Any]:
    policy = _kind_policy_payload(kind)
    return {
        "action": action,
        "kind": kind,
        "resource_id": resource_id,
        **policy,
        "status": status,
        "dry_run": action == "dry-run",
        "audit": _audit_payload(audit),
        "result": result,
    }


def _record_failed_action(
    actions: SettingsActionService,
    *,
    action: str,
    kind: str,
    resource_id: str | None,
    actor: str | None,
    risk: str | None,
    request_payload: SettingsActionRequest,
    error: dict[str, Any],
    default_reason: str = "missing required settings action reason",
) -> SettingsActionAudit:
    audit = actions.record_operator_attempt(
        action_type=_action_type(action),
        target_type=kind,
        target_id=resource_id,
        reason=request_payload.reason or default_reason,
        actor=actor,
        risk=risk,
        request_metadata=_request_metadata(request_payload),
    )
    return actions.mark_operator_attempt_failed(audit.id, error=error)


def _settings_query_service(container: AppContainer) -> SettingsQueryService:
    return container.require(AppKey.SETTINGS_QUERY_SERVICE)


def _settings_action_service(container: AppContainer) -> SettingsActionService:
    return container.require(AppKey.SETTINGS_ACTION_SERVICE)


def _resource_counts(query: SettingsQueryService) -> dict[str, int]:
    return {
        kind: (
            len(query.list_audits())
            if kind == "audit-logs"
            else len(query.list_resources(resource_kind=kind))
        )
        for kind in _SUPPORTED_KINDS
    }


def _resource_by_kind(
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


def _require_resource_for_action(
    query: SettingsQueryService,
    kind: str,
    resource_id: str,
) -> SettingsResource:
    resource = _resource_by_kind(query, kind, resource_id)
    if resource is None:
        raise SettingsNotFoundError(f"settings resource '{kind}/{resource_id}' was not found.")
    return resource


def _kind_audits(query: SettingsQueryService, kind: str) -> tuple[SettingsActionAudit, ...]:
    return tuple(audit for audit in query.list_audits() if audit.target_type == kind)


def _resource_audits(
    query: SettingsQueryService,
    resource: SettingsResource,
) -> tuple[SettingsActionAudit, ...]:
    return tuple(
        audit
        for audit in query.list_audits()
        if audit.target_type == resource.resource_kind and audit.target_id == resource.id
    )


def _audit_by_id(query: SettingsQueryService, audit_id: str) -> SettingsActionAudit | None:
    for audit in query.list_audits():
        if audit.id == audit_id:
            return audit
    return None


def _normalize_kind(kind: str) -> str | None:
    normalized = kind.strip().lower().replace("_", "-")
    if normalized in _SUPPORTED_KINDS:
        return normalized
    return _KIND_ALIASES.get(normalized)


def _require_kind(kind: str) -> str:
    resolved = _normalize_kind(kind)
    if resolved is None:
        raise HTTPException(status_code=404, detail="Settings resource kind not found.")
    return resolved


def _kind_action_policy(kind: str) -> dict[str, Any]:
    policy = _KIND_ACTION_POLICY_REGISTRY.get(kind)
    if policy is not None:
        return policy
    owner_module = _owner_module_for_kind(kind)
    return {
        "owner_module": owner_module,
        "truth_owner": "settings",
        "truth_source": "settings_application_service",
        "allowed_actions": _SETTINGS_OWNED_ACTIONS,
        "owner_api": f"/settings/{kind}",
        "message": (
            "This Settings resource kind is governed by the Settings action service."
        ),
        "apply_policy": {
            "mode": "settings_action_service",
            "owner_module": owner_module,
            "hot_apply": False,
            "requires_owner_api": False,
        },
    }


def _kind_policy_payload(kind: str) -> dict[str, Any]:
    policy = _kind_action_policy(kind)
    allowed_actions = _ordered_actions(policy.get("allowed_actions", ()))
    blocked_actions = [
        action for action in _ALL_ACTIONS if action not in allowed_actions
    ]
    owner_module = str(policy["owner_module"])
    truth_owner = str(policy["truth_owner"])
    settings_role = (
        "owner"
        if truth_owner == "settings"
        else "governance_readmodel"
    )
    action_policy = {
        "allowed_actions": allowed_actions,
        "blocked_actions": blocked_actions,
        "write_actions_allowed": any(
            action in _WRITE_ACTIONS for action in allowed_actions
        ),
        "settings_write_allowed": any(
            action in _WRITE_ACTIONS for action in allowed_actions
        ),
        "owner_api": policy.get("owner_api"),
        "message": policy["message"],
    }
    return {
        "ownership": {
            "owner_module": owner_module,
            "truth_owner": truth_owner,
            "truth_source": policy["truth_source"],
            "settings_role": settings_role,
        },
        "action_policy": action_policy,
        "apply_policy": deepcopy(policy["apply_policy"]),
    }


def _ordered_actions(actions: Any) -> list[str]:
    allowed = set(actions or ())
    return [action for action in _ALL_ACTIONS if action in allowed]


def _kind_action_allowed(kind: str, action: str) -> bool:
    return action in _ordered_actions(_kind_action_policy(kind).get("allowed_actions", ()))


def _kind_action_rejection_message(kind: str, action: str) -> str:
    del action
    return str(_kind_action_policy(kind)["message"])


def _owner_module_for_kind(kind: str) -> str:
    return {
        "agent-profiles": "agent",
        "llm-profiles": "llm",
        "tool-catalog": "tool",
        "skill-catalog": "skills",
        "memory-config": "memory",
        "access-assets": "access",
        "channel-profiles": "channels",
        "event-registry": "events",
        "runtime-defaults": "runtime",
        "environment": "settings",
        "backup-restore": "settings",
    }.get(kind, "settings")


def _action_type(action: str) -> str:
    return f"settings.resource.{action.replace('-', '_')}"


def _action_name_from_type(action_type: str) -> str:
    return action_type.rsplit(".", maxsplit=1)[-1].replace("_", "-")


def _request_metadata(payload: SettingsActionRequest) -> dict[str, Any]:
    return _redact_value({"payload": payload.payload, "metadata": payload.metadata})


def _resource_id_from_payload(payload: Mapping[str, Any]) -> str | None:
    for key in ("resource_id", "id", "name", "key"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _display_name_from_payload(payload: Mapping[str, Any], *, default: str) -> str:
    for key in ("display_name", "name", "model_name", "id"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return default


def _optional_payload_text(payload: Mapping[str, Any], key: str) -> str | None:
    value = payload.get(key)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _rollback_target_version_id(
    query: SettingsQueryService,
    resource: SettingsResource,
    payload: Mapping[str, Any],
) -> str:
    explicit = _optional_payload_text(payload, "target_version_id") or _optional_payload_text(
        payload,
        "version_id",
    )
    if explicit is not None:
        return explicit
    versions = query.list_versions(resource.id)
    if not versions:
        raise SettingsNotFoundError("rollback target version was not found for resource.")
    active_index = next(
        (
            index
            for index, version in enumerate(versions)
            if version.id == resource.active_version_id
        ),
        len(versions) - 1,
    )
    return versions[max(active_index - 1, 0)].id


def _resource_row(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "Name": summary["display_name"],
        "ID": summary["resource_id"],
        "Status": summary["status"],
        "Enabled": summary["enabled"],
        "Source": summary["source"],
        "Version": summary["version"],
    }


def _resolution_payload(resolution: Any) -> dict[str, Any]:
    sources = [_source_payload(source) for source in resolution.sources]
    primary = sources[0] if sources else {"kind": "resource_state", "name": "resource_state"}
    return {
        "resource_ref": {
            "kind": resolution.resource.resource_kind,
            "id": resolution.resource.resource_id,
        },
        "value": _redact_value(resolution.effective_value),
        "source": primary,
        "sources": sources,
        "override_trace": [_source_payload(source) for source in resolution.overrides],
        "snapshot_id": resolution.snapshot_id,
        "resolved_at": resolution.resolved_at,
        "validation": dict(resolution.validation),
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


def _resource_tabs(kind: str) -> list[dict[str, str]]:
    labels = ["overview", "effective", "validation", "audit"]
    if kind in {"tool-catalog", "agent-profiles", "llm-profiles", "runtime-defaults"}:
        labels.insert(2, "impact")
    return [{"id": label, "label": label.replace("-", " ").title()} for label in labels]


def _kind_actions(kind: str) -> list[dict[str, Any]]:
    policy = _kind_policy_payload(kind)
    return [
        {
            "id": f"settings.{kind}.{action}",
            "label": action.replace("-", " ").title(),
            "method": "POST",
            "route": f"/settings/{kind}/actions/{action}",
            "requires_reason": action in _WRITE_ACTIONS,
            "risk": "medium" if action in _WRITE_ACTIONS else "low",
            "allowed": True,
            "owner_module": policy["ownership"]["owner_module"],
        }
        for action in ("dry-run", "validate", "create")
        if _kind_action_allowed(kind, action)
    ]


def _resource_actions(kind: str, resource_id: str) -> list[dict[str, Any]]:
    policy = _kind_policy_payload(kind)
    return [
        {
            "id": f"settings.{kind}.{resource_id}.{action}",
            "label": action.replace("-", " ").title(),
            "method": "POST",
            "route": f"/settings/{kind}/{resource_id}/actions/{action}",
            "requires_reason": action in _WRITE_ACTIONS,
            "risk": "medium" if action in _WRITE_ACTIONS else "low",
            "allowed": True,
            "owner_module": policy["ownership"]["owner_module"],
        }
        for action in (
            "dry-run",
            "validate",
            "publish",
            "rollback",
            "enable",
            "disable",
            "update",
        )
        if _kind_action_allowed(kind, action)
    ]


def _overview_actions() -> list[dict[str, Any]]:
    return [
        {
            "id": "settings.bootstrap_import",
            "label": "Bootstrap Import",
            "method": "POST",
            "route": "/settings/bootstrap-import",
            "requires_reason": True,
            "risk": "low",
        },
        {
            "id": "settings.validate_all",
            "label": "Validate All",
            "method": "POST",
            "route": "/settings/runtime-defaults/defaults/actions/validate",
            "requires_reason": False,
            "risk": "low",
        },
    ]


def _key_value_section(title: str, values: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "title": title,
        "items": [
            {"label": key.replace("_", " ").title(), "value": value}
            for key, value in values.items()
        ],
    }


def _runtime_defaults_read_model(
    *,
    resource: SettingsResource,
    latest: SettingsResourceVersion | None,
    effective_config: Mapping[str, Any],
    summary: Mapping[str, Any],
) -> dict[str, Any]:
    resolution = summary.get("resolution") if isinstance(summary.get("resolution"), Mapping) else {}
    source = summary.get("source")
    version = summary.get("version")
    return {
        "schema": "runtime-defaults.v1",
        "resource_id": resource.id,
        "status": resource.status.value,
        "enabled": resource.enabled,
        "source": source if source is not None else latest.source if latest is not None else None,
        "version": version if version is not None else latest.version_number if latest is not None else None,
        "updated_at": _format_datetime(resource.updated_at),
        "resolved_at": resolution.get("resolved_at"),
        "effective_payload": _redact_value(dict(effective_config)),
        "groups": [
            _runtime_default_group_payload("orchestration", effective_config),
            _runtime_default_group_payload("compaction", effective_config),
            _runtime_default_group_payload("tool_worker", effective_config),
        ],
        "apply_requirements": list(_RUNTIME_DEFAULT_APPLY_REQUIREMENTS),
        "validation": _runtime_defaults_validation_payload(effective_config),
    }


def _runtime_default_group_payload(
    group: str,
    effective_config: Mapping[str, Any],
) -> dict[str, Any]:
    fields = [
        _runtime_default_field_payload(spec, effective_config)
        for spec in _RUNTIME_DEFAULT_FIELD_SPECS
        if spec["group"] == group
    ]
    return {
        "id": group,
        "fields": fields,
    }


def _runtime_default_field_payload(
    spec: Mapping[str, Any],
    effective_config: Mapping[str, Any],
) -> dict[str, Any]:
    path = str(spec["path"])
    value = _runtime_default_value(effective_config, path)
    default = spec.get("default")
    return {
        "path": path,
        "value": value if value is not None else default,
        "default": default,
        "unit": spec.get("unit"),
        "minimum": spec.get("minimum"),
        "consumer": spec.get("consumer"),
        "apply_requirement": spec.get("apply_requirement"),
        "input": "toggle" if path in _RUNTIME_DEFAULT_BOOL_FIELDS else "number",
    }


def _runtime_default_value(payload: Mapping[str, Any], path: str) -> Any:
    current: Any = payload
    for part in path.split("."):
        if not isinstance(current, Mapping):
            return None
        current = current.get(part)
    return current


def _runtime_defaults_validation_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    errors = _runtime_defaults_payload_errors(payload)
    status_value = "invalid" if errors else "valid"
    validation = _validation_payload(status_value)
    validation["checks"] = {
        "title": "Runtime Defaults Validation",
        "columns": ["Check", "Result"],
        "rows": [
            {
                "Check": "schema",
                "Result": "pass" if not errors else "failed",
            },
            {
                "Check": "orchestration",
                "Result": _runtime_default_group_result(payload, "orchestration"),
            },
            {
                "Check": "tool_worker",
                "Result": _runtime_default_group_result(payload, "tool_worker"),
            },
        ],
    }
    validation["result"] = {
        "ok": not errors,
        "errors": errors,
        "warnings": [],
        "metadata": {"schema": "runtime-defaults.v1"},
    }
    return validation


def _runtime_default_group_result(payload: Mapping[str, Any], group: str) -> str:
    value = payload.get(group)
    if not isinstance(value, Mapping):
        return "missing"
    unknown = set(value) - _RUNTIME_DEFAULT_GROUP_KEYS[group]
    return "unknown fields" if unknown else "pass"


def _ensure_runtime_defaults_payload_is_valid(
    actions: SettingsActionService,
    *,
    action: str,
    kind: str,
    resource_id: str | None,
    actor: str | None,
    risk: str | None,
    request_payload: SettingsActionRequest,
    candidate: Mapping[str, Any],
) -> None:
    errors = _runtime_defaults_payload_errors(candidate)
    if not errors:
        return
    audit = _record_failed_action(
        actions,
        action=action,
        kind=kind,
        resource_id=resource_id,
        actor=actor,
        risk=risk,
        request_payload=request_payload,
        error={
            "code": "runtime_defaults_validation_failed",
            "errors": errors,
        },
        default_reason="runtime defaults validation failed",
    )
    raise HTTPException(
        status_code=400,
        detail={
            "code": "runtime_defaults_validation_failed",
            "message": "Runtime Defaults payload failed schema validation.",
            "errors": errors,
            "audit": _audit_payload(audit),
        },
    )


def _runtime_defaults_payload_errors(payload: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    unknown_top_level = set(payload) - _RUNTIME_DEFAULT_TOP_LEVEL_KEYS
    for key in sorted(unknown_top_level):
        errors.append(f"unknown top-level field: {key}")
    config_id = payload.get("config_id", payload.get("id"))
    if config_id is not None and (not isinstance(config_id, str) or not config_id.strip()):
        errors.append("config_id must be a non-empty string when provided.")
    if "enabled" in payload and not isinstance(payload["enabled"], bool):
        errors.append("enabled must be a boolean when provided.")
    if "metadata" in payload and not isinstance(payload["metadata"], Mapping):
        errors.append("metadata must be an object when provided.")
    for group, allowed_fields in _RUNTIME_DEFAULT_GROUP_KEYS.items():
        group_value = payload.get(group)
        if group_value is None:
            continue
        if not isinstance(group_value, Mapping):
            errors.append(f"{group} must be an object.")
            continue
        unknown_nested = set(group_value) - allowed_fields
        for key in sorted(unknown_nested):
            errors.append(f"unknown {group} field: {key}")
        for key, value in group_value.items():
            path = f"{group}.{key}"
            if path in _RUNTIME_DEFAULT_NUMERIC_FIELDS:
                _append_positive_number_error(errors, path, value)
            elif path in _RUNTIME_DEFAULT_BOOL_FIELDS and not isinstance(value, bool):
                errors.append(f"{path} must be a boolean.")
    return errors


def _append_positive_number_error(errors: list[str], path: str, value: Any) -> None:
    if isinstance(value, bool):
        errors.append(f"{path} must be a positive number.")
        return
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        errors.append(f"{path} must be a positive number.")
        return
    if parsed <= 0:
        errors.append(f"{path} must be positive.")


def _validation_from_version(version: SettingsResourceVersion | None) -> dict[str, Any]:
    if version is None:
        return _validation_payload("unknown")
    status_value = "valid" if version.validation.ok else "invalid"
    payload = _validation_payload(status_value)
    payload["result"] = version.validation.to_payload()
    payload["last_validated_at"] = _format_datetime(version.created_at)
    return payload


def _validation_payload(status_value: str) -> dict[str, Any]:
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
        "last_validated_at": _format_datetime(_now()),
        "actions": [],
    }


def _impact_payload(kind: str, resource_id: str | None) -> dict[str, Any]:
    payload = {
        "level": "info",
        "summary": _key_value_section(
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
    if _kind_action_allowed(kind, "dry-run"):
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


def _effective_configuration_payload(
    kind: str,
    resources: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "title": f"{_KIND_TITLES[kind]} Effective Configuration",
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


def _danger_zone_payload(kind: str) -> dict[str, Any]:
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
        if _kind_action_allowed(kind, action)
    ]
    return {
        "title": "Danger Zone",
        "description": "Publishing, rollback, enable, and disable actions require an audit reason.",
        "actions": actions,
    }


def _audit_summary_payload(audits: tuple[SettingsActionAudit, ...]) -> dict[str, Any]:
    return {
        "recent_changes": _audit_table(audits[-10:]),
        "audit_history_route": "/settings/audit-logs",
        "reason_required": True,
    }


def _audit_table(
    audits: tuple[SettingsActionAudit, ...] | list[SettingsActionAudit],
) -> dict[str, Any]:
    return {
        "title": "Recent Settings Changes",
        "columns": ["Audit ID", "Action", "Target", "Status", "Actor", "Reason"],
        "rows": [_audit_row(audit) for audit in reversed(tuple(audits))],
    }


def _audit_row(audit: SettingsActionAudit) -> dict[str, Any]:
    payload = _audit_payload(audit)
    return {
        "Audit ID": payload["audit_id"],
        "Action": payload["action"],
        "Target": f"{payload['kind']}/{payload['resource_id'] or '*'}",
        "Status": payload["status"],
        "Actor": payload["actor"],
        "Reason": payload["reason"] or "",
    }


def _audit_payload(audit: SettingsActionAudit) -> dict[str, Any]:
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
        "request_metadata": _redact_value(raw["request_metadata"]),
        "result": _redact_value(raw["result"]),
        "error": _redact_value(raw["error"]),
        "created_at": raw["created_at"],
        "completed_at": raw["updated_at"],
    }


def _deep_merge(left: dict[str, Any], right: Mapping[str, Any]) -> dict[str, Any]:
    merged = deepcopy(left)
    for key, value in right.items():
        if (
            isinstance(value, Mapping)
            and isinstance(merged.get(key), dict)
        ):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = deepcopy(value)
    return merged


def _to_plain_payload(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    to_payload = getattr(value, "to_payload", None)
    if callable(to_payload):
        return _to_plain_payload(to_payload())
    if is_dataclass(value):
        return _to_plain_payload(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _to_plain_payload(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_to_plain_payload(item) for item in value]
    return str(value)


def _redact_value(value: Any, *, _key: str | None = None) -> Any:
    plain = _to_plain_payload(value)
    if isinstance(plain, dict):
        redacted: dict[str, Any] = {}
        for key, item in plain.items():
            key_text = str(key)
            if _is_sensitive_key(key_text) and not _is_safe_numeric_token_count_key(
                key_text,
                item,
            ):
                redacted[key] = _REDACTED_VALUE
            else:
                redacted[key] = _redact_value(item, _key=key_text)
        return redacted
    if isinstance(plain, list):
        return [_redact_value(item, _key=_key) for item in plain]
    if isinstance(plain, str):
        return _redact_string(plain, force_database_url=_is_database_url_key(_key))
    return plain


def _is_sensitive_key(key: str) -> bool:
    normalized = _normalize_secret_key(key)
    return any(_normalize_secret_key(part) in normalized for part in _SECRET_KEY_PARTS)


def _is_safe_numeric_token_count_key(key: str, value: Any) -> bool:
    normalized = _normalize_secret_key(key)
    if not normalized.endswith("tokens"):
        return False
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_database_url_key(key: str | None) -> bool:
    if key is None:
        return False
    normalized = _normalize_secret_key(key)
    return any(_normalize_secret_key(part) in normalized for part in _DATABASE_URL_KEY_PARTS)


def _normalize_secret_key(key: str) -> str:
    return re.sub(r"[^a-z0-9]", "", key.lower())


def _redact_string(value: str, *, force_database_url: bool = False) -> str:
    redacted = _redact_url_password(value)
    redacted = _SENSITIVE_ASSIGNMENT_RE.sub(
        lambda match: f"{match.group(1)}{_REDACTED_VALUE}",
        redacted,
    )
    if force_database_url and redacted == value and value:
        return _REDACTED_VALUE
    return redacted


def _redact_url_password(value: str) -> str:
    try:
        parts = urlsplit(value)
    except ValueError:
        return value
    if not parts.scheme or not parts.netloc:
        return value
    try:
        password = parts.password
    except ValueError:
        return value
    if password is None:
        return value
    username = parts.username or ""
    user_info = f"{username}:{_REDACTED_VALUE}@"
    return urlunsplit(
        SplitResult(
            scheme=parts.scheme,
            netloc=f"{user_info}{_url_host_port(parts)}",
            path=parts.path,
            query=parts.query,
            fragment=parts.fragment,
        ),
    )


def _url_host_port(parts: SplitResult) -> str:
    fallback = parts.netloc.rsplit("@", maxsplit=1)[-1]
    try:
        host = parts.hostname
        port = parts.port
    except ValueError:
        return fallback
    if host is None:
        return fallback
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    if port is not None:
        return f"{host}:{port}"
    return host


def _format_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _now() -> datetime:
    return datetime.now(timezone.utc)
