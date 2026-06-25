from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import time
from typing import Any, Mapping

import requests

from crxzipple.modules.access.application.repositories import AccessOAuthProviderRecord
from crxzipple.modules.access.infrastructure.oauth_tokens import OAuthTokenDocument
from crxzipple.shared.time import coerce_utc_datetime

JsonObject = dict[str, Any]

_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


class AccessOAuthTokenEndpointError(RuntimeError):
    """Raised when an OAuth provider token endpoint cannot be reached safely."""


@dataclass(slots=True)
class AccessOAuthTokenClient:
    timeout_seconds: int = 30
    max_attempts: int = 2
    retry_backoff_seconds: float = 0.1

    def exchange_authorization_code(
        self,
        provider: AccessOAuthProviderRecord,
        *,
        code: str,
        code_verifier: str,
        callback_url: str,
    ) -> JsonObject:
        assert provider.token_url is not None
        decoded = self._post_json(
            provider.token_url,
            {
                "grant_type": "authorization_code",
                "code": _required_text(code, "authorization code"),
                "redirect_uri": callback_url,
                "client_id": provider.client_id,
                "code_verifier": code_verifier,
            },
            operation="authorization-code token",
        )
        if not isinstance(decoded, Mapping):
            raise ValueError("OAuth token endpoint returned a non-object payload.")
        return dict(decoded)

    def request_device_code(
        self,
        provider: AccessOAuthProviderRecord,
        *,
        requested_scopes: tuple[str, ...],
    ) -> JsonObject:
        assert provider.device_code_url is not None
        decoded = self._post_json(
            provider.device_code_url,
            {
                "client_id": provider.client_id,
                "scope": " ".join(requested_scopes),
            },
            operation="device-code request",
        )
        if not isinstance(decoded, Mapping):
            raise ValueError("OAuth device-code endpoint returned a non-object payload.")
        return dict(decoded)

    def exchange_device_code(
        self,
        provider: AccessOAuthProviderRecord,
        *,
        device_code: str,
    ) -> JsonObject:
        if not provider.token_url:
            raise ValueError(
                f"OAuth provider '{provider.provider_id}' does not declare a token URL.",
            )
        decoded = self._post_json(
            provider.token_url,
            {
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                "device_code": _required_text(device_code, "OAuth device code"),
                "client_id": provider.client_id,
            },
            operation="device-code token",
        )
        if not isinstance(decoded, Mapping):
            raise ValueError("OAuth device-code token endpoint returned a non-object payload.")
        error = _optional_text(decoded.get("error"))
        if error:
            if error in {"authorization_pending", "slow_down"}:
                raise ValueError(f"OAuth device-code authorization is still pending: {error}.")
            raise ValueError(f"OAuth device-code authorization failed: {error}.")
        return dict(decoded)

    def refresh_token(
        self,
        provider: AccessOAuthProviderRecord,
        token: OAuthTokenDocument,
        *,
        now: datetime,
    ) -> OAuthTokenDocument:
        if not provider.token_url:
            return token
        decoded = self._post_json(
            provider.token_url,
            {
                "grant_type": "refresh_token",
                "refresh_token": token.refresh_token,
                "client_id": provider.client_id,
            },
            operation="refresh token",
        )
        if not isinstance(decoded, Mapping):
            raise ValueError("OAuth refresh endpoint returned a non-object payload.")
        merged = {
            **token.to_payload(),
            **dict(decoded),
        }
        if "scope" in decoded:
            merged["scopes"] = _string_tuple(decoded.get("scope"))
        if "expires_in" in decoded:
            merged["expires_at"] = _expires_at_from_payload(decoded, now=now)
        return OAuthTokenDocument.from_payload(merged)

    def revoke_token(
        self,
        provider: AccessOAuthProviderRecord,
        token: OAuthTokenDocument,
    ) -> None:
        if not provider.revocation_url:
            return
        self._post_json(
            provider.revocation_url,
            {
                "token": token.access_token,
                "client_id": provider.client_id,
            },
            operation="token revocation",
        )

    def _post_json(
        self,
        url: str,
        payload: Mapping[str, Any],
        *,
        operation: str,
    ) -> object:
        attempts = max(int(self.max_attempts), 1)
        for attempt_index in range(attempts):
            try:
                response = requests.post(url, data=payload, timeout=self.timeout_seconds)
                response.raise_for_status()
                return response.json()
            except requests.HTTPError as exc:
                if _is_retryable_http_error(exc) and attempt_index + 1 < attempts:
                    self._sleep_before_retry(attempt_index)
                    continue
                raise AccessOAuthTokenEndpointError(
                    _oauth_http_error_message(operation, exc),
                ) from exc
            except requests.RequestException as exc:
                if attempt_index + 1 < attempts:
                    self._sleep_before_retry(attempt_index)
                    continue
                raise AccessOAuthTokenEndpointError(
                    f"OAuth {operation} endpoint request failed after {attempts} "
                    f"attempt(s): {exc.__class__.__name__}.",
                ) from exc
            except ValueError as exc:
                raise ValueError(f"OAuth {operation} endpoint returned invalid JSON.") from exc
        raise AccessOAuthTokenEndpointError(
            f"OAuth {operation} endpoint request failed after {attempts} attempt(s).",
        )

    def _sleep_before_retry(self, attempt_index: int) -> None:
        if self.retry_backoff_seconds <= 0:
            return
        time.sleep(self.retry_backoff_seconds * (attempt_index + 1))


def _is_retryable_http_error(exc: requests.HTTPError) -> bool:
    response = getattr(exc, "response", None)
    status_code = getattr(response, "status_code", None)
    try:
        normalized = int(status_code)
    except (TypeError, ValueError):
        return False
    return normalized in _RETRYABLE_STATUS_CODES


def _oauth_http_error_message(operation: str, exc: requests.HTTPError) -> str:
    response = getattr(exc, "response", None)
    status_code = getattr(response, "status_code", None)
    try:
        normalized = int(status_code)
    except (TypeError, ValueError):
        normalized = 0
    if normalized > 0:
        return f"OAuth {operation} endpoint request failed with HTTP {normalized}."
    return f"OAuth {operation} endpoint request failed: HTTPError."


def _expires_at_from_payload(
    payload: Mapping[str, Any],
    *,
    now: datetime,
) -> datetime | None:
    expires_at = _coerce_optional_datetime(payload.get("expires_at"))
    if expires_at is not None:
        return expires_at
    expires_in = payload.get("expires_in")
    try:
        seconds = int(expires_in) if expires_in is not None else None
    except (TypeError, ValueError):
        seconds = None
    if seconds is None or seconds <= 0:
        return None
    return now + timedelta(seconds=seconds)


def _coerce_optional_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    try:
        return coerce_utc_datetime(value)
    except (TypeError, ValueError):
        return None


def _required_text(value: str | None, label: str) -> str:
    normalized = _optional_text(value)
    if normalized is None:
        raise ValueError(f"{label} is required.")
    return normalized


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _string_tuple(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return tuple(part for part in value.split() if part)
    if isinstance(value, (list, tuple, set)):
        return tuple(str(item).strip() for item in value if str(item).strip())
    return (str(value).strip(),) if str(value).strip() else ()
