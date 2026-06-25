from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Any, Mapping
from uuid import uuid4

from crxzipple.modules.access.application.repositories import (
    AccessOAuthAccountRecord,
    AccessOAuthProviderRecord,
)
from crxzipple.modules.access.infrastructure.oauth_tokens import OAuthTokenDocument

from .oauth_token_payloads import (
    default_account_id,
    expires_at_from_payload,
    masked_token,
    optional_text,
    required_text,
    scope_diff_payload,
    scopes_from_token_payload,
    string_tuple,
    subject_from_token_payload,
)


@dataclass(frozen=True, slots=True)
class OAuthStoredAccountRecord:
    token_document: OAuthTokenDocument
    account: AccessOAuthAccountRecord
    credential_binding_id: str


@dataclass(frozen=True, slots=True)
class OAuthSettingsActionRequest:
    action_id: str
    resource_kind: str
    target_id: str | None
    intent: str
    changes: Mapping[str, Any]
    reason: str
    actor: str | None = None
    trace_context: Mapping[str, Any] = field(default_factory=dict)


def oauth_provider_record(
    *,
    provider_id: str,
    display_name: str | None = None,
    provider_kind: str = "oauth2",
    authorization_url: str | None = None,
    token_url: str | None = None,
    revocation_url: str | None = None,
    device_code_url: str | None = None,
    default_scopes: tuple[str, ...] = (),
    client_id: str | None = None,
    client_credential_binding_id: str | None = None,
    callback_url: str | None = None,
    callback_mode: str = "manual_code",
    status: str = "active",
    metadata: Mapping[str, Any] | None = None,
) -> AccessOAuthProviderRecord:
    normalized_provider_id = required_text(provider_id, "provider id")
    return AccessOAuthProviderRecord(
        provider_id=normalized_provider_id,
        display_name=display_name or normalized_provider_id,
        provider_kind=provider_kind,
        authorization_url=optional_text(authorization_url),
        token_url=optional_text(token_url),
        revocation_url=optional_text(revocation_url),
        device_code_url=optional_text(device_code_url),
        default_scopes=string_tuple(default_scopes),
        client_id=optional_text(client_id),
        client_credential_binding_id=optional_text(client_credential_binding_id),
        callback_url=optional_text(callback_url),
        callback_mode=callback_mode or "manual_code",
        status=status or "active",
        redaction_policy={"mode": "metadata_only"},
        metadata=dict(metadata or {}),
    )


def oauth_stored_account_record(
    *,
    provider: AccessOAuthProviderRecord,
    token_payload: Mapping[str, Any],
    account_id: str | None,
    credential_binding_id: str | None,
    storage_key: str,
    metadata: Mapping[str, Any],
    now: datetime,
) -> OAuthStoredAccountRecord:
    access_token = required_text(str(token_payload.get("access_token") or ""), "access token")
    refresh_token = optional_text(token_payload.get("refresh_token"))
    expires_at = expires_at_from_payload(token_payload, now=now)
    scopes = scopes_from_token_payload(token_payload, fallback=provider.default_scopes)
    requested_scopes = string_tuple(metadata.get("requested_scopes"))
    scope_diff = scope_diff_payload(
        declared_scopes=provider.default_scopes,
        requested_scopes=requested_scopes or provider.default_scopes,
        granted_scopes=scopes,
    )
    subject = subject_from_token_payload(token_payload)
    resolved_account_id = resolved_oauth_account_id(
        provider=provider,
        token_payload=token_payload,
        account_id=account_id,
    )
    resolved_binding_id = credential_binding_id or f"oauth:{resolved_account_id}"
    token_document = OAuthTokenDocument(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type=optional_text(token_payload.get("token_type")) or "Bearer",
        expires_at=expires_at,
        scopes=scopes,
        metadata={
            "provider_id": provider.provider_id,
            "account_id": resolved_account_id,
        },
    )
    account = AccessOAuthAccountRecord(
        account_id=resolved_account_id,
        provider_id=provider.provider_id,
        credential_binding_id=resolved_binding_id,
        display_name=subject or provider.display_name,
        subject=subject,
        granted_scopes=scopes,
        expires_at=expires_at,
        refresh_ready=bool(refresh_token),
        status="active",
        storage_key=storage_key,
        masked_preview=masked_token(access_token),
        redaction_policy={"mode": "metadata_only"},
        metadata={
            **dict(metadata),
            "scope_diff": scope_diff,
        },
    )
    return OAuthStoredAccountRecord(
        token_document=token_document,
        account=account,
        credential_binding_id=resolved_binding_id,
    )


def resolved_oauth_account_id(
    *,
    provider: AccessOAuthProviderRecord,
    token_payload: Mapping[str, Any],
    account_id: str | None,
) -> str:
    return account_id or default_account_id(
        provider.provider_id,
        subject_from_token_payload(token_payload),
    )


def refreshed_oauth_account_record(
    account: AccessOAuthAccountRecord,
    token: OAuthTokenDocument,
    *,
    refreshed_at: datetime,
) -> AccessOAuthAccountRecord:
    return replace(
        account,
        granted_scopes=token.scopes or account.granted_scopes,
        expires_at=token.expires_at,
        refresh_ready=bool(token.refresh_token),
        masked_preview=masked_token(token.access_token),
        metadata={
            **dict(account.metadata),
            "last_refresh_at": refreshed_at.isoformat(),
        },
    )


def oauth_account_status_record(
    account: AccessOAuthAccountRecord,
    *,
    status: str,
) -> AccessOAuthAccountRecord:
    return AccessOAuthAccountRecord(
        account_id=account.account_id,
        provider_id=account.provider_id,
        credential_binding_id=account.credential_binding_id,
        display_name=account.display_name,
        subject=account.subject,
        granted_scopes=account.granted_scopes,
        expires_at=account.expires_at,
        refresh_ready=account.refresh_ready,
        status=status,
        storage_key=account.storage_key,
        masked_preview=account.masked_preview,
        redaction_policy=dict(account.redaction_policy),
        metadata=dict(account.metadata),
        created_at=account.created_at,
    )


def oauth_account_binding_request(
    account: AccessOAuthAccountRecord,
    provider: AccessOAuthProviderRecord,
) -> OAuthSettingsActionRequest:
    return OAuthSettingsActionRequest(
        action_id=f"oauth_binding_{uuid4().hex}",
        resource_kind="credential_binding",
        target_id=account.credential_binding_id,
        intent="register_oauth_account_binding",
        changes={
            "binding_id": account.credential_binding_id,
            "binding_kind": (
                "openid_connect"
                if provider.provider_kind == "openid_connect"
                else "oauth2_account"
            ),
            "source_kind": "oauth_account",
            "source_ref": account.account_id,
            "account_id": account.account_id,
            "asset_id": f"oauth_provider:{provider.provider_id}",
            "masked_preview": account.masked_preview,
            "metadata": {
                "provider_id": provider.provider_id,
                "account_id": account.account_id,
            },
        },
        reason="register OAuth account credential binding",
    )
