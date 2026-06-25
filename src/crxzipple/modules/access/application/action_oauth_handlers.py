from __future__ import annotations

from crxzipple.modules.access.application.action_changes import (
    change_bool,
    change_object,
    change_optional_text,
    change_text,
    string_list,
)
from crxzipple.modules.access.application.action_contracts import (
    AccessActionRequest,
    AccessActionResult,
)
from crxzipple.modules.access.application.action_payloads import access_action_decision
from crxzipple.modules.access.application.oauth import AccessOAuthService


def register_oauth_provider(
    request: AccessActionRequest,
    *,
    audit_ref: str,
    oauth_service: AccessOAuthService | None,
) -> AccessActionResult:
    service = _required_oauth_service(oauth_service)
    provider = service.register_provider(
        provider_id=change_text(
            request.changes,
            "provider_id",
            default=request.target_id,
        ),
        display_name=change_optional_text(request.changes, "display_name"),
        provider_kind=change_text(request.changes, "provider_kind", default="oauth2"),
        authorization_url=change_optional_text(request.changes, "authorization_url"),
        token_url=change_optional_text(request.changes, "token_url"),
        revocation_url=change_optional_text(request.changes, "revocation_url"),
        device_code_url=change_optional_text(request.changes, "device_code_url"),
        default_scopes=tuple(string_list(request.changes.get("default_scopes"))),
        client_id=change_optional_text(request.changes, "client_id"),
        client_credential_binding_id=change_optional_text(
            request.changes,
            "client_credential_binding_id",
        ),
        callback_url=change_optional_text(request.changes, "callback_url"),
        callback_mode=change_text(
            request.changes,
            "callback_mode",
            default="manual_code",
        ),
        status=change_text(request.changes, "status", default="active"),
        metadata=change_object(request.changes, "metadata"),
    )
    return AccessActionResult(
        status="succeeded",
        asset={
            "resource_kind": "oauth_provider",
            "provider_id": provider.provider_id,
            "display_name": provider.display_name,
            "provider_kind": provider.provider_kind,
            "status": provider.status,
            "default_scopes": list(provider.default_scopes),
            "callback_mode": provider.callback_mode,
        },
        audit_ref=audit_ref,
        validation={
            "ok": True,
            "after_redacted": {
                "provider_id": provider.provider_id,
                "status": provider.status,
            },
            "permission_decision": access_action_decision(),
        },
    )


def begin_oauth_setup_session(
    request: AccessActionRequest,
    *,
    audit_ref: str,
    oauth_service: AccessOAuthService | None,
) -> AccessActionResult:
    service = _required_oauth_service(oauth_service)
    flow_kind = change_text(request.changes, "flow_kind", default="browser_oauth")
    provider_id = change_text(
        request.changes,
        "provider_id",
        default=request.target_id,
    )
    requested_scopes = tuple(string_list(request.changes.get("scopes")))
    account_id = change_optional_text(request.changes, "account_id")
    credential_binding_id = change_optional_text(
        request.changes,
        "credential_binding_id",
    )
    if flow_kind == "device_code":
        result = service.begin_device_code_setup(
            provider_id=provider_id,
            requested_scopes=requested_scopes,
            account_id=account_id,
            credential_binding_id=credential_binding_id,
            actor=request.actor,
            reason=request.reason,
        )
    elif flow_kind == "browser_oauth":
        result = service.begin_browser_setup(
            provider_id=provider_id,
            requested_scopes=requested_scopes,
            account_id=account_id,
            credential_binding_id=credential_binding_id,
            actor=request.actor,
            reason=request.reason,
        )
    else:
        raise ValueError(
            "OAuth setup flow_kind must be browser_oauth or device_code.",
        )
    return AccessActionResult(
        status="unsupported" if result.status == "unsupported" else "succeeded",
        asset={
            "resource_kind": "oauth_setup_session",
            **result.to_payload(),
        },
        audit_ref=audit_ref,
        validation={
            "ok": True,
            "after_redacted": result.to_payload(),
            "permission_decision": access_action_decision(),
        },
    )


