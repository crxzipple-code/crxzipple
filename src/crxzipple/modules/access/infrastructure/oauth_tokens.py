from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import os
from typing import Any, Mapping

from crxzipple.shared.time import coerce_utc_datetime


JsonObject = dict[str, Any]


@dataclass(frozen=True, slots=True)
class OAuthTokenDocument:
    access_token: str
    refresh_token: str | None = None
    token_type: str = "Bearer"
    expires_at: datetime | None = None
    scopes: tuple[str, ...] = ()
    metadata: Mapping[str, Any] | None = None

    def to_payload(self) -> JsonObject:
        payload: JsonObject = {
            "access_token": self.access_token,
            "token_type": self.token_type,
            "scopes": list(self.scopes),
            "metadata": dict(self.metadata or {}),
        }
        if self.refresh_token:
            payload["refresh_token"] = self.refresh_token
        if self.expires_at is not None:
            payload["expires_at"] = self.expires_at.isoformat()
        return payload

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "OAuthTokenDocument":
        access_token = str(payload.get("access_token") or "").strip()
        if not access_token:
            raise ValueError("OAuth token document is missing access_token.")
        refresh_token = _optional_text(payload.get("refresh_token"))
        token_type = _optional_text(payload.get("token_type")) or "Bearer"
        expires_at = _coerce_optional_datetime(payload.get("expires_at"))
        scopes = _string_tuple(payload.get("scopes"))
        metadata = payload.get("metadata")
        return cls(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type=token_type,
            expires_at=expires_at,
            scopes=scopes,
            metadata=dict(metadata) if isinstance(metadata, Mapping) else {},
        )


class FileBackedAccessOAuthTokenStore:
    def __init__(self, root_dir: str | Path) -> None:
        self._root_dir = Path(root_dir).expanduser()
        self._tokens_dir = self._root_dir / "oauth_tokens"
        self._tokens_dir.mkdir(parents=True, exist_ok=True)

    def storage_key_for_account(self, account_id: str) -> str:
        safe_account_id = _safe_storage_part(account_id)
        return f"oauth_tokens/{safe_account_id}.json"

    def write_token(
        self,
        storage_key: str,
        document: OAuthTokenDocument | Mapping[str, Any],
    ) -> None:
        payload = (
            document.to_payload()
            if isinstance(document, OAuthTokenDocument)
            else dict(document)
        )
        path = self._path_for_key(storage_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        try:
            os.chmod(temporary, 0o600)
        except OSError:
            pass
        temporary.replace(path)

    def read_token(self, storage_key: str) -> OAuthTokenDocument:
        path = self._path_for_key(storage_key)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise LookupError(f"OAuth token storage key '{storage_key}' is missing.") from exc
        if not isinstance(payload, Mapping):
            raise ValueError(f"OAuth token storage key '{storage_key}' is invalid.")
        return OAuthTokenDocument.from_payload(payload)

    def delete_token(self, storage_key: str) -> None:
        try:
            self._path_for_key(storage_key).unlink()
        except FileNotFoundError:
            return

    def _path_for_key(self, storage_key: str) -> Path:
        normalized = storage_key.strip()
        if not normalized:
            raise ValueError("OAuth token storage key is required.")
        path = Path(normalized)
        if path.is_absolute():
            return path
        safe_parts = [_safe_storage_part(part) for part in path.parts if part not in {"", "."}]
        if not safe_parts:
            raise ValueError("OAuth token storage key is invalid.")
        return self._root_dir.joinpath(*safe_parts)


def _safe_storage_part(value: str) -> str:
    normalized = "".join(
        char if char.isalnum() or char in {"_", "-", "."} else "_"
        for char in value.strip()
    ).strip("._")
    return normalized or "default"


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _string_tuple(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        return tuple(item for item in value.split() if item)
    if isinstance(value, (list, tuple)):
        return tuple(str(item).strip() for item in value if str(item).strip())
    return ()


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
