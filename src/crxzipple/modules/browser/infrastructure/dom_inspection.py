from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from crxzipple.modules.browser.domain import BrowserValidationError

DOM_INSPECTION_KINDS = frozenset(
    {
        "dom-inspect",
        "dom-box-model",
        "dom-computed-style",
        "dom-clickability",
        "dom-highlight",
        "dom-mutation-wait",
    }
)
_DOM_INSPECT_EXPRESSION = """
/*__crxzipple_dom_inspect__*/
(element, raw) => {
  const input = raw && typeof raw === "object" ? raw : {};
  const includeStyles = input.include_styles !== false;
  const styleProperties = Array.isArray(input.style_properties)
    ? input.style_properties.map((item) => String(item || "").trim()).filter(Boolean)
    : [
      "display",
      "visibility",
      "opacity",
      "pointer-events",
      "position",
      "z-index",
      "overflow",
      "cursor",
      "color",
      "background-color",
      "font-size",
    ];
  const attrNames = Array.isArray(input.attributes)
    ? input.attributes.map((item) => String(item || "").trim()).filter(Boolean)
    : ["id", "class", "name", "type", "role", "aria-label", "aria-expanded", "aria-selected", "disabled", "readonly"];
  const rect = element && element.getBoundingClientRect ? element.getBoundingClientRect() : null;
  const style = element && window.getComputedStyle ? window.getComputedStyle(element) : null;
  const text = element ? String(element.innerText || element.textContent || "").trim().replace(/\\s+/g, " ") : "";
  const tag = element && element.tagName ? element.tagName.toLowerCase() : null;
  const role = element && element.getAttribute ? (element.getAttribute("role") || null) : null;
  const label = element && element.getAttribute ? (element.getAttribute("aria-label") || element.getAttribute("title") || null) : null;
  const value = element && "value" in element ? String(element.value || "") : null;
  const attributes = {};
  if (element && element.getAttribute) {
    for (const name of attrNames) {
      const value = element.getAttribute(name);
      if (value !== null && value !== "") attributes[name] = value;
    }
  }
  const box = rect ? {
    x: rect.x,
    y: rect.y,
    width: rect.width,
    height: rect.height,
    top: rect.top,
    right: rect.right,
    bottom: rect.bottom,
    left: rect.left,
  } : null;
  const viewport = {
    width: window.innerWidth || 0,
    height: window.innerHeight || 0,
  };
  const visible = !!(
    rect
    && rect.width > 0
    && rect.height > 0
    && style
    && style.visibility !== "hidden"
    && style.display !== "none"
    && Number(style.opacity || "1") > 0
  );
  const inViewport = !!(
    rect
    && rect.bottom >= 0
    && rect.right >= 0
    && rect.top <= viewport.height
    && rect.left <= viewport.width
  );
  const disabled = !!(
    element
    && (
      element.disabled === true
      || element.getAttribute("aria-disabled") === "true"
      || element.hasAttribute("disabled")
    )
  );
  const readOnly = !!(
    element
    && (
      element.readOnly === true
      || element.getAttribute("aria-readonly") === "true"
      || element.hasAttribute("readonly")
    )
  );
  const center = rect ? {
    x: Math.max(0, Math.min(viewport.width - 1, rect.left + rect.width / 2)),
    y: Math.max(0, Math.min(viewport.height - 1, rect.top + rect.height / 2)),
  } : null;
  const hit = center && document.elementFromPoint ? document.elementFromPoint(center.x, center.y) : null;
  const blocked = !!(hit && element && hit !== element && !element.contains(hit));
  const summarize = (node) => {
    if (!node || !node.tagName) return null;
    const id = node.id ? `#${node.id}` : "";
    const cls = node.className && typeof node.className === "string"
      ? "." + node.className.trim().split(/\\s+/).filter(Boolean).slice(0, 3).join(".")
      : "";
    return {
      tag: node.tagName.toLowerCase(),
      selector_hint: `${node.tagName.toLowerCase()}${id}${cls}`,
      text: String(node.innerText || node.textContent || "").trim().replace(/\\s+/g, " ").slice(0, 120),
    };
  };
  const computedStyle = {};
  if (includeStyles && style) {
    for (const name of styleProperties) computedStyle[name] = style.getPropertyValue(name);
  }
  const editable = !!(
    element
    && (
      element.isContentEditable
      || ["input", "textarea", "select"].includes(tag)
      || role === "textbox"
      || role === "combobox"
    )
  );
  const clickable = visible && inViewport && !disabled && !blocked && !!(
    element
    && (
      ["a", "button", "input", "select", "textarea", "option"].includes(tag)
      || ["button", "link", "menuitem", "option", "tab", "checkbox", "radio", "switch", "combobox"].includes(role || "")
      || element.hasAttribute("onclick")
      || (style && style.cursor === "pointer")
    )
  );
  const eventSummary = (() => {
    const inlineHandlers = [];
    const propertyHandlers = [];
    const listenerTypes = [];
    if (!element) {
      return { inline_handlers: [], property_handlers: [], listener_types: [], has_handlers: false };
    }
    try {
      const names = typeof element.getAttributeNames === "function" ? element.getAttributeNames() : [];
      for (const name of names) {
        if (String(name || "").toLowerCase().startsWith("on")) {
          inlineHandlers.push(String(name).slice(2).toLowerCase());
        }
      }
    } catch {}
    for (const type of ["click", "input", "change", "submit", "keydown", "keyup", "mousedown", "mouseup", "pointerdown", "pointerup", "focus", "blur"]) {
      try {
        if (typeof element[`on${type}`] === "function") {
          propertyHandlers.push(type);
        }
      } catch {}
    }
    try {
      const customTypes = element.__crxzippleListenerTypes__;
      if (Array.isArray(customTypes)) {
        for (const type of customTypes) {
          const normalized = String(type || "").trim().toLowerCase();
          if (normalized) listenerTypes.push(normalized);
        }
      }
    } catch {}
    const unique = (items) => Array.from(new Set(items.filter(Boolean))).sort();
    const inline = unique(inlineHandlers);
    const properties = unique(propertyHandlers);
    const listeners = unique(listenerTypes);
    return {
      inline_handlers: inline,
      property_handlers: properties,
      listener_types: listeners,
      has_handlers: Boolean(inline.length || properties.length || listeners.length),
    };
  })();
  const reasons = [];
  if (!visible) reasons.push("not_visible");
  if (!inViewport) reasons.push("out_of_viewport");
  if (disabled) reasons.push("disabled");
  if (blocked) reasons.push("blocked_by_overlay");
  if (!clickable && !editable && reasons.length === 0) reasons.push("not_interactive");
  return {
    tag,
    role,
    label,
    text,
    value,
    attributes,
    box,
    viewport,
    visible,
    in_viewport: inViewport,
    disabled,
    read_only: readOnly,
    editable,
    clickable,
    click_point: center,
    blocked_by: blocked ? summarize(hit) : null,
    computed_style: computedStyle,
    event_summary: eventSummary,
    reasons,
  };
}
""".strip()
_DOM_HIGHLIGHT_EXPRESSION = """
/*__crxzipple_dom_highlight__*/
(element, raw) => {
  const input = raw && typeof raw === "object" ? raw : {};
  const durationMs = Math.max(100, Math.min(10000, Number(input.duration_ms || input.durationMs || 1200)));
  const color = typeof input.color === "string" && input.color.trim() ? input.color.trim() : "#3b82f6";
  const label = typeof input.label === "string" && input.label.trim() ? input.label.trim().slice(0, 80) : "";
  const rect = element && element.getBoundingClientRect ? element.getBoundingClientRect() : null;
  if (!rect) {
    return {
      highlighted: false,
      reason: "no_box",
      duration_ms: durationMs,
      color,
      label: label || null,
    };
  }
  const overlay = document.createElement("div");
  overlay.setAttribute("data-crxzipple-dom-highlight", "true");
  overlay.style.position = "fixed";
  overlay.style.left = `${rect.left}px`;
  overlay.style.top = `${rect.top}px`;
  overlay.style.width = `${rect.width}px`;
  overlay.style.height = `${rect.height}px`;
  overlay.style.border = `2px solid ${color}`;
  overlay.style.boxShadow = `0 0 0 3px rgba(59, 130, 246, 0.22)`;
  overlay.style.borderRadius = "4px";
  overlay.style.pointerEvents = "none";
  overlay.style.zIndex = "2147483647";
  overlay.style.boxSizing = "border-box";
  if (label) {
    const badge = document.createElement("div");
    badge.textContent = label;
    badge.style.position = "absolute";
    badge.style.left = "0";
    badge.style.top = "-24px";
    badge.style.maxWidth = "320px";
    badge.style.padding = "2px 6px";
    badge.style.borderRadius = "4px";
    badge.style.background = color;
    badge.style.color = "#fff";
    badge.style.font = "12px/18px system-ui, -apple-system, BlinkMacSystemFont, sans-serif";
    badge.style.whiteSpace = "nowrap";
    badge.style.overflow = "hidden";
    badge.style.textOverflow = "ellipsis";
    overlay.appendChild(badge);
  }
  document.documentElement.appendChild(overlay);
  window.setTimeout(() => {
    try {
      overlay.remove();
    } catch (_error) {
      /* noop */
    }
  }, durationMs);
  return {
    highlighted: true,
    duration_ms: durationMs,
    color,
    label: label || null,
    box: {
      x: rect.x,
      y: rect.y,
      width: rect.width,
      height: rect.height,
      top: rect.top,
      right: rect.right,
      bottom: rect.bottom,
      left: rect.left,
    },
  };
}
""".strip()
_DOM_MUTATION_WAIT_EXPRESSION = """
/*__crxzipple_dom_mutation_wait__*/
(element, raw) => new Promise((resolve) => {
  const input = raw && typeof raw === "object" ? raw : {};
  const timeoutMs = Math.max(1, Math.min(60000, Number(input.timeout_ms || input.timeoutMs || 5000)));
  const quietMs = Math.max(0, Math.min(5000, Number(input.quiet_ms || input.quietMs || 100)));
  const options = {
    childList: input.child_list !== false && input.childList !== false,
    subtree: input.subtree !== false,
    attributes: input.attributes === true,
    characterData: input.character_data === true || input.characterData === true,
  };
  if (!options.childList && !options.attributes && !options.characterData) {
    options.childList = true;
  }
  if (Array.isArray(input.attribute_filter) || Array.isArray(input.attributeFilter)) {
    const attributeFilter = (input.attribute_filter || input.attributeFilter)
      .map((item) => String(item || "").trim())
      .filter(Boolean);
    if (attributeFilter.length) {
      options.attributes = true;
      options.attributeFilter = attributeFilter;
    }
  }
  const start = performance.now();
  let mutationCount = 0;
  let quietTimer = null;
  let settled = false;
  let observer = null;
  let timeoutTimer = null;
  const finish = (changed, reason) => {
    if (settled) return;
    settled = true;
    if (quietTimer !== null) window.clearTimeout(quietTimer);
    if (timeoutTimer !== null) window.clearTimeout(timeoutTimer);
    if (observer) observer.disconnect();
    resolve({
      changed,
      reason,
      mutation_count: mutationCount,
      elapsed_ms: Math.round(performance.now() - start),
      timeout_ms: timeoutMs,
      quiet_ms: quietMs,
      options,
    });
  };
  observer = new MutationObserver((mutations) => {
    mutationCount += mutations.length;
    if (quietMs <= 0) {
      finish(true, "mutation");
      return;
    }
    if (quietTimer !== null) window.clearTimeout(quietTimer);
    quietTimer = window.setTimeout(() => finish(true, "quiet"), quietMs);
  });
  try {
    observer.observe(element, options);
  } catch (error) {
    finish(false, `observe_failed:${error && error.message ? error.message : "unknown"}`);
    return;
  }
  timeoutTimer = window.setTimeout(
    () => finish(mutationCount > 0, mutationCount > 0 ? "timeout_after_mutation" : "timeout"),
    timeoutMs,
  );
})
""".strip()


