from __future__ import annotations

import base64
import json
from typing import Any, Mapping

from .oauth_callback_listener import CODEX_OAUTH_CALLBACK_URL as CODEX_OAUTH_CALLBACK_URL
from .oauth_contracts import JsonObject


DEFAULT_CODEX_OAUTH_PROVIDER_ID = "openai-codex"
DEFAULT_CODEX_OAUTH_ACCOUNT_ID = "openai-codex:default"
DEFAULT_CODEX_OAUTH_BINDING_ID = "codex-oauth-default"
CODEX_OAUTH_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
CODEX_OAUTH_AUTHORIZE_URL = "https://auth.openai.com/oauth/authorize"
CODEX_OAUTH_TOKEN_URL = "https://auth.openai.com/oauth/token"
CODEX_OAUTH_SCOPES = ("openid", "profile", "email", "offline_access")
CODEX_OAUTH_AUTHORIZE_EXTRAS = {
    "id_token_add_organizations": "true",
    "codex_cli_simplified_flow": "true",
    "originator": "pi",
}
CODEX_JWT_AUTH_CLAIM = "https://api.openai.com/auth"
CODEX_JWT_PROFILE_CLAIM = "https://api.openai.com/profile"


def codex_token_payload_with_identity(payload: JsonObject) -> JsonObject:
    access_token = _required_text(str(payload.get("access_token") or ""), "access token")
    decoded = decode_jwt_payload(access_token)
    account_id = codex_account_id(decoded)
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


def decode_jwt_payload(token: str) -> JsonObject:
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


def codex_account_id(payload: Mapping[str, Any]) -> str | None:
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
