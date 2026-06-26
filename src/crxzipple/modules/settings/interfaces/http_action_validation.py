from __future__ import annotations

from typing import Any

from crxzipple.modules.settings.application import (
    SettingsActionService,
    SettingsQueryService,
)
from crxzipple.modules.settings.application.action_policy import SettingsActionName
from crxzipple.modules.settings.application.read_models import (
    RUNTIME_DEFAULT_APPLY_REQUIREMENTS,
    impact_payload,
    runtime_defaults_validation_payload,
    validation_payload,
)
from crxzipple.modules.settings.interfaces.http_action_helpers import (
    action_type,
    request_metadata,
    require_resource_for_action,
)
from crxzipple.modules.settings.interfaces.http_action_models import SettingsActionRequest
from crxzipple.modules.settings.interfaces.http_action_responses import action_response


def execute_validation_action(
    *,
    query: SettingsQueryService,
    actions: SettingsActionService,
    action: SettingsActionName,
    kind: str,
    resource_id: str | None,
    payload: SettingsActionRequest,
) -> dict[str, Any]:
    if resource_id is None:
        raise ValueError(f"{action} action requires a resource_id.")
    resource = require_resource_for_action(query, kind, resource_id)
    effective_config = dict(query.get_effective(resource.id).effective_value)
    validation = (
        runtime_defaults_validation_payload(effective_config)
        if kind == "runtime-defaults"
        else validation_payload("valid")
    )
    audit = actions.record_operator_attempt(
        action_type=action_type(action),
        target_type=kind,
        target_id=resource_id,
        reason=payload.reason or f"{action} settings resource",
        actor=payload.actor,
        risk=payload.risk,
        request_metadata=request_metadata(payload),
    )
    result = {
        "resource_id": resource.id,
        "mutation": action,
        "applied": False,
        "validation": validation,
        "impact": impact_payload(kind, resource.id),
    }
    if kind == "runtime-defaults":
        result["apply_requirement"] = list(RUNTIME_DEFAULT_APPLY_REQUIREMENTS)
    audit = actions.mark_operator_attempt_succeeded(audit.id, result=result)
    return action_response(action, kind, resource.id, audit, result)
