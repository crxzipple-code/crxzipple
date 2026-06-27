from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from .network_capture import DefaultBrowserNetworkRedactor
from .storage_cookie_payloads import redact_cookie_payload

_VALUE_PREVIEW_BYTES = 16_384


@dataclass(frozen=True, slots=True)
class BrowserStorageResultProjector:
    redactor: DefaultBrowserNetworkRedactor = field(
        default_factory=DefaultBrowserNetworkRedactor,
    )

    def redact_cookie(self, cookie: Mapping[str, Any]) -> dict[str, Any]:
        return redact_cookie_payload(cookie, self.redact_value)

    def indexeddb_database(self, raw: Mapping[str, Any]) -> dict[str, Any]:
        database = raw.get("databaseWithObjectStores")
        if not isinstance(database, Mapping):
            database = raw
        stores: list[dict[str, Any]] = []
        raw_stores = database.get("objectStores")
        if isinstance(raw_stores, list):
            for raw_store in raw_stores:
                if not isinstance(raw_store, Mapping):
                    continue
                indexes: list[dict[str, Any]] = []
                raw_indexes = raw_store.get("indexes")
                if isinstance(raw_indexes, list):
                    for raw_index in raw_indexes:
                        if isinstance(raw_index, Mapping):
                            indexes.append(
                                {
                                    "name": raw_index.get("name"),
                                    "key_path": self.redact_value(raw_index.get("keyPath")),
                                    "unique": bool(raw_index.get("unique")),
                                    "multi_entry": bool(raw_index.get("multiEntry")),
                                }
                            )
                stores.append(
                    {
                        "name": raw_store.get("name"),
                        "key_path": self.redact_value(raw_store.get("keyPath")),
                        "auto_increment": bool(raw_store.get("autoIncrement")),
                        "indexes": indexes,
                        "index_count": len(indexes),
                    }
                )
        return {
            "name": database.get("name"),
            "version": database.get("version"),
            "object_stores": stores,
            "object_store_count": len(stores),
        }

    def indexeddb_entry(self, raw_entry: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "key": self.redact_value(raw_entry.get("key"), key_hint="key"),
            "primary_key": self.redact_value(
                raw_entry.get("primaryKey"),
                key_hint="primary_key",
            ),
            "value": self.redact_value(raw_entry.get("value"), key_hint="value"),
        }

    def cache_entry(self, raw_entry: Mapping[str, Any]) -> dict[str, Any]:
        request_headers = raw_entry.get("requestHeaders")
        response_headers = raw_entry.get("responseHeaders")
        return {
            "request_url": self.redactor.redact_url(str(raw_entry.get("requestURL") or "")),
            "request_method": raw_entry.get("requestMethod"),
            "request_headers": self.redact_header_list(request_headers),
            "response_status": raw_entry.get("responseStatus"),
            "response_status_text": raw_entry.get("responseStatusText"),
            "response_time": raw_entry.get("responseTime"),
            "response_headers": self.redact_header_list(response_headers),
        }

    def cache_response(self, raw_response: Mapping[str, Any]) -> dict[str, Any]:
        body = raw_response.get("body")
        body_text = "" if body is None else str(body)
        limited = body_text[:_VALUE_PREVIEW_BYTES]
        return {
            "body": self.redactor.redact_body(
                body=limited,
                kind="response",
                mime_type=None,
                headers=None,
            ),
            "body_size_bytes": len(body_text.encode("utf-8")),
            "truncated": len(body_text.encode("utf-8")) > _VALUE_PREVIEW_BYTES,
        }

    def redact_header_list(self, value: Any) -> dict[str, str]:
        if not isinstance(value, list):
            return {}
        return self.redactor.redact_headers(
            {
                str(item.get("name")): str(item.get("value") or "")
                for item in value
                if isinstance(item, Mapping) and item.get("name") is not None
            }
        )

    def redact_value(self, value: Any, *, key_hint: str | None = None) -> Any:
        if isinstance(key_hint, str) and storage_name_is_sensitive(key_hint):
            return "[redacted]"
        if value is None or isinstance(value, (int, float, bool)):
            return value
        if isinstance(value, str):
            limited = value
            if len(limited.encode("utf-8")) > _VALUE_PREVIEW_BYTES:
                limited = limited.encode("utf-8")[:_VALUE_PREVIEW_BYTES].decode(
                    "utf-8",
                    errors="replace",
                )
            return self.redactor.redact_body(
                body=limited,
                kind="response",
                mime_type=None,
                headers=None,
            )
        if isinstance(value, Mapping):
            return {
                str(key): self.redact_value(item, key_hint=str(key))
                for key, item in value.items()
            }
        if isinstance(value, (list, tuple)):
            return [self.redact_value(item, key_hint=key_hint) for item in value]
        return str(value)


def storage_name_is_sensitive(name: str) -> bool:
    normalized = name.strip().lower().replace("-", "_")
    return any(
        marker in normalized
        for marker in (
            "api_key",
            "apikey",
            "auth",
            "authorization",
            "credential",
            "jwt",
            "password",
            "passwd",
            "secret",
            "session",
            "token",
        )
    )


__all__ = ["BrowserStorageResultProjector", "storage_name_is_sensitive"]
