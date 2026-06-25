from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping, Protocol

from crxzipple.modules.access.application.repositories import (
    AccessOAuthAccountRecord,
    AccessOAuthProviderRecord,
    AccessSetupSessionRecord,
)
from crxzipple.modules.access.infrastructure.oauth_tokens import OAuthTokenDocument

from .oauth_redaction import JsonObject, redacted_mapping


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

    def token_lock(self, storage_key: str) -> AbstractContextManager[None]: ...

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
            "metadata": redacted_mapping(self.metadata),
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
