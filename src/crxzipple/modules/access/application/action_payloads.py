from __future__ import annotations

from crxzipple.modules.access.application.action_contracts import (
    AccessActionRequest,
    AccessActionResult,
    JsonObject,
)
from crxzipple.modules.access.application.events import (
    ACCESS_ACTION_FAILED_EVENT,
    ACCESS_ACTION_SUCCEEDED_EVENT,
    ACCESS_CREDENTIAL_CONFIGURED_EVENT,
    ACCESS_CREDENTIAL_DISABLED_EVENT,
    ACCESS_CREDENTIAL_FAILED_EVENT,
    ACCESS_CREDENTIAL_REVOKED_EVENT,
    ACCESS_CREDENTIAL_ROTATED_EVENT,
    ACCESS_SETUP_COMPLETED_EVENT,
    ACCESS_SETUP_FAILED_EVENT,
    ACCESS_SETUP_STARTED_EVENT,
)


def access_action_success_event_name(intent: str) -> str:
    normalized = intent.strip().lower()
    if normalized in {
        "begin_setup_session",
        "begin_oauth_setup_session",
        "begin_codex_oauth_login",
    }:
        return ACCESS_SETUP_STARTED_EVENT
    if normalized == "complete_oauth_setup_session":
        return ACCESS_SETUP_COMPLETED_EVENT
    if normalized in {"disable_credential_binding", "disable_oauth_account"}:
        return ACCESS_CREDENTIAL_DISABLED_EVENT
    if normalized in {"revoke_credential_binding", "revoke_oauth_account"}:
        return ACCESS_CREDENTIAL_REVOKED_EVENT
    if normalized in {
        "register_env_binding",
        "register_file_binding",
        "register_oauth_account_binding",
        "register_app_credential_binding",
        "update_credential_binding",
    }:
        return ACCESS_CREDENTIAL_CONFIGURED_EVENT
    if normalized in {"refresh_oauth_account", "rotate_oauth_account"}:
        return ACCESS_CREDENTIAL_ROTATED_EVENT
    return ACCESS_ACTION_SUCCEEDED_EVENT


def access_action_failure_event_name(intent: str) -> str:
    normalized = intent.strip().lower()
    if "setup" in normalized or normalized == "begin_codex_oauth_login":
        return ACCESS_SETUP_FAILED_EVENT
    if "credential" in normalized or "oauth_account" in normalized:
        return ACCESS_CREDENTIAL_FAILED_EVENT
    return ACCESS_ACTION_FAILED_EVENT


def audit_result_payload(
    request: AccessActionRequest,
    result: AccessActionResult,
) -> JsonObject:
    validation = dict(result.validation)
    return {
        "actor": request.actor,
        "resource": {
            "kind": request.resource_kind,
            "id": request.target_id,
        },
        "action": request.intent,
        "reason": request.reason,
        "before_redacted": validation.get("before_redacted"),
        "after_redacted": validation.get("after_redacted"),
        "permission_decision": validation.get(
            "permission_decision",
            access_action_decision(),
        ),
        "result": {
            "status": result.status,
            "asset": result.asset,
            "validation": result.validation,
            "readiness": result.readiness,
            "warnings": list(result.warnings),
        },
    }


def access_result_from_settings_result(result: object) -> AccessActionResult:
    return AccessActionResult(
        status=str(getattr(result, "status")),
        asset=getattr(result, "asset", None),
        audit_ref=getattr(result, "audit_ref", None),
        validation=dict(getattr(result, "validation", None) or {}),
        warnings=tuple(getattr(result, "warnings", ())),
    )


def access_action_decision() -> JsonObject:
    return {
        "effect": "allow",
        "code": "access_action_accepted",
        "reason": "external access governance action accepted by Access",
    }
