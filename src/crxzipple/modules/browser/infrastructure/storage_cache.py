from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from crxzipple.modules.browser.domain import BrowserValidationError

from .cdp_sessions import display_safe_cdp_error
from .storage_cdp import page_security_origin, send_cdp_session_command
from .storage_payloads import payload_limit, payload_skip, payload_text_any
from .storage_result_projection import BrowserStorageResultProjector


@dataclass(frozen=True, slots=True)
class BrowserCacheStorageInspector:
    projector: BrowserStorageResultProjector = field(
        default_factory=BrowserStorageResultProjector,
    )

    def execute(
        self,
        *,
        page: Any,
        session: Any,
        kind: str,
        payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        origin = page_security_origin(page, payload)
        cache_items = self._cache_items(session=session, origin=origin)
        if kind == "storage-cache-list":
            return {
                "kind": kind,
                "origin": origin,
                "caches": cache_items,
                "count": len(cache_items),
            }
        return self._get_cache_entries(
            session=session,
            payload=payload,
            origin=origin,
            kind=kind,
            cache_items=cache_items,
        )

    def _cache_items(self, *, session: Any, origin: str) -> list[dict[str, Any]]:
        raw_caches = send_cdp_session_command(
            session,
            "CacheStorage.requestCacheNames",
            {"securityOrigin": origin},
        )
        caches = raw_caches.get("caches") if isinstance(raw_caches, Mapping) else None
        return (
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

    def _get_cache_entries(
        self,
        *,
        session: Any,
        payload: Mapping[str, Any],
        origin: str,
        kind: str,
        cache_items: list[dict[str, Any]],
    ) -> dict[str, Any]:
        cache_id = payload_text_any(payload, "cache_id", "cacheId")
        cache_name = payload_text_any(payload, "cache_name", "cacheName", "cache")
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
        request_url = payload_text_any(payload, "request_url", "requestURL", "url")
        limit = payload_limit(payload, default=50)
        skip = payload_skip(payload)
        entries_payload = send_cdp_session_command(
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
                self.projector.cache_entry(raw_entry)
                for raw_entry in raw_entries
                if isinstance(raw_entry, Mapping)
            ]
            if isinstance(raw_entries, list)
            else []
        )
        response = self._cached_response(
            session=session,
            cache_id=cache_id,
            request_url=request_url,
        )
        return {
            "kind": kind,
            "origin": origin,
            "cache_id": cache_id,
            "cache_name": cache_name,
            "request_url": self.projector.redactor.redact_url(request_url)
            if request_url
            else None,
            "skip": skip,
            "limit": limit,
            "entries": entries,
            "count": len(entries),
            "return_count": entries_payload.get("returnCount")
            if isinstance(entries_payload, Mapping)
            else None,
            "response": response,
        }

    def _cached_response(
        self,
        *,
        session: Any,
        cache_id: str,
        request_url: str | None,
    ) -> dict[str, Any] | None:
        if request_url is None:
            return None
        try:
            raw_response = send_cdp_session_command(
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
                return self.projector.cache_response(
                    raw_body if isinstance(raw_body, Mapping) else raw_response,
                )
        except Exception as exc:  # pragma: no cover - CDP support varies by target
            return {
                "error": display_safe_cdp_error(
                    exc,
                    operation="CacheStorage.requestCachedResponse",
                )
            }
        return None


__all__ = ["BrowserCacheStorageInspector"]
