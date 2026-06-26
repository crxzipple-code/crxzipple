from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from crxzipple.modules.settings.application.action_policy import (
    kind_policy_payload as _kind_policy_payload,
)
from crxzipple.modules.settings.application.read_models import (
    RUNTIME_DEFAULT_APPLY_REQUIREMENTS as _RUNTIME_DEFAULT_APPLY_REQUIREMENTS,
    audit_payload as _audit_payload,
    resolution_payload as _resolution_payload,
    runtime_defaults_read_model as _runtime_defaults_read_model,
    runtime_defaults_validation_payload as _runtime_defaults_validation_payload,
)
from crxzipple.modules.settings.application.redaction import redact_value as _redact_value
from crxzipple.modules.settings.domain import SettingsActionAudit


def result_response(
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
                    "version": (
                        result.version.version_number if result.version is not None else None
                    ),
                    "resolution": payload.get("resolution", {}),
                },
            )
            payload["validation"] = _runtime_defaults_validation_payload(effective_config)
        payload["apply_requirement"] = list(_RUNTIME_DEFAULT_APPLY_REQUIREMENTS)
    return action_response(action, kind, resource_id, result.audit, payload, status=result.status)


def action_response(
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