@dataclass(slots=True)
class BrowserDomInspectionService:
    def execute(
        self,
        *,
        kind: str,
        locator: Any,
        selector: str | None,
        payload: Mapping[str, Any],
        command_timeout_ms: float | None = None,
        devtools_event_listeners: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        include_styles = _payload_bool_any(payload, "include_styles", "includeStyles")
        if include_styles is None:
            include_styles = True
        raw_result = locator.evaluate(
            _DOM_INSPECT_EXPRESSION,
            {
                "include_styles": include_styles,
                "style_properties": _payload_text_list(
                    payload,
                    "style_properties",
                    "styleProperties",
                    "properties",
                ),
                "attributes": _payload_text_list(payload, "attributes"),
            },
        )
        if not isinstance(raw_result, Mapping):
            raise BrowserValidationError("Browser DOM inspection returned an invalid result.")
        result = _json_safe_payload(dict(raw_result))
        if not isinstance(result, dict):
            result = {}
        event_summary = _merge_event_summary(
            result.get("event_summary"),
            devtools_event_listeners,
        )
        common = {
            "kind": kind,
            "selector": selector,
            "tag": result.get("tag"),
            "role": result.get("role"),
            "label": result.get("label"),
            "text": result.get("text"),
            "visible": bool(result.get("visible")),
            "in_viewport": bool(result.get("in_viewport")),
            "disabled": bool(result.get("disabled")),
            "read_only": bool(result.get("read_only")),
            "editable": bool(result.get("editable")),
            "clickable": bool(result.get("clickable")),
            "event_summary": event_summary,
            "reasons": list(result.get("reasons") or ()),
        }
        if kind == "dom-box-model":
            return {
                **common,
                "box": result.get("box"),
                "viewport": result.get("viewport"),
                "click_point": result.get("click_point"),
            }
        if kind == "dom-computed-style":
            return {
                **common,
                "computed_style": result.get("computed_style") or {},
            }
        if kind == "dom-clickability":
            return {
                **common,
                "box": result.get("box"),
                "click_point": result.get("click_point"),
                "blocked_by": result.get("blocked_by"),
            }
        if kind == "dom-highlight":
            highlight_result = locator.evaluate(
                _DOM_HIGHLIGHT_EXPRESSION,
                {
                    "duration_ms": _payload_int_any(
                        payload,
                        "duration_ms",
                        "durationMs",
                        minimum=100,
                    )
                    or 1200,
                    "color": _payload_text_any(payload, "color"),
                    "label": _payload_text_any(payload, "label"),
                },
            )
            if not isinstance(highlight_result, Mapping):
                raise BrowserValidationError("Browser DOM highlight returned an invalid result.")
            highlight_payload = _json_safe_payload(dict(highlight_result))
            if not isinstance(highlight_payload, dict):
                highlight_payload = {}
            highlight_label = highlight_payload.get("label")
            return {
                **common,
                **highlight_payload,
                "label": common.get("label") or highlight_label,
                "highlight_label": highlight_label,
            }
        if kind == "dom-mutation-wait":
            timeout_ms = (
                _payload_int_any(payload, "timeout_ms", "timeoutMs", minimum=1)
                or (int(command_timeout_ms) if command_timeout_ms is not None else None)
                or 5000
            )
            mutation_result = locator.evaluate(
                _DOM_MUTATION_WAIT_EXPRESSION,
                {
                    "timeout_ms": timeout_ms,
                    "quiet_ms": _payload_int_any(payload, "quiet_ms", "quietMs", minimum=0)
                    or 100,
                    "subtree": _payload_bool_any(payload, "subtree"),
                    "child_list": _payload_bool_any(payload, "child_list", "childList"),
                    "attributes": _payload_bool_any(payload, "attributes"),
                    "character_data": _payload_bool_any(
                        payload,
                        "character_data",
                        "characterData",
                    ),
                    "attribute_filter": _payload_text_list(
                        payload,
                        "attribute_filter",
                        "attributeFilter",
                    ),
                },
            )
            if not isinstance(mutation_result, Mapping):
                raise BrowserValidationError("Browser DOM mutation wait returned an invalid result.")
            mutation_payload = _json_safe_payload(dict(mutation_result))
            if not isinstance(mutation_payload, dict):
                mutation_payload = {}
            return {
                **common,
                **mutation_payload,
            }
        return {
            **common,
            "value": result.get("value"),
            "attributes": result.get("attributes") or {},
            "box": result.get("box"),
            "viewport": result.get("viewport"),
            "click_point": result.get("click_point"),
            "blocked_by": result.get("blocked_by"),
            "computed_style": result.get("computed_style") or {},
        }


def _merge_event_summary(
    raw_summary: Any,
    devtools_event_listeners: Mapping[str, Any] | None,
) -> dict[str, Any]:
    summary = dict(raw_summary) if isinstance(raw_summary, Mapping) else {}
    inline_handlers = _normalized_text_list(summary.get("inline_handlers"))
    property_handlers = _normalized_text_list(summary.get("property_handlers"))
    listener_types = set(_normalized_text_list(summary.get("listener_types")))
    devtools_listeners = _summarize_devtools_listeners(devtools_event_listeners)

    for listener in devtools_listeners:
        listener_type = _normalized_event_type(listener.get("type"))
        if listener_type is not None:
            listener_types.add(listener_type)

    summary["inline_handlers"] = inline_handlers
    summary["property_handlers"] = property_handlers
    summary["listener_types"] = sorted(listener_types)
    summary["has_handlers"] = bool(
        inline_handlers
        or property_handlers
        or listener_types
        or devtools_listeners
    )
    if devtools_event_listeners is not None:
        summary["devtools_available"] = not bool(devtools_event_listeners.get("error"))
        summary["devtools_listener_count"] = _devtools_listener_count(
            devtools_event_listeners,
        )
        summary["devtools_listeners"] = devtools_listeners
        if devtools_event_listeners.get("error") is not None:
            summary["devtools_error"] = _bounded_text(
                str(devtools_event_listeners.get("error") or ""),
                limit=240,
            )
    return summary


def _summarize_devtools_listeners(
    payload: Mapping[str, Any] | None,
) -> list[dict[str, Any]]:
    if payload is None:
        return []
    raw_listeners = payload.get("listeners")
    if not isinstance(raw_listeners, list):
        return []
    summarized: list[dict[str, Any]] = []
    for raw_listener in raw_listeners:
        if not isinstance(raw_listener, Mapping):
            continue
        listener_type = _normalized_event_type(raw_listener.get("type"))
        if listener_type is None:
            continue
        item: dict[str, Any] = {"type": listener_type}
        for raw_key, output_key in (
            ("useCapture", "capture"),
            ("passive", "passive"),
            ("once", "once"),
        ):
            if raw_key in raw_listener:
                item[output_key] = bool(raw_listener.get(raw_key))
        script_id = _normalized_text(raw_listener.get("scriptId"))
        if script_id is not None:
            item["script_id"] = script_id
        url = _normalized_text(raw_listener.get("url"))
        if url is not None:
            item["url"] = _bounded_text(url, limit=240)
        line_number = _optional_int(raw_listener.get("lineNumber"))
        if line_number is not None:
            item["line_number"] = line_number
        column_number = _optional_int(raw_listener.get("columnNumber"))
        if column_number is not None:
            item["column_number"] = column_number
        handler_preview = _handler_preview(raw_listener.get("handler"))
        if handler_preview is not None:
            item["handler_preview"] = handler_preview
        summarized.append(item)
        if len(summarized) >= 12:
            break
    return summarized


def _devtools_listener_count(payload: Mapping[str, Any]) -> int:
    raw_listeners = payload.get("listeners")
    if not isinstance(raw_listeners, list):
        return 0
    return len([item for item in raw_listeners if isinstance(item, Mapping)])


def _handler_preview(value: Any) -> str | None:
    if isinstance(value, Mapping):
        for key in ("description", "className", "type"):
            candidate = _normalized_text(value.get(key))
            if candidate is not None:
                return _bounded_text(candidate, limit=200)
        return None
    candidate = _normalized_text(value)
    return _bounded_text(candidate, limit=200) if candidate is not None else None


def _normalized_text_list(value: Any) -> list[str]:
    if isinstance(value, str):
        items = (item.strip() for item in value.split(","))
    elif isinstance(value, (list, tuple, set)):
        items = (str(item).strip() for item in value)
    else:
        return []
    return sorted({item.lower() for item in items if item})


def _normalized_event_type(value: Any) -> str | None:
    normalized = _normalized_text(value)
    return normalized.lower() if normalized is not None else None


def _normalized_text(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized if normalized else None


def _bounded_text(value: str, *, limit: int) -> str:
    normalized = " ".join(str(value).split())
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[: max(0, limit - 3)].rstrip()}..."


def _optional_int(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _payload_text_list(payload: Mapping[str, Any], *keys: str) -> list[str]:
    raw_value = _payload_value_any(payload, *keys)
    if raw_value is None:
        return []
    if isinstance(raw_value, str):
        return [item.strip() for item in raw_value.split(",") if item.strip()]
    if isinstance(raw_value, (list, tuple)):
        return [str(item).strip() for item in raw_value if str(item).strip()]
    raise BrowserValidationError("DOM inspection properties/attributes must be a string or list.")


def _payload_text_any(
    payload: Mapping[str, Any],
    *keys: str,
) -> str | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _payload_bool_any(
    payload: Mapping[str, Any],
    *keys: str,
) -> bool | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, bool):
            return value
    return None


def _payload_value_any(
    payload: Mapping[str, Any],
    *keys: str,
) -> Any:
    for key in keys:
        if key in payload:
            return payload.get(key)
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


def _json_safe_payload(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return {str(key): _json_safe_payload(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe_payload(item) for item in value]
    return str(value)
