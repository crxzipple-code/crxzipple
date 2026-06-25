from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping
from urllib.parse import urlencode

from crxzipple.modules.access.application.repositories import (
    AccessOAuthProviderRecord,
    AccessSetupSessionRecord,
)

from .oauth_contracts import AccessOAuthSetupResult


def browser_authorize_url(
    provider: AccessOAuthProviderRecord,
    *,
    callback_url: str,
    scopes: tuple[str, ...],
    state: str,
    code_challenge: str,
) -> str:
    assert provider.authorization_url is not None
    authorize_params: dict[str, str] = {
        "response_type": "code",
        "client_id": provider.client_id or "",
        "redirect_uri": callback_url,
        "scope": " ".join(scopes),
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    authorize_params.update(authorization_extra_params(provider.metadata))
    return f"{provider.authorization_url}?{urlencode(authorize_params)}"


def browser_setup_session_record(
    *,
    session_id: str,
    provider: AccessOAuthProviderRecord,
    callback_url: str,
    scopes: tuple[str, ...],
    state: str,
    code_verifier: str,
    account_id: str | None,
    credential_binding_id: str | None,
    actor: str | None,
    reason: str,
    expires_at: datetime,
    created_at: datetime,
) -> AccessSetupSessionRecord:
    return AccessSetupSessionRecord(
        session_id=session_id,
        target_kind="oauth_provider",
        target_id=provider.provider_id,
        status="waiting_for_user",
        flow_kind="browser_oauth",
        requested_by=actor,
        expires_at=expires_at,
        redaction_policy={"mode": "metadata_only"},
        metadata={
            "provider_id": provider.provider_id,
            "requested_scopes": list(scopes),
            "account_id": _optional_text(account_id),
            "credential_binding_id": _optional_text(credential_binding_id),
            "callback_url": callback_url,
            "state": state,
            "code_verifier": code_verifier,
            "reason": reason,
        },
        created_at=created_at,
    )


def browser_setup_result(
    *,
    record: AccessSetupSessionRecord,
    provider: AccessOAuthProviderRecord,
    authorize_url: str,
    callback_url: str,
    scopes: tuple[str, ...],
    expires_at: datetime,
) -> AccessOAuthSetupResult:
    return AccessOAuthSetupResult(
        session_id=record.session_id,
        provider_id=provider.provider_id,
        flow_kind="browser_oauth",
        status=record.status,
        authorize_url=authorize_url,
        callback_url=callback_url,
        expires_at=expires_at,
        metadata={
            "declared_scopes": list(provider.default_scopes),
            "requested_scopes": list(scopes),
            "callback_mode": provider.callback_mode,
        },
    )


def unsupported_device_setup_session_record(
    *,
    session_id: str,
    provider: AccessOAuthProviderRecord,
    scopes: tuple[str, ...],
    account_id: str | None,
    credential_binding_id: str | None,
    actor: str | None,
    reason: str,
    expires_at: datetime,
    created_at: datetime,
) -> AccessSetupSessionRecord:
    return AccessSetupSessionRecord(
        session_id=session_id,
        target_kind="oauth_provider",
        target_id=provider.provider_id,
        status="unsupported",
        flow_kind="device_code",
        requested_by=actor,
        expires_at=expires_at,
        redaction_policy={"mode": "metadata_only"},
        metadata={
            "provider_id": provider.provider_id,
            "declared_scopes": list(provider.default_scopes),
            "requested_scopes": list(scopes),
            "account_id": _optional_text(account_id),
            "credential_binding_id": _optional_text(credential_binding_id),
            "reason": reason,
            "unsupported_reason": "oauth_device_code_url_not_configured",
        },
        created_at=created_at,
    )


def unsupported_device_setup_result(
    *,
    record: AccessSetupSessionRecord,
    provider: AccessOAuthProviderRecord,
    scopes: tuple[str, ...],
    expires_at: datetime,
) -> AccessOAuthSetupResult:
    return AccessOAuthSetupResult(
        session_id=record.session_id,
        provider_id=provider.provider_id,
        flow_kind="device_code",
        status="unsupported",
        expires_at=expires_at,
        metadata={
            "declared_scopes": list(provider.default_scopes),
            "requested_scopes": list(scopes),
            "unsupported": True,
            "reason": "oauth_device_code_url_not_configured",
        },
    )


def ready_device_setup_session_record(
    *,
    session_id: str,
    provider: AccessOAuthProviderRecord,
    scopes: tuple[str, ...],
    account_id: str | None,
    credential_binding_id: str | None,
    actor: str | None,
    reason: str,
    device_code: str,
    verification_url: str,
    interval_seconds: int | None,
    expires_at: datetime,
    created_at: datetime,
) -> AccessSetupSessionRecord:
    return AccessSetupSessionRecord(
        session_id=session_id,
        target_kind="oauth_provider",
        target_id=provider.provider_id,
        status="waiting_for_user",
        flow_kind="device_code",
        requested_by=actor,
        expires_at=expires_at,
        redaction_policy={"mode": "metadata_only"},
        metadata={
            "provider_id": provider.provider_id,
            "declared_scopes": list(provider.default_scopes),
            "requested_scopes": list(scopes),
            "account_id": _optional_text(account_id),
            "credential_binding_id": _optional_text(credential_binding_id),
            "reason": reason,
            "device_code_url": provider.device_code_url,
            "device_code": device_code,
            "verification_url": verification_url,
            "interval_seconds": interval_seconds,
            "ready": True,
        },
        created_at=created_at,
    )


def ready_device_setup_result(
    *,
    record: AccessSetupSessionRecord,
    provider: AccessOAuthProviderRecord,
    scopes: tuple[str, ...],
    verification_url: str,
    user_code: str,
    interval_seconds: int | None,
    expires_at: datetime,
) -> AccessOAuthSetupResult:
    return AccessOAuthSetupResult(
        session_id=record.session_id,
        provider_id=provider.provider_id,
        flow_kind="device_code",
        status=record.status,
        verification_url=verification_url,
        user_code=user_code,
        expires_at=expires_at,
        metadata={
            "declared_scopes": list(provider.default_scopes),
            "requested_scopes": list(scopes),
            "ready": True,
            "interval_seconds": interval_seconds,
        },
    )


def authorization_extra_params(metadata: Mapping[str, Any]) -> dict[str, str]:
    raw = metadata.get("authorization_params")
    if not isinstance(raw, Mapping):
        return {}
    result: dict[str, str] = {}
    for key, value in raw.items():
        key_text = str(key).strip()
        value_text = _optional_text(value)
        if key_text and value_text is not None:
            result[key_text] = value_text
    return result


def device_verification_url(payload: Mapping[str, Any]) -> str:
    for key in ("verification_uri_complete", "verification_url_complete"):
        value = _optional_text(payload.get(key))
        if value:
            return value
    for key in ("verification_uri", "verification_url"):
        value = _optional_text(payload.get(key))
        if value:
            return value
    raise ValueError("OAuth device-code endpoint did not return a verification URL.")


def positive_int(value: object) -> int | None:
    if isinstance(value, int) and value > 0:
        return value
    if isinstance(value, float) and value > 0:
        return int(value)
    if isinstance(value, str):
        try:
            parsed = int(value.strip())
        except ValueError:
            return None
        return parsed if parsed > 0 else None
    return None


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None
