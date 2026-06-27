from __future__ import annotations

from dataclasses import dataclass, field
import json
import time
from typing import Any, Mapping

from crxzipple.modules.browser.domain import BrowserValidationError

from .cdp_sessions import BrowserCdpSessionBroker
from .error_projection import display_safe_exception_message


JsonObject = dict[str, Any]


@dataclass(slots=True)
class BrowserDevToolsAdapter:
    """Thin, page-scoped wrapper for native Chromium DevTools commands."""

    cdp_session_broker: BrowserCdpSessionBroker = field(
        default_factory=BrowserCdpSessionBroker,
    )

    def capture_dom_snapshot(
        self,
        page: Any,
        *,
        computed_styles: list[str] | tuple[str, ...] | None = None,
        include_dom_rects: bool = False,
        include_paint_order: bool = False,
        include_blended_background_colors: bool = False,
    ) -> JsonObject:
        params: JsonObject = {
            "computedStyles": list(computed_styles or ()),
            "includeDOMRects": bool(include_dom_rects),
            "includePaintOrder": bool(include_paint_order),
            "includeBlendedBackgroundColors": bool(include_blended_background_colors),
        }
        return self._send_page_command(
            page,
            "DOMSnapshot.captureSnapshot",
            params,
        )

    def get_node_for_location(
        self,
        page: Any,
        *,
        x: int,
        y: int,
        include_user_agent_shadow_dom: bool = False,
        ignore_pointer_events_none: bool = False,
    ) -> JsonObject:
        params: JsonObject = {
            "x": _json_safe_int("x", x),
            "y": _json_safe_int("y", y),
            "includeUserAgentShadowDOM": bool(include_user_agent_shadow_dom),
            "ignorePointerEventsNone": bool(ignore_pointer_events_none),
        }
        return self._send_page_command(page, "DOM.getNodeForLocation", params)

    def mark_backend_node(
        self,
        page: Any,
        *,
        backend_node_id: int,
        attribute_name: str,
        attribute_value: str,
    ) -> JsonObject:
        normalized_backend_node_id = _json_safe_positive_int(
            "backend_node_id",
            backend_node_id,
        )
        normalized_attribute_name = _required_text(
            "attribute_name",
            attribute_name,
        )
        normalized_attribute_value = _required_text(
            "attribute_value",
            attribute_value,
        )
        resolved = self.resolve_backend_node(
            page,
            backend_node_id=normalized_backend_node_id,
        )
        object_id = _required_text("object_id", str(resolved.get("object_id") or ""))
        marked = self._send_page_command(
            page,
            "Runtime.callFunctionOn",
            {
                "objectId": object_id,
                "functionDeclaration": _MARK_BACKEND_NODE_FUNCTION,
                "arguments": [
                    {"value": normalized_attribute_name},
                    {"value": normalized_attribute_value},
                ],
                "returnByValue": True,
                "awaitPromise": False,
            },
        )
        result = marked.get("result")
        if not isinstance(result, Mapping):
            raise BrowserValidationError(
                "Browser DevTools Runtime.callFunctionOn returned no result.",
            )
        value = result.get("value")
        if not isinstance(value, Mapping):
            raise BrowserValidationError(
                "Browser DevTools backend-node marker returned no value.",
            )
        if value.get("ok") is not True:
            reason = str(value.get("reason") or "not available")
            raise BrowserValidationError(
                f"Browser DevTools backend-node marker failed: {reason}.",
        )
        return dict(value)

    def resolve_backend_node(
        self,
        page: Any,
        *,
        backend_node_id: int,
    ) -> JsonObject:
        normalized_backend_node_id = _json_safe_positive_int(
            "backend_node_id",
            backend_node_id,
        )
        resolved = self._send_page_command(
            page,
            "DOM.resolveNode",
            {"backendNodeId": normalized_backend_node_id},
        )
        remote_object = resolved.get("object")
        if not isinstance(remote_object, Mapping):
            raise BrowserValidationError(
                "Browser DevTools DOM.resolveNode returned no remote object.",
            )
        object_id = _required_text(
            "object_id",
            str(remote_object.get("objectId") or ""),
        )
        return {
            "backend_node_id": normalized_backend_node_id,
            "object_id": object_id,
            "object": dict(remote_object),
        }

    def get_event_listeners_for_object(
        self,
        page: Any,
        *,
        object_id: str,
        depth: int | None = None,
        pierce: bool | None = None,
    ) -> JsonObject:
        normalized_object_id = _required_text("object_id", object_id)
        params: JsonObject = {"objectId": normalized_object_id}
        if depth is not None:
            params["depth"] = _json_safe_int("depth", depth)
        if pierce is not None:
            params["pierce"] = bool(pierce)
        return self._send_page_command(
            page,
            "DOMDebugger.getEventListeners",
            params,
        )

    def get_event_listeners_for_backend_node(
        self,
        page: Any,
        *,
        backend_node_id: int,
        depth: int | None = None,
        pierce: bool | None = None,
    ) -> JsonObject:
        resolved = self.resolve_backend_node(page, backend_node_id=backend_node_id)
        result = self.get_event_listeners_for_object(
            page,
            object_id=str(resolved["object_id"]),
            depth=depth,
            pierce=pierce,
        )
        return {
            **result,
            "backend_node_id": resolved["backend_node_id"],
            "object": resolved["object"],
        }

    def read_script_source(self, page: Any, *, script_id: str) -> JsonObject:
        params: JsonObject = {"scriptId": _required_text("script_id", script_id)}
        try:
            with self.cdp_session_broker.command_session(
                page,
                operation="Debugger.getScriptSource",
            ) as session:
                self.cdp_session_broker.send_command(session, "Debugger.enable", {})
                result = self.cdp_session_broker.send_command(
                    session,
                    "Debugger.getScriptSource",
                    params,
                )
                try:
                    self.cdp_session_broker.send_command(session, "Debugger.disable", {})
                except Exception:
                    pass
        except BrowserValidationError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise BrowserValidationError(
                "Browser DevTools Debugger.getScriptSource failed: "
                f"{_display_safe_message(exc)}",
            ) from exc
        json_result = _json_safe_payload(
            result or {},
            label="Debugger.getScriptSource result",
        )
        if not isinstance(json_result, dict):
            raise BrowserValidationError(
                "Browser DevTools Debugger.getScriptSource returned a non-object result.",
            )
        return json_result

    def collect_debugger_scripts(
        self,
        page: Any,
        *,
        wait_ms: int = 50,
    ) -> list[JsonObject]:
        normalized_wait_ms = _json_safe_int("wait_ms", wait_ms)
        if normalized_wait_ms < 0:
            raise BrowserValidationError(
                "Browser DevTools wait_ms must be greater than or equal to 0.",
            )
        scripts: list[JsonObject] = []

        def _on_script_parsed(payload: Mapping[str, Any]) -> None:
            try:
                scripts.append(
                    _json_safe_payload(
                        payload,
                        label="Debugger.scriptParsed payload",
                    )
                )
            except BrowserValidationError:
                return

        try:
            with self.cdp_session_broker.command_session(
                page,
                operation="Debugger.collectScripts",
            ) as session:
                _add_cdp_listener(session, "Debugger.scriptParsed", _on_script_parsed)
                try:
                    self.cdp_session_broker.send_command(
                        session,
                        "Debugger.enable",
                        {},
                    )
                    try:
                        self.cdp_session_broker.send_command(
                            session,
                            "Runtime.evaluate",
                            {"expression": "void 0", "returnByValue": True},
                        )
                    except Exception:
                        pass
                    if normalized_wait_ms:
                        time.sleep(normalized_wait_ms / 1000)
                finally:
                    _remove_cdp_listener(
                        session,
                        "Debugger.scriptParsed",
                        _on_script_parsed,
                    )
                    try:
                        self.cdp_session_broker.send_command(
                            session,
                            "Debugger.disable",
                            {},
                        )
                    except Exception:
                        pass
        except BrowserValidationError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise BrowserValidationError(
                "Browser DevTools Debugger.collectScripts failed: "
                f"{_display_safe_message(exc)}",
            ) from exc
        return scripts

    def _send_page_command(
        self,
        page: Any,
        method: str,
        params: Mapping[str, Any] | None = None,
    ) -> JsonObject:
        json_params = _json_safe_payload(params or {}, label=f"{method} payload")
        try:
            with self.cdp_session_broker.command_session(
                page,
                operation=method,
            ) as session:
                result = self.cdp_session_broker.send_command(
                    session,
                    method,
                    json_params,
                )
        except BrowserValidationError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise BrowserValidationError(
                f"Browser DevTools {method} failed: {_display_safe_message(exc)}",
            ) from exc
        json_result = _json_safe_payload(result or {}, label=f"{method} result")
        if not isinstance(json_result, dict):
            raise BrowserValidationError(
                f"Browser DevTools {method} returned a non-object result.",
            )
        return json_result


