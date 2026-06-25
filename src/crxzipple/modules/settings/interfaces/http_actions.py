from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from fastapi import HTTPException
from pydantic import BaseModel, Field

from crxzipple.interfaces.runtime_container import AppContainer
from crxzipple.modules.settings.application import (
    CreateSettingsResourceInput,
    PublishSettingsVersionInput,
    RollbackSettingsResourceInput,
    SettingsActionService,
    SettingsQueryService,
    UpdateSettingsResourceInput,
)
from crxzipple.modules.settings.application.action_policy import (
    WRITE_ACTIONS as _WRITE_ACTIONS,
    SettingsActionName,
    kind_action_allowed as _kind_action_allowed,
    kind_action_rejection_message as _kind_action_rejection_message,
    kind_policy_payload as _kind_policy_payload,
    owner_module_for_kind as _owner_module_for_kind,
)
from crxzipple.modules.settings.application.read_models import (
    RUNTIME_DEFAULT_APPLY_REQUIREMENTS as _RUNTIME_DEFAULT_APPLY_REQUIREMENTS,
    audit_payload as _audit_payload,
    impact_payload as _impact_payload,
    resolution_payload as _resolution_payload,
    resource_by_kind as _resource_by_kind,
    runtime_defaults_payload_errors as _runtime_defaults_payload_errors,
    runtime_defaults_read_model as _runtime_defaults_read_model,
    runtime_defaults_validation_payload as _runtime_defaults_validation_payload,
    validation_payload as _validation_payload,
)
from crxzipple.modules.settings.application.redaction import redact_value as _redact_value
from crxzipple.modules.settings.domain import (
    SettingsActionAudit,
    SettingsAlreadyExistsError,
    SettingsConflictError,
    SettingsError,
    SettingsNotFoundError,
    SettingsResource,
)
from crxzipple.modules.settings.interfaces.http_common import (
    require_kind as _require_kind,
    settings_action_service as _settings_action_service,
    settings_query_service as _settings_query_service,
)


class SettingsActionRequest(BaseModel):
    resource_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    reason: str | None = None
    actor: str | None = None
    risk: str | None = None
    dry_run: bool = False
    expected_active_version_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


def run_settings_action(
    container: AppContainer,
    *,
    action: SettingsActionName,
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
                    expected_active_version_id=payload.expected_active_version_id,
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
                    expected_active_version_id=payload.expected_active_version_id,
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
                    expected_active_version_id=payload.expected_active_version_id,
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
    except SettingsConflictError as exc:
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


def _require_resource_for_action(
    query: SettingsQueryService,
    kind: str,
    resource_id: str,
) -> SettingsResource:
    resource = _resource_by_kind(query, kind, resource_id)
    if resource is None:
        raise SettingsNotFoundError(f"settings resource '{kind}/{resource_id}' was not found.")
    return resource


def _action_type(action: str) -> str:
    return f"settings.resource.{action.replace('-', '_')}"


def _request_metadata(payload: SettingsActionRequest) -> dict[str, Any]:
    return _redact_value(
        {
            "payload": payload.payload,
            "expected_active_version_id": payload.expected_active_version_id,
            "metadata": payload.metadata,
        },
    )


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


def _deep_merge(left: dict[str, Any], right: Mapping[str, Any]) -> dict[str, Any]:
    merged = deepcopy(left)
    for key, value in right.items():
        if isinstance(value, Mapping) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = deepcopy(value)
    return merged
