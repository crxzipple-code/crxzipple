from __future__ import annotations

from datetime import datetime, timedelta, timezone
import base64
import hashlib
import json
from typing import Any, Mapping
from uuid import uuid4

from crxzipple.modules.access.infrastructure.oauth_tokens import OAuthTokenDocument
from crxzipple.shared.time import coerce_utc_datetime

from .oauth_contracts import JsonObject


def expires_at_from_payload(
    payload: Mapping[str, Any],
    *,
    now: datetime,
) -> datetime | None:
    expires_at = coerce_optional_datetime(payload.get("expires_at"))
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


def coerce_optional_datetime(value: object) -> datetime | None:
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


def scopes_from_token_payload(
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


def subject_from_token_payload(payload: Mapping[str, Any]) -> str | None:
    for key in ("email", "account", "account_id", "sub"):
        value = optional_text(payload.get(key))
        if value is not None:
            return value
    id_token = optional_text(payload.get("id_token"))
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
    return optional_text(decoded_payload.get("email")) or optional_text(
        decoded_payload.get("sub"),
    )


def token_should_refresh(token: OAuthTokenDocument, *, now: datetime) -> bool:
    if token.expires_at is None:
        return False
    return token.expires_at <= now + timedelta(minutes=5)


def masked_token(value: str) -> str:
    if len(value) <= 10:
        return "***"
    return f"{value[:4]}...{value[-4:]}"


def default_account_id(provider_id: str, subject: str | None) -> str:
    suffix = subject or uuid4().hex
    return f"{provider_id}:{safe_id_part(suffix)}"


def safe_id_part(value: str) -> str:
    normalized = "".join(
        char if char.isalnum() or char in {"_", "-", "."} else "_"
        for char in value.strip()
    ).strip("._")
    return normalized or "default"


def pkce_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def required_text(value: str | None, label: str) -> str:
    normalized = (value or "").strip()
    if not normalized:
        raise ValueError(f"{label} is required.")
    return normalized


def optional_text(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def string_tuple(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        return tuple(item for item in value.replace(",", " ").split() if item)
    if isinstance(value, (list, tuple)):
        return tuple(str(item).strip() for item in value if str(item).strip())
    return ()


def scope_diff_payload(
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
