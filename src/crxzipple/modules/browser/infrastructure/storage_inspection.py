from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping
from urllib.parse import urlsplit, urlunsplit

from crxzipple.modules.browser.domain import BrowserValidationError

from .cdp_sessions import BrowserCdpSessionBroker
from .network_capture import DefaultBrowserNetworkRedactor

_VALUE_PREVIEW_BYTES = 16_384
_SERVICE_WORKER_INSPECT_EXPRESSION = """
/*__crxzipple_service_worker_inspect__*/
(raw) => {
  const input = raw && typeof raw === "object" ? raw : {};
  const scopeFilter = typeof input.scope_url === "string" && input.scope_url.trim()
    ? input.scope_url.trim()
    : null;
  const scriptFilter = typeof input.script_url === "string" && input.script_url.trim()
    ? input.script_url.trim()
    : null;
  const serializeWorker = (worker) => worker ? {
    script_url: String(worker.scriptURL || ""),
    state: String(worker.state || ""),
  } : null;
  const serializeRegistration = (registration) => ({
    scope_url: String(registration.scope || ""),
    update_via_cache: String(registration.updateViaCache || ""),
    active: serializeWorker(registration.active),
    installing: serializeWorker(registration.installing),
    waiting: serializeWorker(registration.waiting),
  });
  if (!navigator.serviceWorker || !navigator.serviceWorker.getRegistrations) {
    return {
      supported: false,
      registrations: [],
      count: 0,
    };
  }
  return navigator.serviceWorker.getRegistrations().then((registrations) => {
    let items = registrations.map(serializeRegistration);
    if (scopeFilter) {
      items = items.filter((item) => item.scope_url === scopeFilter || item.scope_url.includes(scopeFilter));
    }
    if (scriptFilter) {
      items = items.filter((item) => {
        const workers = [item.active, item.installing, item.waiting].filter(Boolean);
        return workers.some((worker) => worker.script_url === scriptFilter || worker.script_url.includes(scriptFilter));
      });
    }
    return {
      supported: true,
      registrations: items,
      count: items.length,
    };
  });
}
""".strip()


