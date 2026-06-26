from __future__ import annotations

from typing import Any

from crxzipple.modules.settings.application import (
    CreateSettingsResourceInput,
    SettingsActionService,
    SettingsQueryService,
    UpdateSettingsResourceInput,
)
from crxzipple.modules.settings.application.action_policy import (
    SettingsActionName,
    owner_module_for_kind,
)
from crxzipple.modules.settings.interfaces.http_action_helpers import (
    deep_merge,
    display_name_from_payload,
    ensure_runtime_defaults_payload_is_valid,
    resource_id_from_payload,
)
from crxzipple.modules.settings.interfaces.http_action_models import SettingsActionRequest
from crxzipple.modules.settings.interfaces.http_action_responses import result_response


def execute_create_action(
    *,
    actions: SettingsActionService,
    action: SettingsActionName,
    kind: str,
    resource_id: str | None,
    payload: SettingsActionRequest,
) -> dict[str, Any]:
    resolved_id = resource_id or resource_id_from_payload(payload.payload)
    if resolved_id is None:
        raise ValueError("Create action requires resource_id or payload.id.")
    if kind == "runtime-defaults":
        ensure_runtime_defaults_payload_is_valid(
            actions,
            action=action,
            kind=kind,
            resource_id=resolved_id,
            actor=payload.actor,
            risk=payload.risk,
            request_payload=payload,
            candidate=payload.payload,
        )
    result = actions.create_resource(
        CreateSettingsResourceInput(
            resource_id=resolved_id,
            resource_kind=kind,
            owner_module=owner_module_for_kind(kind),
            payload=payload.payload,
            display_name=display_name_from_payload(
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
    return result_response(action, kind, result, mutation="create")


def execute_update_action(
    *,
    query: SettingsQueryService,
    actions: SettingsActionService,
    action: SettingsActionName,
    kind: str,
    resource_id: str,
    payload: SettingsActionRequest,
) -> dict[str, Any]:
    merged = deep_merge(
        dict(query.get_effective(resource_id).effective_value),
        payload.payload,
    )
    if kind == "runtime-defaults":
        ensure_runtime_defaults_payload_is_valid(
            actions,
            action=action,
            kind=kind,
            resource_id=resource_id,
            actor=payload.actor,
            risk=payload.risk,
            request_payload=payload,
            candidate=merged,
        )
    result = actions.update_resource(
        UpdateSettingsResourceInput(
            resource_id=resource_id,
            payload=merged,
            actor=payload.actor,
            reason=payload.reason or "update settings resource",
            publish=True,
            source="settings_action",
            expected_active_version_id=payload.expected_active_version_id,
            metadata=payload.metadata,
        ),
    )
    return result_response(action, kind, result, mutation="update")
