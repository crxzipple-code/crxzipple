from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
import secrets
from typing import Any, Mapping
from uuid import uuid4

from crxzipple.modules.access.application.repositories import (
    AccessOAuthAccountRecord,
    AccessOAuthProviderRecord,
    AccessSetupSessionRecord,
)
from crxzipple.modules.access.application.settings_integration import (
    AccessSettingsActionAdapter,
)
from .oauth_account_records import (
    oauth_account_status_record,
    oauth_provider_record,
    refreshed_oauth_account_record,
)
from .oauth_account_lifecycle import (
    revoke_and_update_oauth_account_status,
    store_oauth_account_from_token_payload,
)
from .oauth_contracts import (
    AccessOAuthAccountResult,
    AccessOAuthRepository,
    AccessOAuthSetupResult,
    AccessOAuthTokenStore,
)
from .oauth_callback_listener import (
    CODEX_OAUTH_CALLBACK_TIMEOUT_SECONDS,
    open_browser_url,
    start_codex_oauth_callback_listener,
)
from .oauth_codex import (
    CODEX_OAUTH_AUTHORIZE_EXTRAS,
    CODEX_OAUTH_AUTHORIZE_URL,
    CODEX_OAUTH_CALLBACK_URL,
    CODEX_OAUTH_CLIENT_ID,
    CODEX_OAUTH_SCOPES,
    CODEX_OAUTH_TOKEN_URL,
    DEFAULT_CODEX_OAUTH_ACCOUNT_ID,
    DEFAULT_CODEX_OAUTH_BINDING_ID,
    DEFAULT_CODEX_OAUTH_PROVIDER_ID,
    codex_token_payload_with_identity,
)
from .oauth_setup_flows import (
    browser_authorize_url,
    browser_setup_result,
    browser_setup_session_record,
    device_verification_url,
    positive_int,
    ready_device_setup_result,
    ready_device_setup_session_record,
    unsupported_device_setup_result,
    unsupported_device_setup_session_record,
)
from .oauth_token_client import AccessOAuthTokenClient
from .oauth_token_payloads import (
    expires_at_from_payload,
    optional_text,
    pkce_challenge,
    required_text,
    string_tuple,
    token_should_refresh,
)
from crxzipple.shared.time import coerce_utc_datetime