def _json_safe_payload(value: Any, *, label: str) -> Any:
    try:
        return json.loads(json.dumps(value, allow_nan=False))
    except (TypeError, ValueError) as exc:
        raise BrowserValidationError(
            f"Browser DevTools {label} must be JSON-safe.",
        ) from exc


def _json_safe_int(label: str, value: int) -> int:
    if isinstance(value, bool):
        raise BrowserValidationError(f"Browser DevTools {label} must be an integer.")
    try:
        normalized = int(value)
    except (TypeError, ValueError) as exc:
        raise BrowserValidationError(f"Browser DevTools {label} must be an integer.") from exc
    _json_safe_payload(normalized, label=label)
    return normalized


def _json_safe_positive_int(label: str, value: int) -> int:
    normalized = _json_safe_int(label, value)
    if normalized < 1:
        raise BrowserValidationError(
            f"Browser DevTools {label} must be a positive integer.",
        )
    return normalized


def _required_text(label: str, value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise BrowserValidationError(f"Browser DevTools {label} is required.")
    return value.strip()


def _display_safe_message(exc: Exception) -> str:
    return display_safe_exception_message(exc, limit=300)


def _add_cdp_listener(session: Any, event_name: str, callback: Any) -> None:
    for method_name in ("on", "add_listener", "addListener"):
        method = getattr(session, method_name, None)
        if callable(method):
            method(event_name, callback)
            return


def _remove_cdp_listener(session: Any, event_name: str, callback: Any) -> None:
    for method_name in ("off", "remove_listener", "removeListener"):
        method = getattr(session, method_name, None)
        if callable(method):
            method(event_name, callback)
            return


_MARK_BACKEND_NODE_FUNCTION = """
function(attributeName, attributeValue) {
  if (!(this instanceof Element)) {
    return { ok: false, reason: "remote object is not an Element" };
  }
  this.setAttribute(attributeName, attributeValue);
  return {
    ok: true,
    tag: String(this.tagName || "").toLowerCase(),
    id: String(this.id || ""),
    text: String(this.innerText || this.textContent || "").slice(0, 160)
  };
}
""".strip()


__all__ = ["BrowserDevToolsAdapter"]
