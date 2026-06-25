from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from crxzipple.modules.settings.application.redaction import redact_value
from crxzipple.modules.settings.domain import SettingsResource, SettingsResourceVersion

RUNTIME_DEFAULT_TOP_LEVEL_KEYS = frozenset(
    {"config_id", "id", "enabled", "orchestration", "tool_worker", "metadata"},
)
RUNTIME_DEFAULT_GROUP_KEYS = {
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
RUNTIME_DEFAULT_NUMERIC_FIELDS = frozenset(
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
RUNTIME_DEFAULT_BOOL_FIELDS = frozenset({"orchestration.auto_compaction_enabled"})
RUNTIME_DEFAULT_FIELD_SPECS = (
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
RUNTIME_DEFAULT_APPLY_REQUIREMENTS = (
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


def runtime_defaults_read_model(
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
        "effective_payload": redact_value(dict(effective_config)),
        "groups": [
            _runtime_default_group_payload("orchestration", effective_config),
            _runtime_default_group_payload("compaction", effective_config),
            _runtime_default_group_payload("tool_worker", effective_config),
        ],
        "apply_requirements": list(RUNTIME_DEFAULT_APPLY_REQUIREMENTS),
        "validation": runtime_defaults_validation_payload(effective_config),
    }


def _runtime_default_group_payload(
    group: str,
    effective_config: Mapping[str, Any],
) -> dict[str, Any]:
    fields = [
        _runtime_default_field_payload(spec, effective_config)
        for spec in RUNTIME_DEFAULT_FIELD_SPECS
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
    value = runtime_default_value(effective_config, path)
    default = spec.get("default")
    return {
        "path": path,
        "value": value if value is not None else default,
        "default": default,
        "unit": spec.get("unit"),
        "minimum": spec.get("minimum"),
        "consumer": spec.get("consumer"),
        "apply_requirement": spec.get("apply_requirement"),
        "input": "toggle" if path in RUNTIME_DEFAULT_BOOL_FIELDS else "number",
    }


def runtime_default_value(payload: Mapping[str, Any], path: str) -> Any:
    current: Any = payload
    for part in path.split("."):
        if not isinstance(current, Mapping):
            return None
        current = current.get(part)
    return current


def runtime_defaults_validation_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    errors = runtime_defaults_payload_errors(payload)
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


def runtime_defaults_payload_errors(payload: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    unknown_top_level = set(payload) - RUNTIME_DEFAULT_TOP_LEVEL_KEYS
    for key in sorted(unknown_top_level):
        errors.append(f"unknown top-level field: {key}")
    config_id = payload.get("config_id", payload.get("id"))
    if config_id is not None and (not isinstance(config_id, str) or not config_id.strip()):
        errors.append("config_id must be a non-empty string when provided.")
    if "enabled" in payload and not isinstance(payload["enabled"], bool):
        errors.append("enabled must be a boolean when provided.")
    if "metadata" in payload and not isinstance(payload["metadata"], Mapping):
        errors.append("metadata must be an object when provided.")
    for group, allowed_fields in RUNTIME_DEFAULT_GROUP_KEYS.items():
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
            if path in RUNTIME_DEFAULT_NUMERIC_FIELDS:
                _append_positive_number_error(errors, path, value)
            elif path in RUNTIME_DEFAULT_BOOL_FIELDS and not isinstance(value, bool):
                errors.append(f"{path} must be a boolean.")
    return errors


def _runtime_default_group_result(payload: Mapping[str, Any], group: str) -> str:
    value = payload.get(group)
    if not isinstance(value, Mapping):
        return "missing"
    unknown = set(value) - RUNTIME_DEFAULT_GROUP_KEYS[group]
    return "unknown fields" if unknown else "pass"


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
        "last_validated_at": _format_datetime(datetime.now(timezone.utc)),
        "actions": [],
    }


def _format_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