@dataclass(slots=True)
class AccessOAuthService:
    repository: AccessOAuthRepository
    token_store: AccessOAuthTokenStore
    settings_action_adapter: AccessSettingsActionAdapter | None = None
    token_client: AccessOAuthTokenClient = field(
        default_factory=AccessOAuthTokenClient,
        repr=False,
    )
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
        return self.repository.upsert_oauth_provider(
            oauth_provider_record(
                provider_id=provider_id,
                display_name=display_name,
                provider_kind=provider_kind,
                authorization_url=authorization_url,
                token_url=token_url,
                revocation_url=revocation_url,
                device_code_url=device_code_url,
                default_scopes=default_scopes,
                client_id=client_id,
                client_credential_binding_id=client_credential_binding_id,
                callback_url=callback_url,
                callback_mode=callback_mode,
                status=status,
                metadata=metadata,
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
        code_challenge = pkce_challenge(code_verifier)
        now = self._now()
        expires_at = now + timedelta(minutes=30)
        authorize_url = browser_authorize_url(
            provider,
            callback_url=callback_url,
            scopes=scopes,
            state=state,
            code_challenge=code_challenge,
        )
        record = self.repository.create_setup_session(
            browser_setup_session_record(
                session_id=f"oauthsetup_{uuid4().hex}",
                provider=provider,
                callback_url=callback_url,
                scopes=scopes,
                state=state,
                code_verifier=code_verifier,
                account_id=account_id,
                credential_binding_id=credential_binding_id,
                actor=actor,
                reason=reason,
                expires_at=expires_at,
                created_at=now,
            ),
        )
        return browser_setup_result(
            record=record,
            provider=provider,
            authorize_url=authorize_url,
            callback_url=callback_url,
            scopes=scopes,
            expires_at=expires_at,
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
        now = self._now()
        expires_at = now + timedelta(minutes=30)
        if not provider.device_code_url:
            record = self.repository.create_setup_session(
                unsupported_device_setup_session_record(
                    session_id=f"oauthsetup_{uuid4().hex}",
                    provider=provider,
                    scopes=scopes,
                    account_id=account_id,
                    credential_binding_id=credential_binding_id,
                    actor=actor,
                    reason=reason,
                    expires_at=expires_at,
                    created_at=now,
                ),
            )
            return unsupported_device_setup_result(
                record=record,
                provider=provider,
                scopes=scopes,
                expires_at=expires_at,
            )
        if not provider.client_id:
            raise ValueError(
                f"OAuth provider '{provider.provider_id}' does not declare a client id.",
            )
        if not provider.token_url:
            raise ValueError(
                f"OAuth provider '{provider.provider_id}' does not declare a token URL.",
            )
        device_payload = self.token_client.request_device_code(
            provider,
            requested_scopes=scopes,
        )
        device_code = required_text(
            str(device_payload.get("device_code") or ""),
            "OAuth device code",
        )
        user_code = required_text(
            str(device_payload.get("user_code") or ""),
            "OAuth user code",
        )
        verification_url = device_verification_url(device_payload)
        interval_seconds = positive_int(device_payload.get("interval"))
        device_expires_at = expires_at_from_payload(device_payload, now=self._now())
        if device_expires_at is not None:
            expires_at = device_expires_at
        record = self.repository.create_setup_session(
            ready_device_setup_session_record(
                session_id=f"oauthsetup_{uuid4().hex}",
                provider=provider,
                scopes=scopes,
                account_id=account_id,
                credential_binding_id=credential_binding_id,
                actor=actor,
                reason=reason,
                device_code=device_code,
                verification_url=verification_url,
                interval_seconds=interval_seconds,
                expires_at=expires_at,
                created_at=now,
            ),
        )
        return ready_device_setup_result(
            record=record,
            provider=provider,
            scopes=scopes,
            verification_url=verification_url,
            user_code=user_code,
            interval_seconds=interval_seconds,
            expires_at=expires_at,
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
                code=required_text(code, "authorization code"),
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
        expected_state = optional_text(session_metadata.get("state"))
        if expected_state and (state is None or expected_state != state.strip()):
            raise ValueError("OAuth setup state does not match.")
        if session.expires_at is not None and session.expires_at < self._now():
            raise ValueError("OAuth setup session has expired.")
        if not provider.token_url:
            raise ValueError(
                f"OAuth provider '{provider.provider_id}' does not declare a token URL.",
            )
        token_payload = self.token_client.exchange_authorization_code(
            provider,
            code=code,
            code_verifier=required_text(
                str(session_metadata.get("code_verifier") or ""),
                "code verifier",
            ),
            callback_url=required_text(
                str(session_metadata.get("callback_url") or ""),
                "callback URL",
            ),
        )
        if provider.provider_id == DEFAULT_CODEX_OAUTH_PROVIDER_ID:
            token_payload = codex_token_payload_with_identity(token_payload)
        result = self._store_account_from_token_payload(
            provider,
            token_payload,
            account_id=account_id or optional_text(session_metadata.get("account_id")),
            credential_binding_id=(
                credential_binding_id
                or optional_text(session_metadata.get("credential_binding_id"))
            ),
            metadata={
                "setup_session_id": session.session_id,
                "setup_flow": "browser_oauth",
                "declared_scopes": list(provider.default_scopes),
                "requested_scopes": list(
                    string_tuple(session_metadata.get("requested_scopes")),
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
        token_payload = self.token_client.exchange_device_code(
            provider,
            device_code=required_text(
                str(session_metadata.get("device_code") or ""),
                "OAuth device code",
            ),
        )
        result = self._store_account_from_token_payload(
            provider,
            token_payload,
            account_id=account_id or optional_text(session_metadata.get("account_id")),
            credential_binding_id=(
                credential_binding_id
                or optional_text(session_metadata.get("credential_binding_id"))
            ),
            metadata={
                "setup_session_id": session.session_id,
                "setup_flow": "device_code",
                "declared_scopes": list(provider.default_scopes),
                "requested_scopes": list(
                    string_tuple(session_metadata.get("requested_scopes")),
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
        listener = start_codex_oauth_callback_listener(
            service=self,
            session_id=setup.session_id,
            account_id=account_id,
            credential_binding_id=credential_binding_id,
            timeout_seconds=CODEX_OAUTH_CALLBACK_TIMEOUT_SECONDS,
        )
        browser_opened = open_browser_url(setup.authorize_url) if open_browser else False
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
        storage_key = required_text(account.storage_key or "", "OAuth token storage key")
        token = self.token_store.read_token(storage_key)
        if token_should_refresh(token, now=self._now()) and token.refresh_token:
            self._refresh_account(account.account_id, only_if_needed=True)
            token = self.token_store.read_token(storage_key)
        if token.expires_at is not None and token.expires_at <= self._now():
            raise ValueError(f"OAuth account '{account.account_id}' is expired.")
        return token.access_token

    def refresh_account(self, account_id: str) -> AccessOAuthAccountResult:
        return self._refresh_account(account_id, only_if_needed=False)

    def _refresh_account(
        self,
        account_id: str,
        *,
        only_if_needed: bool,
    ) -> AccessOAuthAccountResult:
        account = self._active_account(account_id)
        storage_key = required_text(account.storage_key or "", "OAuth token storage key")
        with self.token_store.token_lock(storage_key):
            account = self._active_account(account_id)
            token = self.token_store.read_token(storage_key)
            provider = self._active_provider(account.provider_id)
            if only_if_needed and not token_should_refresh(token, now=self._now()):
                return AccessOAuthAccountResult(
                    account=account,
                    credential_binding_id=required_text(
                        account.credential_binding_id or "",
                        "OAuth credential binding id",
                    ),
                    provider=provider,
                )
            if not token.refresh_token:
                raise ValueError(
                    f"OAuth account '{account.account_id}' does not have a refresh token.",
                )
            if not provider.token_url:
                raise ValueError(
                    f"OAuth provider '{provider.provider_id}' does not declare a token URL.",
                )
            refreshed = self.token_client.refresh_token(provider, token, now=self._now())
            self.token_store.write_token(storage_key, refreshed)
            updated = self.repository.upsert_oauth_account(
                refreshed_oauth_account_record(
                    account,
                    refreshed,
                    refreshed_at=self._now(),
                ),
            )
        return AccessOAuthAccountResult(
            account=updated,
            credential_binding_id=required_text(
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
            return self._revoke_and_update_account_status(account)
        updated = oauth_account_status_record(account, status=status)
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
        return store_oauth_account_from_token_payload(
            repository=self.repository,
            token_store=self.token_store,
            settings_action_adapter=self.settings_action_adapter,
            provider=provider,
            token_payload=token_payload,
            account_id=account_id,
            credential_binding_id=credential_binding_id,
            metadata=metadata,
            now=self._now(),
        )

    def _revoke_and_update_account_status(
        self,
        account: AccessOAuthAccountRecord,
    ) -> AccessOAuthAccountRecord:
        return revoke_and_update_oauth_account_status(
            repository=self.repository,
            token_store=self.token_store,
            token_client=self.token_client,
            account=account,
        )

    def _active_provider(self, provider_id: str) -> AccessOAuthProviderRecord:
        provider = self.repository.get_oauth_provider(required_text(provider_id, "provider id"))
        if provider is None:
            raise LookupError(f"OAuth provider '{provider_id}' was not found.")
        if provider.status != "active":
            raise ValueError(f"OAuth provider '{provider.provider_id}' is {provider.status}.")
        return provider

    def _setup_session_record(self, session_id: str) -> AccessSetupSessionRecord:
        session = self.repository.get_setup_session(
            required_text(session_id, "setup session id"),
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
        account = self.repository.get_oauth_account(required_text(account_id, "OAuth account id"))
        if account is None:
            raise LookupError(f"OAuth account '{account_id}' was not found.")
        return account

    def _now(self) -> datetime:
        return coerce_utc_datetime(self.now_factory())
