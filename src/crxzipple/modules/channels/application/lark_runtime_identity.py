from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from threading import Lock
from typing import Any, Protocol

import requests

from crxzipple.modules.channels.application.bindings import (
    ChannelCredentialResolutionError,
)
from crxzipple.modules.channels.application.runtime_helpers import utcnow
from crxzipple.shared.http import request_url


@dataclass(frozen=True, slots=True)
class LarkTenantAccessToken:
    token: str
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class LarkBotIdentity:
    open_id: str
    expires_at: datetime


class LarkAccountProfileResolver(Protocol):
    def __call__(self, channel_account_id: str) -> Any:
        ...


class LarkMetadataCredentialResolver(Protocol):
    def __call__(
        self,
        metadata: dict[str, Any],
        *,
        key: str,
        description: str,
        required: bool,
        channel_type: str,
        component: str,
        channel_account_id: str | None = None,
        runtime_ref: str | None = None,
    ) -> str | None:
        ...


class LarkIdentityRuntime:
    def __init__(
        self,
        *,
        account_profile_resolver: LarkAccountProfileResolver,
        metadata_credential_resolver: LarkMetadataCredentialResolver,
        bot_identity_ttl_seconds: int = 3600,
    ) -> None:
        self._account_profile_resolver = account_profile_resolver
        self._metadata_credential_resolver = metadata_credential_resolver
        self.bot_identity_ttl_seconds = bot_identity_ttl_seconds
        self._tenant_access_tokens: dict[str, LarkTenantAccessToken] = {}
        self._token_lock = Lock()
        self._bot_identities: dict[str, LarkBotIdentity] = {}
        self._bot_identity_lock = Lock()

    def resolve_bot_open_id_for_account(
        self,
        channel_account_id: str,
        *,
        force_refresh: bool = False,
    ) -> str | None:
        account_profile = self._account_profile_resolver(channel_account_id)
        metadata = dict(account_profile.metadata)
        configured_open_id = self._metadata_credential_resolver(
            metadata,
            key="lark_bot_open_id",
            description="Lark bot open id",
            required=False,
            channel_type="lark",
            component="bot_identity",
            channel_account_id=channel_account_id,
        )
        if configured_open_id:
            return configured_open_id
        now = utcnow()
        with self._bot_identity_lock:
            cached = None if force_refresh else self._bot_identities.get(channel_account_id)
            if cached is not None and cached.expires_at > now:
                return cached.open_id
        base_url = lark_base_url_from_metadata(metadata)
        try:
            token = self.tenant_access_token_for_account(
                channel_account_id,
                base_url=base_url,
            )
            response = request_url(
                "GET",
                f"{base_url}/open-apis/bot/v3/info",
                headers={
                    "Authorization": f"Bearer {token}",
                },
                timeout=10,
            )
            payload = response.json()
        except ChannelCredentialResolutionError:
            raise
        except (requests.RequestException, ValueError, RuntimeError):
            return None
        code = payload.get("code")
        if response.status_code != 200 or code not in {0, "0", None}:
            return None
        bot_open_id = extract_bot_open_id(payload)
        if not bot_open_id:
            return None
        with self._bot_identity_lock:
            self._bot_identities[channel_account_id] = LarkBotIdentity(
                open_id=bot_open_id,
                expires_at=utcnow() + timedelta(seconds=self.bot_identity_ttl_seconds),
            )
        return bot_open_id

    def tenant_access_token_for_account(
        self,
        channel_account_id: str,
        *,
        base_url: str,
    ) -> str:
        now = utcnow()
        with self._token_lock:
            cached = self._tenant_access_tokens.get(channel_account_id)
            if cached is not None and cached.expires_at > now + timedelta(seconds=60):
                return cached.token
        account_profile = self._account_profile_resolver(channel_account_id)
        metadata = dict(account_profile.metadata)
        app_id = self._metadata_credential_resolver(
            metadata,
            key="lark_app_id",
            description="Lark app id",
            required=True,
            channel_type="lark",
            component="tenant_access_token",
            channel_account_id=channel_account_id,
        )
        app_secret = self._metadata_credential_resolver(
            metadata,
            key="lark_app_secret",
            description="Lark app secret",
            required=True,
            channel_type="lark",
            component="tenant_access_token",
            channel_account_id=channel_account_id,
        )
        response = request_url(
            "POST",
            f"{base_url}/open-apis/auth/v3/tenant_access_token/internal",
            json={"app_id": app_id, "app_secret": app_secret},
            timeout=10,
        )
        payload = response.json()
        token = str(payload.get("tenant_access_token") or "").strip()
        if response.status_code != 200 or not token:
            code = payload.get("code")
            raise RuntimeError(f"lark_access_token_failed:{response.status_code}:{code}")
        raw_expire = payload.get("expire")
        try:
            expire_seconds = max(int(raw_expire), 1)
        except (TypeError, ValueError):
            expire_seconds = 7200
        cached_token = LarkTenantAccessToken(
            token=token,
            expires_at=utcnow() + timedelta(seconds=expire_seconds),
        )
        with self._token_lock:
            self._tenant_access_tokens[channel_account_id] = cached_token
        return token


def lark_base_url_from_metadata(metadata: dict[str, Any]) -> str:
    base_url = str(metadata.get("lark_base_url") or "https://open.feishu.cn").strip()
    if not base_url:
        base_url = "https://open.feishu.cn"
    return base_url.rstrip("/")


def extract_bot_open_id(payload: dict[str, Any]) -> str | None:
    candidates: list[dict[str, Any]] = [payload]
    bot_payload = payload.get("bot")
    if isinstance(bot_payload, dict):
        candidates.append(bot_payload)
    data_payload = payload.get("data")
    if isinstance(data_payload, dict):
        candidates.append(data_payload)
        nested_bot_payload = data_payload.get("bot")
        if isinstance(nested_bot_payload, dict):
            candidates.append(nested_bot_payload)
    for candidate in candidates:
        open_id = str(candidate.get("open_id") or "").strip()
        if open_id:
            return open_id
    return None