def complete_oauth_setup_session(
    request: AccessActionRequest,
    *,
    audit_ref: str,
    oauth_service: AccessOAuthService | None,
) -> AccessActionResult:
    service = _required_oauth_service(oauth_service)
    result = service.complete_setup_session(
        session_id=change_text(
            request.changes,
            "session_id",
            default=request.target_id,
        ),
        code=change_optional_text(request.changes, "code"),
        state=change_optional_text(request.changes, "state"),
        account_id=change_optional_text(request.changes, "account_id"),
        credential_binding_id=change_optional_text(
            request.changes,
            "credential_binding_id",
        ),
    )
    return AccessActionResult(
        status="succeeded",
        asset=result.to_payload(),
        audit_ref=audit_ref,
        validation={
            "ok": True,
            "after_redacted": result.to_payload(),
            "permission_decision": access_action_decision(),
        },
    )


def begin_codex_oauth_login(
    request: AccessActionRequest,
    *,
    audit_ref: str,
    oauth_service: AccessOAuthService | None,
) -> AccessActionResult:
    service = _required_oauth_service(oauth_service)
    account_id = change_text(
        request.changes,
        "account_id",
        default="openai-codex:default",
    )
    credential_binding_id = change_text(
        request.changes,
        "credential_binding_id",
        default="codex-oauth-default",
    )
    result = service.begin_codex_oauth_login(
        account_id=account_id,
        credential_binding_id=credential_binding_id,
        actor=request.actor,
        reason=request.reason,
        open_browser=change_bool(request.changes, "open_browser", default=True),
    )
    return AccessActionResult(
        status="succeeded",
        asset={
            "resource_kind": "oauth_setup_session",
            "provider_id": "openai-codex",
            "account_id": account_id,
            "credential_binding_id": credential_binding_id,
            **result.to_payload(),
        },
        audit_ref=audit_ref,
        validation={
            "ok": True,
            "after_redacted": {
                "resource_kind": "oauth_setup_session",
                "provider_id": "openai-codex",
                "account_id": account_id,
                "credential_binding_id": credential_binding_id,
                **result.to_payload(),
            },
            "permission_decision": access_action_decision(),
        },
    )


def refresh_oauth_account(
    request: AccessActionRequest,
    *,
    audit_ref: str,
    oauth_service: AccessOAuthService | None,
) -> AccessActionResult:
    service = _required_oauth_service(oauth_service)
    result = service.refresh_account(
        change_text(request.changes, "account_id", default=request.target_id),
    )
    return AccessActionResult(
        status="succeeded",
        asset=result.to_payload(),
        audit_ref=audit_ref,
        validation={
            "ok": True,
            "after_redacted": result.to_payload(),
            "permission_decision": access_action_decision(),
        },
    )


def rotate_oauth_account(
    request: AccessActionRequest,
    *,
    audit_ref: str,
    oauth_service: AccessOAuthService | None,
) -> AccessActionResult:
    service = _required_oauth_service(oauth_service)
    result = service.begin_account_rotation(
        change_text(request.changes, "account_id", default=request.target_id),
        requested_scopes=tuple(string_list(request.changes.get("scopes"))),
        actor=request.actor,
        reason=request.reason,
        flow_kind=change_text(
            request.changes,
            "flow_kind",
            default="browser_oauth",
        ),
    )
    return AccessActionResult(
        status="unsupported" if result.status == "unsupported" else "succeeded",
        asset={
            "resource_kind": "oauth_setup_session",
            **result.to_payload(),
        },
        audit_ref=audit_ref,
        validation={
            "ok": result.status != "unsupported",
            "after_redacted": result.to_payload(),
            "permission_decision": access_action_decision(),
        },
    )


def update_oauth_account_status(
    request: AccessActionRequest,
    *,
    audit_ref: str,
    oauth_service: AccessOAuthService | None,
) -> AccessActionResult:
    service = _required_oauth_service(oauth_service)
    status = "revoked" if request.intent == "revoke_oauth_account" else "disabled"
    account = service.set_account_status(
        change_text(request.changes, "account_id", default=request.target_id),
        status=status,
    )
    return AccessActionResult(
        status="succeeded",
        asset={
            "resource_kind": "oauth_account",
            "account_id": account.account_id,
            "provider_id": account.provider_id,
            "credential_binding_id": account.credential_binding_id,
            "status": account.status,
        },
        audit_ref=audit_ref,
        validation={
            "ok": True,
            "after_redacted": {
                "account_id": account.account_id,
                "status": account.status,
            },
            "permission_decision": access_action_decision(),
        },
    )


def _required_oauth_service(
    oauth_service: AccessOAuthService | None,
) -> AccessOAuthService:
    if oauth_service is None:
        raise RuntimeError("access OAuth service is not configured.")
    return oauth_service
