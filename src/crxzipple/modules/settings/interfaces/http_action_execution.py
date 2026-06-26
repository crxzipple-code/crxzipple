from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from crxzipple.modules.settings.application import (
    PublishSettingsVersionInput,
    RollbackSettingsResourceInput,
    SettingsActionService,
    SettingsQueryService,
)
from crxzipple.modules.settings.application.action_policy import (
    WRITE_ACTIONS,
    SettingsActionName,
    kind_action_allowed,
    kind_action_rejection_message,
    kind_policy_payload,
)
from crxzipple.modules.settings.application.read_models import audit_payload
from crxzipple.modules.settings.interfaces.http_action_helpers import (
    optional_payload_text,
    record_failed_action,
    require_resource_for_action,
    rollback_target_version_id,
)
from crxzipple.modules.settings.interfaces.http_action_mutations import (
    execute_create_action,
    execute_update_action,
)
from crxzipple.modules.settings.interfaces.http_action_models import SettingsActionRequest
from crxzipple.modules.settings.interfaces.http_action_responses import result_response
from crxzipple.modules.settings.interfaces.http_action_validation import (
    execute_validation_action,
)


def execute_settings_action(
    *,
    query: SettingsQueryService,
    actions: SettingsActionService,
    action: SettingsActionName,
    kind: str,
    resource_id: str | None,
    payload: SettingsActionRequest,
) -> dict[str, Any]:
    resolved_id = resource_id or payload.resource_id
    if not kind_action_allowed(kind, action):
        audit = record_failed_action(
            actions,
            action=action,
            kind=kind,
            resource_id=resolved_id,
            actor=payload.actor,
            risk=payload.risk,
            request_payload=payload,
            error={
                "code": "settings_action_not_allowed_for_kind",
                "action": action,
                "kind": kind,
            },
            default_reason="settings action rejected by ownership policy",
        )
        policy = kind_policy_payload(kind)
        raise HTTPException(
            status_code=409,
            detail={
                "code": "settings_action_not_allowed_for_kind",
                "message": kind_action_rejection_message(kind, action),
                "action": action,
                "kind": kind,
                "resource_id": resolved_id,
                "allowed_actions": policy["action_policy"]["allowed_actions"],
                "blocked_actions": policy["action_policy"]["blocked_actions"],
                "owner_module": policy["ownership"]["owner_module"],
                "owner_api": policy["action_policy"]["owner_api"],
                "ownership": policy["ownership"],
                "action_policy": policy["action_policy"],
                "apply_policy": policy["apply_policy"],
                "audit": audit_payload(audit),
            },
        )
    if action in WRITE_ACTIONS and not payload.reason:
        audit = record_failed_action(
            actions,
            action=action,
            kind=kind,
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
                "audit": audit_payload(audit),
            },
    )
    if action in {"dry-run", "validate"}:
        return execute_validation_action(
            query=query,
            actions=actions,
            action=action,
            kind=kind,
            resource_id=resolved_id,
            payload=payload,
        )
    if action == "create":
        return execute_create_action(
            actions=actions,
            action=action,
            kind=kind,
            resource_id=resolved_id,
            payload=payload,
        )
    if resolved_id is None:
        raise ValueError(f"{action} action requires a resource_id.")
    resource = require_resource_for_action(query, kind, resolved_id)
    if action == "update":
        return execute_update_action(
            query=query,
            actions=actions,
            action=action,
            kind=kind,
            resource_id=resource.id,
            payload=payload,
        )
    if action == "publish":
        result = actions.publish_version(
            PublishSettingsVersionInput(
                resource_id=resource.id,
                version_id=optional_payload_text(payload.payload, "version_id"),
                actor=payload.actor,
                reason=payload.reason or "publish settings version",
                expected_active_version_id=payload.expected_active_version_id,
            ),
        )
        return result_response(action, kind, result, mutation="publish")
    if action == "rollback":
        result = actions.rollback_resource(
            RollbackSettingsResourceInput(
                resource_id=resource.id,
                target_version_id=rollback_target_version_id(
                    query,
                    resource,
                    payload.payload,
                ),
                actor=payload.actor,
                reason=payload.reason or "rollback settings resource",
                expected_active_version_id=payload.expected_active_version_id,
            ),
        )
        return result_response(action, kind, result, mutation="rollback")
    if action == "enable":
        result = actions.enable_resource(
            resource.id,
            actor=payload.actor,
            reason=payload.reason or "enable settings resource",
        )
        return result_response(action, kind, result, mutation="enable")
    if action == "disable":
        result = actions.disable_resource(
            resource.id,
            actor=payload.actor,
            reason=payload.reason or "disable settings resource",
        )
        return result_response(action, kind, result, mutation="disable")
    raise ValueError(f"Unsupported Settings action: {action}.")