@dataclass(frozen=True, slots=True)
class BrowserStorageInspectionService:
    redactor: DefaultBrowserNetworkRedactor = field(
        default_factory=DefaultBrowserNetworkRedactor,
    )

    def execute(
        self,
        *,
        page: Any,
        kind: str,
        payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        if kind.startswith("storage-indexeddb-"):
            session = _new_page_cdp_session(page)
            try:
                return self._indexeddb(page=page, session=session, kind=kind, payload=payload)
            finally:
                _detach_cdp_session(session)
        if kind.startswith("storage-cache-"):
            session = _new_page_cdp_session(page)
            try:
                return self._cache(page=page, session=session, kind=kind, payload=payload)
            finally:
                _detach_cdp_session(session)
        return self._service_worker(page=page, kind=kind, payload=payload)

    def redact_cookie(self, cookie: Mapping[str, Any]) -> dict[str, Any]:
        redacted = {
            str(key): self._redact_value(value, key_hint=str(key))
            for key, value in cookie.items()
        }
        if "value" in redacted:
            redacted["value"] = "[redacted]"
        return redacted

    def _indexeddb(
        self,
        *,
        page: Any,
        session: Any,
        kind: str,
        payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        origin = _page_security_origin(page, payload)
        if kind == "storage-indexeddb-list":
            names_payload = _send_cdp_session_command(
                session,
                "IndexedDB.requestDatabaseNames",
                {"securityOrigin": origin},
            )
            raw_names = (
                names_payload.get("databaseNames")
                if isinstance(names_payload, Mapping)
                else None
            )
            database_names = (
                [
                    str(name)
                    for name in raw_names
                    if isinstance(name, str) and name.strip()
                ]
                if isinstance(raw_names, list)
                else []
            )
            include_metadata = _payload_bool_any(
                payload,
                "include_metadata",
                "includeMetadata",
            )
            if include_metadata is None:
                include_metadata = True
            databases: list[dict[str, Any]] = []
            if include_metadata:
                for database_name in database_names:
                    try:
                        raw_database = _send_cdp_session_command(
                            session,
                            "IndexedDB.requestDatabase",
                            {
                                "securityOrigin": origin,
                                "databaseName": database_name,
                            },
                        )
                    except Exception as exc:  # pragma: no cover - CDP support varies by target
                        databases.append({"name": database_name, "error": str(exc)})
                        continue
                    databases.append(self._indexeddb_database(raw_database))
            return {
                "kind": kind,
                "origin": origin,
                "database_names": database_names,
                "databases": databases,
                "count": len(database_names),
            }

        database_name = _payload_text_any(payload, "database_name", "databaseName")
        object_store_name = _payload_text_any(
            payload,
            "object_store_name",
            "objectStoreName",
            "store",
        )
        if database_name is None or object_store_name is None:
            raise BrowserValidationError(
                "payload.database_name and payload.object_store_name are required.",
            )
        index_name = _payload_text_any(payload, "index_name", "indexName")
        limit = _payload_limit(payload, default=50)
        skip = _payload_skip(payload)
        raw_data = _send_cdp_session_command(
            session,
            "IndexedDB.requestData",
            {
                "securityOrigin": origin,
                "databaseName": database_name,
                "objectStoreName": object_store_name,
                "indexName": index_name or "",
                "skipCount": skip,
                "pageSize": limit,
            },
        )
        raw_entries = (
            raw_data.get("objectStoreDataEntries")
            if isinstance(raw_data, Mapping)
            else None
        )
        entries = (
            [
                self._indexeddb_entry(raw_entry)
                for raw_entry in raw_entries
                if isinstance(raw_entry, Mapping)
            ]
            if isinstance(raw_entries, list)
            else []
        )
        if kind == "storage-indexeddb-get":
            key = _payload_value_any(payload, "key", "primary_key", "primaryKey")
            if key is None:
                raise BrowserValidationError("payload.key is required for indexeddb get.")
            key_text = str(key)
            entries = [
                entry
                for entry in entries
                if str(entry.get("key")) == key_text
                or str(entry.get("primary_key")) == key_text
            ][:1]
        return {
            "kind": kind,
            "origin": origin,
            "database_name": database_name,
            "object_store_name": object_store_name,
            "index_name": index_name,
            "skip": skip,
            "limit": limit,
            "entries": entries,
            "count": len(entries),
            "has_more": bool(raw_data.get("hasMore"))
            if isinstance(raw_data, Mapping)
            else False,
        }

    def _cache(
        self,
        *,
        page: Any,
        session: Any,
        kind: str,
        payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        origin = _page_security_origin(page, payload)
        raw_caches = _send_cdp_session_command(
            session,
            "CacheStorage.requestCacheNames",
            {"securityOrigin": origin},
        )
        caches = raw_caches.get("caches") if isinstance(raw_caches, Mapping) else None
        cache_items = (
            [
                {
                    "cache_id": str(item.get("cacheId") or ""),
                    "cache_name": str(item.get("cacheName") or ""),
                    "security_origin": item.get("securityOrigin"),
                    "storage_key": item.get("storageKey"),
                }
                for item in caches
                if isinstance(item, Mapping)
            ]
            if isinstance(caches, list)
            else []
        )
        if kind == "storage-cache-list":
            return {
                "kind": kind,
                "origin": origin,
                "caches": cache_items,
                "count": len(cache_items),
            }

        cache_id = _payload_text_any(payload, "cache_id", "cacheId")
        cache_name = _payload_text_any(payload, "cache_name", "cacheName", "cache")
        if cache_id is None and cache_name is not None:
            cache_id = next(
                (
                    str(item["cache_id"])
                    for item in cache_items
                    if item["cache_name"] == cache_name
                ),
                None,
            )
        if cache_id is None:
            raise BrowserValidationError("payload.cache_id or payload.cache_name is required.")
        request_url = _payload_text_any(payload, "request_url", "requestURL", "url")
        limit = _payload_limit(payload, default=50)
        skip = _payload_skip(payload)
        entries_payload = _send_cdp_session_command(
            session,
            "CacheStorage.requestEntries",
            {
                "cacheId": cache_id,
                "skipCount": skip,
                "pageSize": limit,
                "pathFilter": request_url or "",
            },
        )
        raw_entries = (
            entries_payload.get("cacheDataEntries")
            if isinstance(entries_payload, Mapping)
            else None
        )
        entries = (
            [
                self._cache_entry(raw_entry)
                for raw_entry in raw_entries
                if isinstance(raw_entry, Mapping)
            ]
            if isinstance(raw_entries, list)
            else []
        )
        response: dict[str, Any] | None = None
        if request_url is not None:
            try:
                raw_response = _send_cdp_session_command(
                    session,
                    "CacheStorage.requestCachedResponse",
                    {
                        "cacheId": cache_id,
                        "requestURL": request_url,
                        "requestHeaders": [],
                    },
                )
                if isinstance(raw_response, Mapping):
                    raw_body = raw_response.get("response")
                    response = self._cache_response(
                        raw_body if isinstance(raw_body, Mapping) else raw_response,
                    )
            except Exception as exc:  # pragma: no cover - CDP support varies by target
                response = {"error": str(exc)}
        return {
            "kind": kind,
            "origin": origin,
            "cache_id": cache_id,
            "cache_name": cache_name,
            "request_url": self.redactor.redact_url(request_url) if request_url else None,
            "skip": skip,
            "limit": limit,
            "entries": entries,
            "count": len(entries),
            "return_count": entries_payload.get("returnCount")
            if isinstance(entries_payload, Mapping)
            else None,
            "response": response,
        }

    def _service_worker(
        self,
        *,
        page: Any,
        kind: str,
        payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        raw = page.evaluate(
            _SERVICE_WORKER_INSPECT_EXPRESSION,
            {
                "scope_url": _payload_text_any(payload, "scope_url", "scopeUrl", "scope"),
                "script_url": _payload_text_any(payload, "script_url", "scriptUrl", "script"),
            },
        )
        if not isinstance(raw, Mapping):
            raw = {}
        registrations = raw.get("registrations")
        if not isinstance(registrations, list):
            registrations = []
        if kind == "service-worker-inspect":
            registrations = registrations[:1]
        return {
            "kind": kind,
            "supported": bool(raw.get("supported", True)),
            "registrations": self._redact_value(registrations),
            "count": len(registrations),
        }

    def _indexeddb_database(self, raw: Mapping[str, Any]) -> dict[str, Any]:
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
                                    "key_path": self._redact_value(raw_index.get("keyPath")),
                                    "unique": bool(raw_index.get("unique")),
                                    "multi_entry": bool(raw_index.get("multiEntry")),
                                }
                            )
                stores.append(
                    {
                        "name": raw_store.get("name"),
                        "key_path": self._redact_value(raw_store.get("keyPath")),
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

    def _indexeddb_entry(self, raw_entry: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "key": self._redact_value(raw_entry.get("key"), key_hint="key"),
            "primary_key": self._redact_value(
                raw_entry.get("primaryKey"),
                key_hint="primary_key",
            ),
            "value": self._redact_value(raw_entry.get("value"), key_hint="value"),
        }

    def _cache_entry(self, raw_entry: Mapping[str, Any]) -> dict[str, Any]:
        request_headers = raw_entry.get("requestHeaders")
        response_headers = raw_entry.get("responseHeaders")
        return {
            "request_url": self.redactor.redact_url(str(raw_entry.get("requestURL") or "")),
            "request_method": raw_entry.get("requestMethod"),
            "request_headers": self._redact_header_list(request_headers),
            "response_status": raw_entry.get("responseStatus"),
            "response_status_text": raw_entry.get("responseStatusText"),
            "response_time": raw_entry.get("responseTime"),
            "response_headers": self._redact_header_list(response_headers),
        }

    def _cache_response(self, raw_response: Mapping[str, Any]) -> dict[str, Any]:
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

    def _redact_header_list(self, value: Any) -> dict[str, str]:
        if not isinstance(value, list):
            return {}
        return self.redactor.redact_headers(
            {
                str(item.get("name")): str(item.get("value") or "")
                for item in value
                if isinstance(item, Mapping) and item.get("name") is not None
            }
        )

    def _redact_value(self, value: Any, *, key_hint: str | None = None) -> Any:
        if isinstance(key_hint, str) and _storage_name_is_sensitive(key_hint):
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
                str(key): self._redact_value(item, key_hint=str(key))
                for key, item in value.items()
            }
        if isinstance(value, (list, tuple)):
            return [self._redact_value(item, key_hint=key_hint) for item in value]
        return str(value)


def _page_security_origin(page: Any, payload: Mapping[str, Any]) -> str:
    explicit_origin = _payload_text_any(payload, "security_origin", "securityOrigin", "origin")
    if explicit_origin is not None:
        return explicit_origin
    url = str(getattr(page, "url", "") or "")
    parsed = urlsplit(url)
    if not parsed.scheme or not parsed.netloc:
        raise BrowserValidationError(
            "Browser storage inspection requires a page URL with scheme and host.",
        )
    return urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))


def _payload_text_any(payload: Mapping[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _payload_value_any(payload: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in payload:
            return payload.get(key)
    return None


def _payload_bool_any(payload: Mapping[str, Any], *keys: str) -> bool | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, bool):
            return value
    return None


def _payload_int_any(
    payload: Mapping[str, Any],
    *keys: str,
    minimum: int = 0,
) -> int | None:
    value = _payload_value_any(payload, *keys)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise BrowserValidationError(f"payload.{keys[0]} must be an integer.")
    resolved = int(value)
    if resolved < minimum:
        raise BrowserValidationError(
            f"payload.{keys[0]} must be greater than or equal to {minimum}.",
        )
    return resolved


def _payload_limit(payload: Mapping[str, Any], *, default: int, maximum: int = 200) -> int:
    limit = _payload_int_any(payload, "limit", "page_size", "pageSize", minimum=1)
    if limit is None:
        limit = default
    return min(limit, maximum)


def _payload_skip(payload: Mapping[str, Any]) -> int:
    return _payload_int_any(payload, "skip", "skip_count", "skipCount", minimum=0) or 0


def _storage_name_is_sensitive(name: str) -> bool:
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


def _new_page_cdp_session(page: Any) -> Any:
    return BrowserCdpSessionBroker().open_command_session(page)


def _send_cdp_session_command(
    session: Any,
    method: str,
    params: Mapping[str, Any] | None = None,
) -> Any:
    return BrowserCdpSessionBroker().send_command(session, method, params)


def _detach_cdp_session(session: Any) -> None:
    BrowserCdpSessionBroker().detach(session)


__all__ = ["BrowserStorageInspectionService"]
