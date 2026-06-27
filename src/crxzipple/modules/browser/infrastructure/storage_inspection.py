from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from crxzipple.modules.browser.domain import BrowserValidationError

from .network_capture import DefaultBrowserNetworkRedactor
from .storage_cache import BrowserCacheStorageInspector
from .storage_cdp import (
    detach_cdp_session as _detach_cdp_session,
    new_page_cdp_session as _new_page_cdp_session,
)
from .storage_cookie_payloads import cookie_payload as _cookie_payload
from .storage_payloads import (
    payload_text_any as _payload_text_any,
    payload_value_any as _payload_value_any,
)
from .storage_indexeddb import BrowserIndexedDbStorageInspector
from .storage_result_projection import BrowserStorageResultProjector

_STORAGE_MARKER = "__crxzipple_storage_access__"
_STORAGE_EXPRESSION = f"""
/*{_STORAGE_MARKER}*/
({{ kind, operation, key, value }}) => {{
  const store = kind === "session" ? window.sessionStorage : window.localStorage;
  if (operation === "get") {{
    if (key) {{
      const resolved = store.getItem(key);
      return resolved === null ? {{}} : {{ [key]: resolved }};
    }}
    const out = {{}};
    for (let i = 0; i < store.length; i += 1) {{
      const itemKey = store.key(i);
      if (!itemKey) continue;
      const itemValue = store.getItem(itemKey);
      if (itemValue !== null) {{
        out[itemKey] = itemValue;
      }}
    }}
    return out;
  }}
  if (operation === "set") {{
    store.setItem(String(key), String(value ?? ""));
    return {{ [String(key)]: String(value ?? "") }};
  }}
  if (operation === "clear") {{
    store.clear();
    return {{}};
  }}
  throw new Error(`Unsupported storage operation: ${{operation}}`);
}}
""".strip()
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
                return BrowserIndexedDbStorageInspector(
                    projector=self._projector(),
                ).execute(page=page, session=session, kind=kind, payload=payload)
            finally:
                _detach_cdp_session(session)
        if kind.startswith("storage-cache-"):
            session = _new_page_cdp_session(page)
            try:
                return BrowserCacheStorageInspector(projector=self._projector()).execute(
                    page=page,
                    session=session,
                    kind=kind,
                    payload=payload,
                )
            finally:
                _detach_cdp_session(session)
        return self._service_worker(page=page, kind=kind, payload=payload)

    def _projector(self) -> BrowserStorageResultProjector:
        return BrowserStorageResultProjector(redactor=self.redactor)

    def redact_cookie(self, cookie: Mapping[str, Any]) -> dict[str, Any]:
        return self._projector().redact_cookie(cookie)

    def execute_cookies(
        self,
        *,
        page: Any,
        payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        operation = (
            _payload_text_any(
                payload,
                "cookies_operation",
                "cookiesOperation",
                "operation",
            )
            or "get"
        ).strip().lower()
        if operation not in {"get", "set", "clear"}:
            raise BrowserValidationError(
                "payload.cookies_operation must be one of get, set, or clear.",
            )
        page_context = _page_context(page)
        if operation == "get":
            raw_cookies = _call_context(page_context, "cookies")
            cookies: list[dict[str, Any]] = []
            if isinstance(raw_cookies, list):
                for item in raw_cookies:
                    if isinstance(item, Mapping):
                        cookies.append(self.redact_cookie(item))
            return {
                "kind": "cookies",
                "operation": "get",
                "count": len(cookies),
                "cookies": cookies,
            }
        if operation == "clear":
            _call_context(page_context, "clear_cookies")
            return {
                "kind": "cookies",
                "operation": "clear",
                "count": 0,
                "cookies": [],
            }
        raw_cookie = payload.get("cookie")
        if not isinstance(raw_cookie, Mapping):
            raise BrowserValidationError("payload.cookie is required for cookies set.")
        cookie_payload = _cookie_payload(raw_cookie)
        _call_context(page_context, "add_cookies", [cookie_payload])
        return {
            "kind": "cookies",
            "operation": "set",
            "count": 1,
            "cookies": [self.redact_cookie(cookie_payload)],
        }

    def execute_browser_storage(
        self,
        *,
        page: Any,
        payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        storage_kind = (
            _payload_text_any(
                payload,
                "storage_kind",
                "storageKind",
                "storage",
            )
            or "local"
        ).strip().lower()
        if storage_kind not in {"local", "session"}:
            raise BrowserValidationError(
                "payload.storage_kind must be either local or session.",
            )
        operation = (
            _payload_text_any(
                payload,
                "storage_operation",
                "storageOperation",
                "operation",
            )
            or "get"
        ).strip().lower()
        if operation not in {"get", "set", "clear"}:
            raise BrowserValidationError(
                "payload.storage_operation must be one of get, set, or clear.",
            )
        storage_key = _payload_text_any(
            payload,
            "storage_key",
            "storageKey",
            "key",
        )
        raw_value = _payload_value_any(
            payload,
            "storage_value",
            "storageValue",
            "value",
        )
        if operation == "set" and storage_key is None:
            raise BrowserValidationError("payload.storage_key is required for storage set.")
        values = page.evaluate(
            _STORAGE_EXPRESSION,
            {
                "kind": storage_kind,
                "operation": operation,
                "key": storage_key,
                "value": None if raw_value is None else str(raw_value),
            },
        )
        if not isinstance(values, Mapping):
            values = {}
        projector = self._projector()
        return {
            "kind": "storage",
            "storage_kind": storage_kind,
            "operation": operation,
            "key": storage_key,
            "values": {
                str(key): projector.redact_value(value, key_hint=str(key))
                for key, value in values.items()
                if value is not None
            },
        }

    def _service_worker(
        self,
        *,
        page: Any,
        kind: str,
        payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        projector = self._projector()
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
            "registrations": projector.redact_value(registrations),
            "count": len(registrations),
        }


def _page_context(page: Any) -> Any:
    page_context = getattr(page, "context", None)
    if callable(page_context):
        page_context = page_context()
    if page_context is None:
        raise BrowserValidationError("Playwright page does not expose a browser context.")
    return page_context


def _call_context(page_context: Any, method_name: str, *args: Any) -> Any:
    method = getattr(page_context, method_name, None)
    if not callable(method):
        raise BrowserValidationError(
            f"Playwright browser context does not support {method_name}().",
        )
    return method(*args)


__all__ = ["BrowserStorageInspectionService"]
