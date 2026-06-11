from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from html import escape as html_escape
from http.server import BaseHTTPRequestHandler, HTTPServer
import base64
import hashlib
import json
import secrets
import subprocess
import sys
from threading import Lock, Thread, Timer
from typing import Any, Mapping, Protocol
from urllib.parse import parse_qs, urlencode, urlparse
from uuid import uuid4
import webbrowser

import requests

from crxzipple.modules.access.application.repositories import (
    AccessOAuthAccountRecord,
    AccessOAuthProviderRecord,
    AccessSetupSessionRecord,
)
from crxzipple.modules.access.application.settings_integration import (
    AccessSettingsActionAdapter,
)
from crxzipple.modules.access.infrastructure.oauth_tokens import OAuthTokenDocument
from crxzipple.shared.time import coerce_utc_datetime


JsonObject = dict[str, Any]
DEFAULT_CODEX_OAUTH_PROVIDER_ID = "openai-codex"
DEFAULT_CODEX_OAUTH_ACCOUNT_ID = "openai-codex:default"
DEFAULT_CODEX_OAUTH_BINDING_ID = "codex-oauth-default"
CODEX_OAUTH_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
CODEX_OAUTH_AUTHORIZE_URL = "https://auth.openai.com/oauth/authorize"
CODEX_OAUTH_TOKEN_URL = "https://auth.openai.com/oauth/token"
CODEX_OAUTH_CALLBACK_URL = "http://localhost:1455/auth/callback"
CODEX_OAUTH_CALLBACK_HOST = "localhost"
CODEX_OAUTH_CALLBACK_PORT = 1455
CODEX_OAUTH_CALLBACK_PATH = "/auth/callback"
CODEX_OAUTH_CALLBACK_TIMEOUT_SECONDS = 10 * 60
CODEX_OAUTH_SCOPES = ("openid", "profile", "email", "offline_access")
CODEX_OAUTH_AUTHORIZE_EXTRAS = {
    "id_token_add_organizations": "true",
    "codex_cli_simplified_flow": "true",
    "originator": "pi",
}
CODEX_JWT_AUTH_CLAIM = "https://api.openai.com/auth"
CODEX_JWT_PROFILE_CLAIM = "https://api.openai.com/profile"
_CODEX_OAUTH_CALLBACK_LOCK = Lock()
_CODEX_OAUTH_CALLBACK_ACTIVE: dict[str, Any] | None = None


class AccessOAuthRepository(Protocol):
    def upsert_oauth_provider(
        self,
        record: AccessOAuthProviderRecord,
    ) -> AccessOAuthProviderRecord: ...

    def get_oauth_provider(self, provider_id: str) -> AccessOAuthProviderRecord | None: ...

    def list_oauth_providers(self) -> tuple[AccessOAuthProviderRecord, ...]: ...

    def upsert_oauth_account(
        self,
        record: AccessOAuthAccountRecord,
    ) -> AccessOAuthAccountRecord: ...

    def get_oauth_account(self, account_id: str) -> AccessOAuthAccountRecord | None: ...

    def list_oauth_accounts(self) -> tuple[AccessOAuthAccountRecord, ...]: ...

    def create_setup_session(
        self,
        record: AccessSetupSessionRecord,
    ) -> AccessSetupSessionRecord: ...

    def get_setup_session(self, session_id: str) -> AccessSetupSessionRecord | None: ...

    def complete_setup_session(
        self,
        session_id: str,
        *,
        status: str,
        metadata: JsonObject | None = None,
        completed_at: datetime | None = None,
    ) -> AccessSetupSessionRecord: ...


class AccessOAuthTokenStore(Protocol):
    def storage_key_for_account(self, account_id: str) -> str: ...

    def write_token(
        self,
        storage_key: str,
        document: OAuthTokenDocument | Mapping[str, Any],
    ) -> None: ...

    def read_token(self, storage_key: str) -> OAuthTokenDocument: ...

    def delete_token(self, storage_key: str) -> None: ...


@dataclass(frozen=True, slots=True)
class AccessOAuthSetupResult:
    session_id: str
    provider_id: str
    flow_kind: str
    status: str = "waiting_for_user"
    authorize_url: str | None = None
    callback_url: str | None = None
    verification_url: str | None = None
    user_code: str | None = None
    expires_at: datetime | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_payload(self) -> JsonObject:
        payload: JsonObject = {
            "session_id": self.session_id,
            "provider_id": self.provider_id,
            "flow_kind": self.flow_kind,
            "status": self.status,
            "metadata": _redacted_mapping(self.metadata),
        }
        if self.authorize_url:
            payload["authorize_url"] = self.authorize_url
        if self.callback_url:
            payload["callback_url"] = self.callback_url
        if self.verification_url:
            payload["verification_url"] = self.verification_url
        if self.user_code:
            payload["user_code"] = self.user_code
        if self.expires_at is not None:
            payload["expires_at"] = self.expires_at.isoformat()
        return payload


