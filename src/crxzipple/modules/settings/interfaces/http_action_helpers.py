from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from fastapi import HTTPException

from crxzipple.modules.settings.application import (
    SettingsActionService,
    SettingsQueryService,
)
from crxzipple.modules.settings.application.read_models import (
    audit_payload as _audit_payload,
    resource_by_kind as _resource_by_kind,
    runtime_defaults_payload_errors as _runtime_defaults_payload_errors,
)
from crxzipple.modules.settings.application.redaction import redact_value as _redact_value
from crxzipple.modules.settings.domain import (
    SettingsActionAudit,
    SettingsNotFoundError,
    SettingsResource,
)
from crxzipple.modules.settings.interfaces.http_action_models import SettingsActionRequest


def record_failed_action(
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
        action_type=action_type(action),
        target_type=kind,
        target_id=resource_id,
        reason=request_payload.reason or default_reason,
        actor=actor,
        risk=risk,
        request_metadata=request_metadata(request_payload),
    )
    return actions.mark_operator_attempt_failed(audit.id, error=error)


def require_resource_for_action(
    query: SettingsQueryService,
    kind: str,
    resource_id: str,
) -> SettingsResource:
    resource = _resource_by_kind(query, kind, resource_id)
    if resource is None:
        raise SettingsNotFoundError(f"settings resource '{kind}/{resource_id}' was not found.")
    return resource


def action_type(action: str) -> str:
    return f"settings.resource.{action.replace('-', '_')}"


def request_metadata(payload: SettingsActionRequest) -> dict[str, Any]:
    return _redact_value(
        {
            "payload": payload.payload,
            "expected_active_version_id": payload.expected_active_version_id,
            "metadata": payload.metadata,
        },
    )


def resource_id_from_payload(payload: Mapping[str, Any]) -> str | None:
    for key in ("resource_id", "id", "name", "key"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def display_name_from_payload(payload: Mapping[str, Any], *, default: str) -> str:
    for key in ("display_name", "name", "model_name", "id"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return default


def optional_payload_text(payload: Mapping[str, Any], key: str) -> str | None:
    value = payload.get(key)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def rollback_target_version_id(
    query: SettingsQueryService,
    resource: SettingsResource,
    payload: Mapping[str, Any],
) -> str:
    explicit = optional_payload_text(payload, "target_version_id") or optional_payload_text(
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


def ensure_runtime_defaults_payload_is_valid(
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
    audit = record_failed_action(
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


def deep_merge(left: dict[str, Any], right: Mapping[str, Any]) -> dict[str, Any]:
    merged = deepcopy(left)
    for key, value in right.items():
        if isinstance(value, Mapping) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = deepcopy(value)
    return merged