@dataclass(frozen=True, slots=True)
class AccessOAuthAccountResult:
    account: AccessOAuthAccountRecord
    credential_binding_id: str
    provider: AccessOAuthProviderRecord

    def to_payload(self) -> JsonObject:
        return {
            "resource_kind": "oauth_account",
            "account_id": self.account.account_id,
            "provider_id": self.account.provider_id,
            "credential_binding_id": self.credential_binding_id,
            "display_name": self.account.display_name,
            "subject": self.account.subject,
            "status": self.account.status,
            "granted_scopes": list(self.account.granted_scopes),
            "scope_diff": dict(self.account.metadata.get("scope_diff") or {}),
            "expires_at": (
                self.account.expires_at.isoformat()
                if self.account.expires_at is not None
                else None
            ),
            "refresh_ready": self.account.refresh_ready,
            "masked_preview": self.account.masked_preview,
        }


@dataclass(slots=True)
class AccessOAuthService:
    repository: AccessOAuthRepository
    token_store: AccessOAuthTokenStore
    settings_action_adapter: AccessSettingsActionAdapter | None = None
    now_factory: Any = field(
        default=lambda: datetime.now(timezone.utc),
        repr=False,
    )

    def register_provider(
        self,
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
        normalized_provider_id = _required_text(provider_id, "provider id")
        return self.repository.upsert_oauth_provider(
            AccessOAuthProviderRecord(
                provider_id=normalized_provider_id,
                display_name=display_name or normalized_provider_id,
                provider_kind=provider_kind,
                authorization_url=_optional_text(authorization_url),
                token_url=_optional_text(token_url),
                revocation_url=_optional_text(revocation_url),
                device_code_url=_optional_text(device_code_url),
                default_scopes=_string_tuple(default_scopes),
                client_id=_optional_text(client_id),
                client_credential_binding_id=_optional_text(
                    client_credential_binding_id,
                ),
                callback_url=_optional_text(callback_url),
                callback_mode=callback_mode or "manual_code",
                status=status or "active",
                redaction_policy={"mode": "metadata_only"},
                metadata=dict(metadata or {}),
            ),
        )

    def ensure_default_codex_provider(self) -> AccessOAuthProviderRecord:
        existing = self.repository.get_oauth_provider(DEFAULT_CODEX_OAUTH_PROVIDER_ID)
        metadata = dict(existing.metadata) if existing is not None else {}
        metadata.update(
            {
                "setup_source": "builtin_oauth",
                "reference": "openclaw.models.auth.login.openai_codex",
                "authorization_params": dict(CODEX_OAUTH_AUTHORIZE_EXTRAS),
            },
        )
        return self.register_provider(
            provider_id=DEFAULT_CODEX_OAUTH_PROVIDER_ID,
            display_name="OpenAI Codex",
            provider_kind="oauth2",
            authorization_url=CODEX_OAUTH_AUTHORIZE_URL,
            token_url=CODEX_OAUTH_TOKEN_URL,
            default_scopes=CODEX_OAUTH_SCOPES,
            client_id=CODEX_OAUTH_CLIENT_ID,
            callback_url=CODEX_OAUTH_CALLBACK_URL,
            callback_mode="local_callback_or_manual",
            status=existing.status if existing is not None else "active",
            metadata=metadata,
        )

    def begin_browser_setup(
        self,
        *,
        provider_id: str,
        requested_scopes: tuple[str, ...] = (),
        account_id: str | None = None,
        credential_binding_id: str | None = None,
        actor: str | None = None,
        reason: str = "begin OAuth setup",
    ) -> AccessOAuthSetupResult:
        provider = (
            self.ensure_default_codex_provider()
            if provider_id == DEFAULT_CODEX_OAUTH_PROVIDER_ID
            else self._active_provider(provider_id)
        )
        if provider.status != "active":
            raise ValueError(f"OAuth provider '{provider.provider_id}' is {provider.status}.")
        if not provider.authorization_url:
            raise ValueError(
                f"OAuth provider '{provider.provider_id}' does not declare an authorization URL.",
            )
        if not provider.client_id:
            raise ValueError(
                f"OAuth provider '{provider.provider_id}' does not declare a client id.",
            )
        callback_url = provider.callback_url or "http://127.0.0.1:1455/access/oauth/callback"
        scopes = requested_scopes or provider.default_scopes
        state = secrets.token_hex(16)
        code_verifier = secrets.token_urlsafe(48)
        code_challenge = _pkce_challenge(code_verifier)
        expires_at = self._now() + timedelta(minutes=30)
        authorize_params: dict[str, str] = {
            'response_type': 'code',
            'client_id': provider.client_id,
            'redirect_uri': callback_url,
            'scope': ' '.join(scopes),
            'state': state,
            'code_challenge': code_challenge,
            'code_challenge_method': 'S256',
        }
        authorize_params.update(_authorization_extra_params(provider.metadata))
        authorize_url = f"{provider.authorization_url}?{urlencode(authorize_params)}"
        record = self.repository.create_setup_session(
            AccessSetupSessionRecord(
                session_id=f"oauthsetup_{uuid4().hex}",
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
                created_at=self._now(),
            ),
        )
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

    def begin_device_code_setup(
        self,
        *,
        provider_id: str,
        requested_scopes: tuple[str, ...] = (),
        account_id: str | None = None,
        credential_binding_id: str | None = None,
        actor: str | None = None,
        reason: str = "begin OAuth device-code setup",
    ) -> AccessOAuthSetupResult:
        provider = self._active_provider(provider_id)
        scopes = requested_scopes or provider.default_scopes
        expires_at = self._now() + timedelta(minutes=30)
        if not provider.device_code_url:
            record = self.repository.create_setup_session(
                AccessSetupSessionRecord(
                    session_id=f"oauthsetup_{uuid4().hex}",
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
                    created_at=self._now(),
                ),
            )
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
        if not provider.client_id:
            raise ValueError(
                f"OAuth provider '{provider.provider_id}' does not declare a client id.",
            )
        if not provider.token_url:
            raise ValueError(
                f"OAuth provider '{provider.provider_id}' does not declare a token URL.",
            )
        device_payload = self._request_device_code(provider, requested_scopes=scopes)
        device_code = _required_text(
            str(device_payload.get("device_code") or ""),
            "OAuth device code",
        )
        user_code = _required_text(
            str(device_payload.get("user_code") or ""),
            "OAuth user code",
        )
        verification_url = _device_verification_url(device_payload)
        interval_seconds = _positive_int(device_payload.get("interval"))
        device_expires_at = _expires_at_from_payload(device_payload, now=self._now())
        if device_expires_at is not None:
            expires_at = device_expires_at
        record = self.repository.create_setup_session(
            AccessSetupSessionRecord(
                session_id=f"oauthsetup_{uuid4().hex}",
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
                created_at=self._now(),
            ),
        )
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

    def complete_setup_session(
        self,
        *,
        session_id: str,
        code: str | None = None,
        state: str | None = None,
        account_id: str | None = None,
        credential_binding_id: str | None = None,
    ) -> AccessOAuthAccountResult:
        session = self._setup_session_record(session_id)
        if session.flow_kind == "browser_oauth":
            return self.complete_browser_setup(
                session_id=session_id,
                code=_required_text(code, "authorization code"),
                state=state,
                account_id=account_id,
                credential_binding_id=credential_binding_id,
            )
        if session.flow_kind == "device_code":
            return self.complete_device_code_setup(
                session_id=session_id,
                account_id=account_id,
                credential_binding_id=credential_binding_id,
            )
        raise ValueError(f"Unsupported OAuth setup flow '{session.flow_kind}'.")

    def complete_browser_setup(
        self,
        *,
        session_id: str,
        code: str,
        state: str | None = None,
        account_id: str | None = None,
        credential_binding_id: str | None = None,
    ) -> AccessOAuthAccountResult:
        session = self._setup_session(session_id, flow_kind="browser_oauth")
        provider = self._active_provider(session.target_id)
        session_metadata = dict(session.metadata)
        expected_state = _optional_text(session_metadata.get("state"))
        if expected_state and (state is None or expected_state != state.strip()):
            raise ValueError("OAuth setup state does not match.")
        if session.expires_at is not None and session.expires_at < self._now():
            raise ValueError("OAuth setup session has expired.")
        if not provider.token_url:
            raise ValueError(
                f"OAuth provider '{provider.provider_id}' does not declare a token URL.",
            )
        token_payload = self._exchange_authorization_code(
            provider,
            code=code,
            code_verifier=_required_text(
                str(session_metadata.get("code_verifier") or ""),
                "code verifier",
            ),
            callback_url=_required_text(
                str(session_metadata.get("callback_url") or ""),
                "callback URL",
            ),
        )
        if provider.provider_id == DEFAULT_CODEX_OAUTH_PROVIDER_ID:
            token_payload = _codex_token_payload_with_identity(token_payload)
        result = self._store_account_from_token_payload(
            provider,
            token_payload,
            account_id=account_id or _optional_text(session_metadata.get("account_id")),
            credential_binding_id=(
                credential_binding_id
                or _optional_text(session_metadata.get("credential_binding_id"))
            ),
            metadata={
                "setup_session_id": session.session_id,
                "setup_flow": "browser_oauth",
                "declared_scopes": list(provider.default_scopes),
                "requested_scopes": list(
                    _string_tuple(session_metadata.get("requested_scopes")),
                ),
            },
        )
        self.repository.complete_setup_session(
            session.session_id,
            status="completed",
            metadata={
                "account_id": result.account.account_id,
                "credential_binding_id": result.credential_binding_id,
            },
            completed_at=self._now(),
        )
        return result

    def complete_device_code_setup(
        self,
        *,
        session_id: str,
        account_id: str | None = None,
        credential_binding_id: str | None = None,
    ) -> AccessOAuthAccountResult:
        session = self._setup_session(session_id, flow_kind="device_code")
        provider = self._active_provider(session.target_id)
        session_metadata = dict(session.metadata)
        if session.expires_at is not None and session.expires_at < self._now():
            raise ValueError("OAuth setup session has expired.")
        token_payload = self._exchange_device_code(
            provider,
            device_code=_required_text(
                str(session_metadata.get("device_code") or ""),
                "OAuth device code",
            ),
        )
        result = self._store_account_from_token_payload(
            provider,
            token_payload,
            account_id=account_id or _optional_text(session_metadata.get("account_id")),
            credential_binding_id=(
                credential_binding_id
                or _optional_text(session_metadata.get("credential_binding_id"))
            ),
            metadata={
                "setup_session_id": session.session_id,
                "setup_flow": "device_code",
                "declared_scopes": list(provider.default_scopes),
                "requested_scopes": list(
                    _string_tuple(session_metadata.get("requested_scopes")),
                ),
            },
        )
        self.repository.complete_setup_session(
            session.session_id,
            status="completed",
            metadata={
                "account_id": result.account.account_id,
                "credential_binding_id": result.credential_binding_id,
            },
            completed_at=self._now(),
        )
        return result

    def begin_codex_oauth_login(
        self,
        *,
        account_id: str = DEFAULT_CODEX_OAUTH_ACCOUNT_ID,
        credential_binding_id: str = DEFAULT_CODEX_OAUTH_BINDING_ID,
        actor: str | None = None,
        reason: str = "begin OpenAI Codex OAuth login",
        open_browser: bool = True,
    ) -> AccessOAuthSetupResult:
        setup = self.begin_browser_setup(
            provider_id=DEFAULT_CODEX_OAUTH_PROVIDER_ID,
            requested_scopes=CODEX_OAUTH_SCOPES,
            account_id=account_id,
            credential_binding_id=credential_binding_id,
            actor=actor,
            reason=reason,
        )
        assert setup.authorize_url is not None
        listener = _start_codex_oauth_callback_listener(
            service=self,
            session_id=setup.session_id,
            account_id=account_id,
            credential_binding_id=credential_binding_id,
            timeout_seconds=CODEX_OAUTH_CALLBACK_TIMEOUT_SECONDS,
        )
        browser_opened = _open_browser_url(setup.authorize_url) if open_browser else False
        return replace(
            setup,
            metadata={
                **dict(setup.metadata),
                "account_id": account_id,
                "credential_binding_id": credential_binding_id,
                "callback_listener": listener,
                "browser_opened": browser_opened,
                "manual_input_supported": True,
            },
        )

    def resolve_access_token(self, account_id: str) -> str:
        account = self._active_account(account_id)
        storage_key = _required_text(account.storage_key or "", "OAuth token storage key")
        token = self.token_store.read_token(storage_key)
        if _token_should_refresh(token, now=self._now()) and token.refresh_token:
            self.refresh_account(account.account_id)
            token = self.token_store.read_token(storage_key)
        if token.expires_at is not None and token.expires_at <= self._now():
            raise ValueError(f"OAuth account '{account.account_id}' is expired.")
        return token.access_token

    def refresh_account(self, account_id: str) -> AccessOAuthAccountResult:
        account = self._active_account(account_id)
        storage_key = _required_text(account.storage_key or "", "OAuth token storage key")
        token = self.token_store.read_token(storage_key)
        if not token.refresh_token:
            raise ValueError(
                f"OAuth account '{account.account_id}' does not have a refresh token.",
            )
        provider = self._active_provider(account.provider_id)
        if not provider.token_url:
            raise ValueError(
                f"OAuth provider '{provider.provider_id}' does not declare a token URL.",
            )
        refreshed = self._refresh_token(provider, token)
        self.token_store.write_token(storage_key, refreshed)
        updated = self.repository.upsert_oauth_account(
            replace(
                account,
                granted_scopes=refreshed.scopes or account.granted_scopes,
                expires_at=refreshed.expires_at,
                refresh_ready=bool(refreshed.refresh_token),
                masked_preview=_masked_token(refreshed.access_token),
                metadata={
                    **dict(account.metadata),
                    "last_refresh_at": self._now().isoformat(),
                },
            ),
        )
        return AccessOAuthAccountResult(
            account=updated,
            credential_binding_id=_required_text(
                updated.credential_binding_id or "",
                "OAuth credential binding id",
            ),
            provider=provider,
        )

    def begin_account_rotation(
        self,
        account_id: str,
        *,
        requested_scopes: tuple[str, ...] = (),
        actor: str | None = None,
        reason: str = "rotate OAuth account",
        flow_kind: str = "browser_oauth",
    ) -> AccessOAuthSetupResult:
        account = self._active_or_existing_account(account_id)
        if account.status == "revoked":
            raise ValueError(f"OAuth account '{account.account_id}' is revoked.")
        if flow_kind == "device_code":
            return self.begin_device_code_setup(
                provider_id=account.provider_id,
                requested_scopes=requested_scopes,
                account_id=account.account_id,
                credential_binding_id=account.credential_binding_id,
                actor=actor,
                reason=reason,
            )
        if flow_kind == "browser_oauth":
            return self.begin_browser_setup(
                provider_id=account.provider_id,
                requested_scopes=requested_scopes,
                account_id=account.account_id,
                credential_binding_id=account.credential_binding_id,
                actor=actor,
                reason=reason,
            )
        raise ValueError("OAuth rotate flow_kind must be browser_oauth or device_code.")

    def set_account_status(self, account_id: str, *, status: str) -> AccessOAuthAccountRecord:
        account = self._active_or_existing_account(account_id)
        if status == "revoked":
            self._revoke_account_token(account)
        updated = AccessOAuthAccountRecord(
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
        if status == "revoked" and account.storage_key:
            self.token_store.delete_token(account.storage_key)
        return self.repository.upsert_oauth_account(updated)

    def _store_account_from_token_payload(
        self,
        provider: AccessOAuthProviderRecord,
        token_payload: Mapping[str, Any],
        *,
        account_id: str | None,
        credential_binding_id: str | None,
        metadata: Mapping[str, Any],
    ) -> AccessOAuthAccountResult:
        access_token = _required_text(str(token_payload.get("access_token") or ""), "access token")
        refresh_token = _optional_text(token_payload.get("refresh_token"))
        expires_at = _expires_at_from_payload(token_payload, now=self._now())
        scopes = _scopes_from_token_payload(token_payload, fallback=provider.default_scopes)
        requested_scopes = _string_tuple(metadata.get("requested_scopes"))
        scope_diff = _scope_diff_payload(
            declared_scopes=provider.default_scopes,
            requested_scopes=requested_scopes or provider.default_scopes,
            granted_scopes=scopes,
        )
        subject = _subject_from_token_payload(token_payload)
        resolved_account_id = account_id or _default_account_id(provider.provider_id, subject)
        resolved_binding_id = credential_binding_id or f"oauth:{resolved_account_id}"
        storage_key = self.token_store.storage_key_for_account(resolved_account_id)
        document = OAuthTokenDocument(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type=_optional_text(token_payload.get("token_type")) or "Bearer",
            expires_at=expires_at,
            scopes=scopes,
            metadata={
                "provider_id": provider.provider_id,
                "account_id": resolved_account_id,
            },
        )
        self.token_store.write_token(storage_key, document)
        account = self.repository.upsert_oauth_account(
            AccessOAuthAccountRecord(
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
                masked_preview=_masked_token(access_token),
                redaction_policy={"mode": "metadata_only"},
                metadata={
                    **dict(metadata),
                    "scope_diff": scope_diff,
                },
            ),
        )
        self._register_oauth_account_binding(account, provider)
        return AccessOAuthAccountResult(
            account=account,
            credential_binding_id=resolved_binding_id,
            provider=provider,
        )

    def _register_oauth_account_binding(
        self,
        account: AccessOAuthAccountRecord,
        provider: AccessOAuthProviderRecord,
    ) -> None:
        if self.settings_action_adapter is None or not account.credential_binding_id:
            return
        request = _SettingsActionRequest(
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
        self.settings_action_adapter.execute_config_action(request)

    def _exchange_authorization_code(
        self,
        provider: AccessOAuthProviderRecord,
        *,
        code: str,
        code_verifier: str,
        callback_url: str,
    ) -> JsonObject:
        assert provider.token_url is not None
        payload = {
            "grant_type": "authorization_code",
            "code": _required_text(code, "authorization code"),
            "redirect_uri": callback_url,
            "client_id": provider.client_id,
            "code_verifier": code_verifier,
        }
        response = requests.post(
            provider.token_url,
            data=payload,
            timeout=30,
        )
        response.raise_for_status()
        decoded = response.json()
        if not isinstance(decoded, Mapping):
            raise ValueError("OAuth token endpoint returned a non-object payload.")
        return dict(decoded)

    def _request_device_code(
        self,
        provider: AccessOAuthProviderRecord,
        *,
        requested_scopes: tuple[str, ...],
    ) -> JsonObject:
        assert provider.device_code_url is not None
        payload = {
            "client_id": provider.client_id,
            "scope": " ".join(requested_scopes),
        }
        response = requests.post(provider.device_code_url, data=payload, timeout=30)
        response.raise_for_status()
        decoded = response.json()
        if not isinstance(decoded, Mapping):
            raise ValueError("OAuth device-code endpoint returned a non-object payload.")
        return dict(decoded)

    def _exchange_device_code(
        self,
        provider: AccessOAuthProviderRecord,
        *,
        device_code: str,
    ) -> JsonObject:
        if not provider.token_url:
            raise ValueError(
                f"OAuth provider '{provider.provider_id}' does not declare a token URL.",
            )
        payload = {
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            "device_code": _required_text(device_code, "OAuth device code"),
            "client_id": provider.client_id,
        }
        response = requests.post(provider.token_url, data=payload, timeout=30)
        response.raise_for_status()
        decoded = response.json()
        if not isinstance(decoded, Mapping):
            raise ValueError("OAuth device-code token endpoint returned a non-object payload.")
        error = _optional_text(decoded.get("error"))
        if error:
            if error in {"authorization_pending", "slow_down"}:
                raise ValueError(f"OAuth device-code authorization is still pending: {error}.")
            raise ValueError(f"OAuth device-code authorization failed: {error}.")
        return dict(decoded)

    def _refresh_token(
        self,
        provider: AccessOAuthProviderRecord,
        token: OAuthTokenDocument,
    ) -> OAuthTokenDocument:
        if not provider.token_url:
            return token
        payload = {
            "grant_type": "refresh_token",
            "refresh_token": token.refresh_token,
            "client_id": provider.client_id,
        }
        response = requests.post(provider.token_url, data=payload, timeout=30)
        response.raise_for_status()
        decoded = response.json()
        if not isinstance(decoded, Mapping):
            raise ValueError("OAuth refresh endpoint returned a non-object payload.")
        merged = {
            **token.to_payload(),
            **dict(decoded),
        }
        if "expires_in" in decoded:
            merged["expires_at"] = _expires_at_from_payload(decoded, now=self._now())
        return OAuthTokenDocument.from_payload(merged)

    def _revoke_account_token(self, account: AccessOAuthAccountRecord) -> None:
        if not account.storage_key:
            return
        provider = self.repository.get_oauth_provider(account.provider_id)
        if provider is None or not provider.revocation_url:
            return
        token = self.token_store.read_token(account.storage_key)
        response = requests.post(
            provider.revocation_url,
            data={
                "token": token.access_token,
                "client_id": provider.client_id,
            },
            timeout=30,
        )
        response.raise_for_status()

    def _active_provider(self, provider_id: str) -> AccessOAuthProviderRecord:
        provider = self.repository.get_oauth_provider(_required_text(provider_id, "provider id"))
        if provider is None:
            raise LookupError(f"OAuth provider '{provider_id}' was not found.")
        if provider.status != "active":
            raise ValueError(f"OAuth provider '{provider.provider_id}' is {provider.status}.")
        return provider

    def _setup_session_record(self, session_id: str) -> AccessSetupSessionRecord:
        session = self.repository.get_setup_session(
            _required_text(session_id, "setup session id"),
        )
        if session is None:
            raise LookupError(f"OAuth setup session '{session_id}' was not found.")
        if session.status != "waiting_for_user":
            raise ValueError(f"OAuth setup session '{session_id}' is {session.status}.")
        return session

    def _setup_session(
        self,
        session_id: str,
        *,
        flow_kind: str,
    ) -> AccessSetupSessionRecord:
        session = self._setup_session_record(session_id)
        if session.flow_kind != flow_kind:
            raise ValueError(f"Setup session '{session_id}' is not a {flow_kind} flow.")
        return session

    def _active_account(self, account_id: str) -> AccessOAuthAccountRecord:
        account = self._active_or_existing_account(account_id)
        if account.status != "active":
            raise ValueError(f"OAuth account '{account.account_id}' is {account.status}.")
        return account

    def _active_or_existing_account(self, account_id: str) -> AccessOAuthAccountRecord:
        account = self.repository.get_oauth_account(_required_text(account_id, "OAuth account id"))
        if account is None:
            raise LookupError(f"OAuth account '{account_id}' was not found.")
        return account

    def _now(self) -> datetime:
        return coerce_utc_datetime(self.now_factory())


@dataclass(frozen=True, slots=True)
class _SettingsActionRequest:
    action_id: str
    resource_kind: str
    target_id: str | None
    intent: str
    changes: Mapping[str, Any]
    reason: str
    actor: str | None = None
    trace_context: Mapping[str, Any] = field(default_factory=dict)


def _expires_at_from_payload(
    payload: Mapping[str, Any],
    *,
    now: datetime,
) -> datetime | None:
    expires_at = _coerce_optional_datetime(payload.get("expires_at"))
    if expires_at is not None:
        return expires_at
    expires_in = payload.get("expires_in")
    if isinstance(expires_in, (int, float)) and expires_in > 0:
        return now + timedelta(seconds=float(expires_in))
    if isinstance(expires_in, str):
        try:
            seconds = float(expires_in.strip())
        except ValueError:
            return None
        if seconds > 0:
            return now + timedelta(seconds=seconds)
    return None


def _device_verification_url(payload: Mapping[str, Any]) -> str:
    for key in ("verification_uri_complete", "verification_url_complete"):
        value = _optional_text(payload.get(key))
        if value:
            return value
    for key in ("verification_uri", "verification_url"):
        value = _optional_text(payload.get(key))
        if value:
            return value
    raise ValueError("OAuth device-code endpoint did not return a verification URL.")


def _positive_int(value: object) -> int | None:
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


def _coerce_optional_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return coerce_utc_datetime(value)
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value), tz=timezone.utc)
    if isinstance(value, str):
        normalized = value.strip()
        if not normalized:
            return None
        if normalized.endswith("Z"):
            normalized = f"{normalized[:-1]}+00:00"
        return coerce_utc_datetime(datetime.fromisoformat(normalized))
    return None


def _scopes_from_token_payload(
    payload: Mapping[str, Any],
    *,
    fallback: tuple[str, ...],
) -> tuple[str, ...]:
    scope_value = payload.get("scope") or payload.get("scopes")
    if isinstance(scope_value, str):
        scopes = tuple(item for item in scope_value.replace(",", " ").split() if item)
    elif isinstance(scope_value, (list, tuple)):
        scopes = tuple(str(item).strip() for item in scope_value if str(item).strip())
    else:
        scopes = fallback
    return tuple(dict.fromkeys(scopes))


def _subject_from_token_payload(payload: Mapping[str, Any]) -> str | None:
    for key in ("email", "account", "account_id", "sub"):
        value = _optional_text(payload.get(key))
        if value is not None:
            return value
    id_token = _optional_text(payload.get("id_token"))
    if id_token is None:
        return None
    parts = id_token.split(".")
    if len(parts) < 2:
        return None
    try:
        padded = parts[1] + "=" * ((4 - len(parts[1]) % 4) % 4)
        decoded = base64.urlsafe_b64decode(padded.encode("ascii"))
        decoded_payload = json.loads(decoded.decode("utf-8"))
    except (ValueError, json.JSONDecodeError):
        return None
    if not isinstance(decoded_payload, Mapping):
        return None
    return _optional_text(decoded_payload.get("email")) or _optional_text(
        decoded_payload.get("sub"),
    )


def _codex_token_payload_with_identity(payload: JsonObject) -> JsonObject:
    access_token = _required_text(str(payload.get("access_token") or ""), "access token")
    decoded = _decode_jwt_payload(access_token)
    account_id = _codex_account_id(decoded)
    if not account_id:
        raise ValueError("Failed to extract OpenAI Codex account id from access token.")
    profile = decoded.get(CODEX_JWT_PROFILE_CLAIM) if decoded else None
    email = (
        _optional_text(profile.get("email"))
        if isinstance(profile, Mapping)
        else None
    )
    return {
        **payload,
        "account_id": payload.get("account_id") or account_id,
        "email": payload.get("email") or email,
    }


def _decode_jwt_payload(token: str) -> JsonObject:
    parts = token.split(".")
    if len(parts) < 2:
        return {}
    try:
        padded = parts[1] + "=" * ((4 - len(parts[1]) % 4) % 4)
        decoded = base64.urlsafe_b64decode(padded.encode("ascii"))
        payload = json.loads(decoded.decode("utf-8"))
    except (ValueError, json.JSONDecodeError):
        return {}
    return dict(payload) if isinstance(payload, Mapping) else {}


def _codex_account_id(payload: Mapping[str, Any]) -> str | None:
    auth = payload.get(CODEX_JWT_AUTH_CLAIM)
    if not isinstance(auth, Mapping):
        return None
    for key in (
        "chatgpt_account_id",
        "chatgpt_account_user_id",
        "chatgpt_user_id",
        "user_id",
    ):
        value = _optional_text(auth.get(key))
        if value:
            return value
    return None


def _token_should_refresh(token: OAuthTokenDocument, *, now: datetime) -> bool:
    if token.expires_at is None:
        return False
    return token.expires_at <= now + timedelta(minutes=5)


def _masked_token(value: str) -> str:
    if len(value) <= 10:
        return "***"
    return f"{value[:4]}...{value[-4:]}"


def _default_account_id(provider_id: str, subject: str | None) -> str:
    suffix = subject or uuid4().hex
    return f"{provider_id}:{_safe_id_part(suffix)}"


def _safe_id_part(value: str) -> str:
    normalized = "".join(
        char if char.isalnum() or char in {"_", "-", "."} else "_"
        for char in value.strip()
    ).strip("._")
    return normalized or "default"


def _authorization_extra_params(metadata: Mapping[str, Any]) -> dict[str, str]:
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


def _start_codex_oauth_callback_listener(
    *,
    service: AccessOAuthService,
    session_id: str,
    account_id: str,
    credential_binding_id: str,
    timeout_seconds: int,
) -> JsonObject:
    _stop_active_codex_oauth_callback_listener(
        service=service,
        reason="OpenAI Codex OAuth callback listener was superseded by a newer login.",
        superseded_by_session_id=session_id,
    )
    completed = {"value": False}

    class CodexOAuthHTTPServer(HTTPServer):
        allow_reuse_address = True

    class CodexCallbackHandler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            return

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path != CODEX_OAUTH_CALLBACK_PATH:
                self.send_error(404, "Not found")
                return

            values = parse_qs(parsed.query)
            code = _optional_text((values.get("code") or [""])[0])
            state = _optional_text((values.get("state") or [""])[0])
            if code is None:
                self._send_html(
                    400,
                    "Authentication failed",
                    "OpenAI did not return an authorization code.",
                )
                _shutdown_callback_server()
                return

            try:
                service.complete_browser_setup(
                    session_id=session_id,
                    code=code,
                    state=state,
                    account_id=account_id,
                    credential_binding_id=credential_binding_id,
                )
            except Exception as exc:
                _mark_setup_session("failed", {"error": str(exc)})
                self._send_html(500, "Authentication failed", str(exc))
                _shutdown_callback_server()
                return

            self._send_html(
                200,
                "Authentication successful",
                "OpenAI Codex OAuth is connected. You can return to CRXZIPPLE.",
            )
            _shutdown_callback_server()

        def _send_html(self, status: int, title: str, message: str) -> None:
            body = _oauth_callback_html(title, message).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    try:
        server = CodexOAuthHTTPServer(
            (CODEX_OAUTH_CALLBACK_HOST, CODEX_OAUTH_CALLBACK_PORT),
            CodexCallbackHandler,
        )
    except OSError as exc:
        raise ValueError(
            "OpenAI Codex OAuth callback listener could not bind "
            f"{CODEX_OAUTH_CALLBACK_URL}: {exc}",
        ) from exc

    def _mark_setup_session(status: str, metadata: JsonObject) -> None:
        try:
            service.repository.complete_setup_session(
                session_id,
                status=status,
                metadata=metadata,
                completed_at=service._now(),
            )
        except Exception:
            return

    def _shutdown_callback_server() -> None:
        if completed["value"]:
            return
        completed["value"] = True
        _clear_active_codex_oauth_callback_listener(
            session_id=session_id,
            completed=completed,
        )
        Thread(target=server.shutdown, daemon=True).start()

    def _expire_callback_server() -> None:
        if completed["value"]:
            return
        _mark_setup_session(
            "expired",
            {"error": "OpenAI Codex OAuth callback timed out."},
        )
        _shutdown_callback_server()

    def _serve() -> None:
        timer = Timer(timeout_seconds, _expire_callback_server)
        timer.daemon = True
        timer.start()
        try:
            server.serve_forever(poll_interval=0.2)
        finally:
            timer.cancel()
            server.server_close()

    _register_active_codex_oauth_callback_listener(
        session_id=session_id,
        server=server,
        completed=completed,
    )
    Thread(target=_serve, name=f"codex-oauth-{session_id}", daemon=True).start()
    return {
        "status": "listening",
        "host": CODEX_OAUTH_CALLBACK_HOST,
        "port": CODEX_OAUTH_CALLBACK_PORT,
        "path": CODEX_OAUTH_CALLBACK_PATH,
        "timeout_seconds": timeout_seconds,
    }


def _register_active_codex_oauth_callback_listener(
    *,
    session_id: str,
    server: HTTPServer,
    completed: dict[str, bool],
) -> None:
    global _CODEX_OAUTH_CALLBACK_ACTIVE
    with _CODEX_OAUTH_CALLBACK_LOCK:
        _CODEX_OAUTH_CALLBACK_ACTIVE = {
            "session_id": session_id,
            "server": server,
            "completed": completed,
        }


def _clear_active_codex_oauth_callback_listener(
    *,
    session_id: str,
    completed: dict[str, bool],
) -> None:
    global _CODEX_OAUTH_CALLBACK_ACTIVE
    with _CODEX_OAUTH_CALLBACK_LOCK:
        active = _CODEX_OAUTH_CALLBACK_ACTIVE
        if active is None:
            return
        if active.get("session_id") != session_id:
            return
        if active.get("completed") is not completed:
            return
        _CODEX_OAUTH_CALLBACK_ACTIVE = None


def _stop_active_codex_oauth_callback_listener(
    *,
    service: AccessOAuthService,
    reason: str,
    superseded_by_session_id: str | None = None,
) -> None:
    global _CODEX_OAUTH_CALLBACK_ACTIVE
    with _CODEX_OAUTH_CALLBACK_LOCK:
        active = _CODEX_OAUTH_CALLBACK_ACTIVE
        _CODEX_OAUTH_CALLBACK_ACTIVE = None
    if active is None:
        return

    completed = active.get("completed")
    if isinstance(completed, dict):
        if completed.get("value"):
            return
        completed["value"] = True

    previous_session_id = _optional_text(active.get("session_id"))
    if previous_session_id is not None:
        metadata: JsonObject = {
            "error": reason,
            "callback_listener": {"status": "superseded"},
        }
        if superseded_by_session_id is not None:
            metadata["superseded_by_session_id"] = superseded_by_session_id
        try:
            service.repository.complete_setup_session(
                previous_session_id,
                status="expired",
                metadata=metadata,
                completed_at=service._now(),
            )
        except Exception:
            pass

    server = active.get("server")
    if isinstance(server, HTTPServer):
        try:
            server.shutdown()
        finally:
            server.server_close()


def _oauth_callback_html(title: str, message: str) -> str:
    return (
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\" />"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />"
        f"<title>{html_escape(title)}</title></head><body>"
        f"<p>{html_escape(message)}</p></body></html>"
    )


def _open_browser_url(url: str) -> bool:
    try:
        if sys.platform == "darwin":
            subprocess.Popen(
                ("open", url),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return True
        return bool(webbrowser.open_new_tab(url))
    except Exception:
        return False


def _pkce_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def _required_text(value: str | None, label: str) -> str:
    normalized = (value or "").strip()
    if not normalized:
        raise ValueError(f"{label} is required.")
    return normalized


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _string_tuple(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        return tuple(item for item in value.replace(",", " ").split() if item)
    if isinstance(value, (list, tuple)):
        return tuple(str(item).strip() for item in value if str(item).strip())
    return ()


def _scope_diff_payload(
    *,
    declared_scopes: tuple[str, ...],
    requested_scopes: tuple[str, ...],
    granted_scopes: tuple[str, ...],
) -> JsonObject:
    declared = tuple(dict.fromkeys(scope for scope in declared_scopes if scope))
    requested = tuple(dict.fromkeys(scope for scope in requested_scopes if scope))
    granted = tuple(dict.fromkeys(scope for scope in granted_scopes if scope))
    granted_set = set(granted)
    requested_set = set(requested)
    return {
        "declared": list(declared),
        "requested": list(requested),
        "granted": list(granted),
        "missing": [scope for scope in requested if scope not in granted_set],
        "extra": [scope for scope in granted if scope not in requested_set],
    }


def _redacted_mapping(value: Mapping[str, Any]) -> JsonObject:
    result: JsonObject = {}
    for key, item in value.items():
        lowered = str(key).lower()
        if any(marker in lowered for marker in ("token", "secret", "verifier", "code")):
            result[str(key)] = "[redacted]"
        else:
            result[str(key)] = item
    return result
