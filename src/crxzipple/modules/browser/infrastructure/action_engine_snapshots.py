from __future__ import annotations

from typing import Any, Mapping

from crxzipple.modules.browser.domain import BrowserStoredRef, BrowserValidationError
from crxzipple.modules.browser.domain.value_objects import _normalize_optional_text

from .action_engine_payloads import (
    _payload_text_any,
    _payload_value_any,
    _probe_timeout,
    _timeout_kwargs,
)
from .action_engine_scripts import (
    _ACTIVE_OVERLAY_SELECTOR_EXPRESSION,
    _ASSOCIATED_OVERLAY_SELECTOR_EXPRESSION,
)

_COMMON_INTERACTIVE_ROLES = frozenset(
    {
        "button",
        "checkbox",
        "combobox",
        "link",
        "listbox",
        "menuitem",
        "option",
        "radio",
        "searchbox",
        "slider",
        "spinbutton",
        "switch",
        "tab",
        "textbox",
        "treeitem",
    }
)
_DEFAULT_INTERACTIVE_REF_LIMIT = 40
_DEFAULT_EFFICIENT_SNAPSHOT_DEPTH = 6
_DEFAULT_FOCUSED_LOCATOR_LIMIT = 80
_HIGH_VALUE_INTERACTIVE_ROLES = frozenset(
    {
        "button",
        "checkbox",
        "combobox",
        "gridcell",
        "link",
        "menuitem",
        "option",
        "radio",
        "searchbox",
        "switch",
        "tab",
        "textbox",
    }
)
_HIGH_VALUE_INTERACTIVE_TAGS = frozenset(
    {
        "a",
        "button",
        "input",
        "select",
        "textarea",
    }
)


def _combine_frame_snapshots(
    frames: list[dict[str, Any]],
    *,
    key: str = "snapshot",
) -> str:
    if not frames:
        return "(empty)"
    if len(frames) == 1:
        value = frames[0].get(key)
        return str(value or "(empty)")
    chunks: list[str] = []
    for frame in frames:
        frame_path = frame.get("frame_path")
        snapshot = str(frame.get(key) or "(empty)")
        if isinstance(frame_path, list) and frame_path:
            label = f"frame {frame_path}"
        else:
            label = "main frame"
        chunks.append(f"[{label}]\n{snapshot}")
    return "\n\n".join(chunks)


def _role_snapshot_stats(
    *,
    snapshot: str,
    refs: tuple[BrowserStoredRef, ...],
) -> dict[str, int]:
    interactive_refs = sum(
        1
        for ref in refs
        if str(ref.role or "").strip().lower() in _HIGH_VALUE_INTERACTIVE_ROLES | _COMMON_INTERACTIVE_ROLES
    )
    return {
        "lines": len(str(snapshot).splitlines()),
        "chars": len(str(snapshot)),
        "refs": len(refs),
        "interactive": interactive_refs,
    }


def _normalize_snapshot_node(node: Any) -> dict[str, Any] | None:
    if not isinstance(node, dict):
        return None
    return dict(node)


def _normalize_text_payload(value: Any) -> list[str]:
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    if isinstance(value, (list, tuple)):
        resolved: list[str] = []
        for item in value:
            if isinstance(item, str) and item.strip():
                resolved.append(item.strip())
        return resolved
    return []


def _normalize_form_fields(value: Any) -> tuple[dict[str, Any], ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    normalized: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, Mapping):
            continue
        ref = _payload_text_any(item, "ref")
        if ref is None:
            continue
        field_type = _payload_text_any(item, "type") or "text"
        raw_value = _payload_value_any(item, "value")
        if isinstance(raw_value, (str, int, float, bool)) and not isinstance(raw_value, bool):
            value_payload: Any = str(raw_value)
        elif isinstance(raw_value, bool):
            value_payload = raw_value
        elif raw_value is None:
            value_payload = ""
        else:
            continue
        normalized.append(
            {
                "ref": ref,
                "type": field_type.strip().lower() or "text",
                "value": value_payload,
            }
        )
    return tuple(normalized)


def _interactive_snapshot_limit(
    payload: Mapping[str, Any],
    snapshot_format: str,
    limit: Any,
) -> int | None:
    if isinstance(limit, int) and limit > 0:
        return limit
    if snapshot_format == "interactive":
        mode = _snapshot_mode(payload, snapshot_format=snapshot_format)
        if mode == "focused":
            return _DEFAULT_FOCUSED_LOCATOR_LIMIT
        if mode == "wide":
            return None
        return _DEFAULT_INTERACTIVE_REF_LIMIT
    return None


def _interactive_role_snapshot_is_too_sparse(
    *,
    snapshot_mode: str | None,
    root_selector: str | None,
    ref_count: int,
) -> bool:
    if _normalize_optional_text(root_selector) is not None:
        return True
    if ref_count > 1:
        return False
    return snapshot_mode == "focused"


def _is_frame_detached_error(exc: Exception) -> bool:
    message = str(exc).strip().lower()
    return "frame was detached" in message


def _is_transient_page_context_error(exc: Exception) -> bool:
    message = str(exc).strip().lower()
    return (
        "frame was detached" in message
        or "execution context was destroyed" in message
        or "cannot find context with specified id" in message
        or "most likely because of a navigation" in message
    )


def _requested_snapshot_mode(payload: Mapping[str, Any]) -> str | None:
    mode = payload.get("mode")
    if not isinstance(mode, str):
        return None
    normalized = mode.strip().lower()
    return normalized or None


def _snapshot_refs_mode(payload: Mapping[str, Any]) -> str | None:
    refs_mode = payload.get("refs_mode")
    if refs_mode is None:
        refs_mode = payload.get("refsMode")
    if not isinstance(refs_mode, str):
        return None
    normalized = refs_mode.strip().lower()
    if not normalized:
        return None
    if normalized not in {"role", "aria"}:
        raise BrowserValidationError("payload.refs_mode must be either 'role' or 'aria'.")
    return normalized


def _snapshot_frame_selector(payload: Mapping[str, Any]) -> str | None:
    frame_selector = payload.get("frame_selector")
    if frame_selector is None:
        frame_selector = payload.get("frameSelector")
    if not isinstance(frame_selector, str):
        return None
    normalized = frame_selector.strip()
    return normalized or None


def _requested_snapshot_format(payload: Mapping[str, Any]) -> str | None:
    requested = payload.get("format")
    if not isinstance(requested, str):
        return None
    normalized = requested.strip().lower()
    return normalized or None


def _resolve_snapshot_format(payload: Mapping[str, Any]) -> str:
    requested_format = _requested_snapshot_format(payload)
    refs_mode = _snapshot_refs_mode(payload)
    if refs_mode is None:
        return requested_format or "html"
    if requested_format is None:
        return refs_mode
    if requested_format in {"role", "aria"}:
        if requested_format != refs_mode:
            raise BrowserValidationError(
                "payload.refs_mode must match payload.format when using role or aria snapshots.",
            )
        return requested_format
    raise BrowserValidationError(
        "payload.refs_mode can only be used when payload.format is omitted or set to 'role'/'aria'.",
    )


def _snapshot_mode(payload: Mapping[str, Any], *, snapshot_format: str) -> str | None:
    requested = _requested_snapshot_mode(payload)
    if requested is not None:
        if snapshot_format == "interactive" and requested not in {"efficient", "focused", "wide"}:
            raise BrowserValidationError(
                "payload.mode for interactive snapshots must be 'efficient', 'focused', or 'wide'.",
            )
        return requested
    if snapshot_format == "interactive" and "compact" not in payload and "depth" not in payload:
        return "efficient"
    return None

def _snapshot_compact(payload: Mapping[str, Any], *, snapshot_format: str) -> bool:
    compact = payload.get("compact")
    if isinstance(compact, bool):
        return compact
    return _snapshot_mode(payload, snapshot_format=snapshot_format) == "efficient"


def _snapshot_depth(payload: Mapping[str, Any], *, snapshot_format: str) -> int | None:
    depth = payload.get("depth")
    if isinstance(depth, int) and depth >= 0:
        return depth
    if _snapshot_mode(payload, snapshot_format=snapshot_format) == "efficient":
        return _DEFAULT_EFFICIENT_SNAPSHOT_DEPTH
    return None


def _snapshot_item_visible(item: Mapping[str, Any]) -> bool:
    visible = item.get("visible")
    if isinstance(visible, bool):
        return visible
    return True


def _snapshot_item_disabled(item: Mapping[str, Any]) -> bool:
    disabled = item.get("disabled")
    if isinstance(disabled, bool):
        return disabled
    return False


def _snapshot_item_priority(item: Mapping[str, Any]) -> int:
    score = 0
    role = str(item.get("role") or "").strip().lower()
    tag = str(item.get("tag") or "").strip().lower()
    label = str(item.get("label") or "").strip()
    text = str(item.get("text") or "").strip()
    selector = str(item.get("selector") or "").strip()
    evidence = set(_snapshot_item_evidence(item))
    if role in _HIGH_VALUE_INTERACTIVE_ROLES:
        score += 3
    if tag in _HIGH_VALUE_INTERACTIVE_TAGS:
        score += 2
    if "native-control" in evidence:
        score += 3
    if "self-listener" in evidence or "ancestor-listener" in evidence:
        score += 2
    if "hit-test" in evidence:
        score += 2
    if label:
        score += 2
    if text:
        score += 1
    if selector.startswith("#"):
        score += 1
    return score


def _is_low_value_interactive_name(name: str | None) -> bool:
    normalized = _normalize_optional_text(name)
    if normalized is None:
        return False
    lowered = normalized.lower()
    return lowered in {
        "skip to content",
        "skip to main content",
        "skip navigation",
        "skip to navigation",
    }


def _snapshot_item_is_low_value_boilerplate(item: Mapping[str, Any]) -> bool:
    role = str(item.get("role") or "").strip().lower()
    if role != "link":
        return False
    return _is_low_value_interactive_name(
        str(item.get("label") or item.get("text") or "").strip() or None,
    )


def _snapshot_item_semantic_key(item: Mapping[str, Any]) -> tuple[str, str] | None:
    role = str(item.get("role") or "").strip().lower()
    name = str(item.get("label") or item.get("text") or "").strip()
    if not role or not name:
        return None
    return role, name


def _snapshot_item_evidence(item: Mapping[str, Any]) -> tuple[str, ...]:
    raw_evidence = item.get("evidence")
    if not isinstance(raw_evidence, (list, tuple)):
        return ()
    evidence: list[str] = []
    seen: set[str] = set()
    for value in raw_evidence:
        normalized = str(value).strip()
        if not normalized or normalized in seen:
            continue
        evidence.append(normalized)
        seen.add(normalized)
    return tuple(evidence)


def _snapshot_item_confidence(item: Mapping[str, Any]) -> float | None:
    raw_confidence = item.get("confidence")
    if raw_confidence is None:
        return None
    try:
        confidence = float(raw_confidence)
    except (TypeError, ValueError):
        return None
    if confidence < 0 or confidence > 1:
        return None
    return confidence


def _snapshot_item_bbox(item: Mapping[str, Any]) -> dict[str, float] | None:
    raw_bbox = item.get("bbox")
    if not isinstance(raw_bbox, Mapping):
        return None
    bbox: dict[str, float] = {}
    for key in ("x", "y", "width", "height"):
        value = raw_bbox.get(key)
        if value is None:
            return None
        try:
            bbox[key] = float(value)
        except (TypeError, ValueError):
            return None
    return bbox


def _snapshot_item_backend_node_id(item: Mapping[str, Any]) -> int | None:
    raw_backend_node_id = item.get("backend_node_id")
    if raw_backend_node_id is None:
        return None
    try:
        backend_node_id = int(raw_backend_node_id)
    except (TypeError, ValueError):
        return None
    return backend_node_id if backend_node_id >= 1 else None


def _snapshot_item_selector(item: Mapping[str, Any]) -> str | None:
    selector = item.get("selector")
    if not isinstance(selector, str):
        return None
    normalized = selector.strip()
    return normalized or None


def _snapshot_item_scope_selector(item: Mapping[str, Any]) -> str | None:
    selector = item.get("scope_selector")
    if not isinstance(selector, str):
        return None
    normalized = selector.strip()
    return normalized or None


def _selector_contains(parent_selector: str, child_selector: str) -> bool:
    if parent_selector == child_selector:
        return True
    return (
        child_selector.startswith(f"{parent_selector} > ")
        or child_selector.startswith(f"{parent_selector}>")
        or child_selector.startswith(f"{parent_selector} ")
    )


def _dedupe_nested_snapshot_candidates(
    candidates: list[tuple[tuple[int, ...], dict[str, Any]]],
) -> list[tuple[tuple[int, ...], dict[str, Any]]]:
    resolved: list[tuple[tuple[int, ...], dict[str, Any]]] = []
    for frame_path, item in candidates:
        semantic_key = _snapshot_item_semantic_key(item)
        selector = _snapshot_item_selector(item)
        scope_selector = _snapshot_item_scope_selector(item)
        if semantic_key is None or selector is None:
            resolved.append((frame_path, item))
            continue

        replace_index: int | None = None
        skip_item = False
        for index, (existing_frame_path, existing_item) in enumerate(resolved):
            if existing_frame_path != frame_path:
                continue
            if _snapshot_item_semantic_key(existing_item) != semantic_key:
                continue
            if _snapshot_item_scope_selector(existing_item) != scope_selector:
                continue
            existing_selector = _snapshot_item_selector(existing_item)
            if existing_selector is None:
                continue
            if _selector_contains(existing_selector, selector):
                skip_item = True
                break
            if _selector_contains(selector, existing_selector):
                replace_index = index
                break

        if skip_item:
            continue
        if replace_index is not None:
            resolved[replace_index] = (frame_path, item)
        else:
            resolved.append((frame_path, item))
    return resolved


def _main_frame(page):  # noqa: ANN001
    return getattr(page, "main_frame", page)


def _child_frames(frame) -> tuple[Any, ...]:  # noqa: ANN001
    frames = getattr(frame, "child_frames", ())
    if not frames:
        return ()
    return tuple(frames)


def _iter_frame_contexts(page) -> tuple[tuple[Any, tuple[int, ...]], ...]:  # noqa: ANN001
    resolved: list[tuple[Any, tuple[int, ...]]] = []

    def _visit(frame, frame_path: tuple[int, ...]) -> None:  # noqa: ANN001
        resolved.append((frame, frame_path))
        for child_index, child in enumerate(_child_frames(frame)):
            _visit(child, frame_path + (child_index,))

    _visit(_main_frame(page), ())
    return tuple(resolved)


def _resolve_frame_context(page, frame_path: tuple[int, ...]):  # noqa: ANN001
    frame = _main_frame(page)
    for index in frame_path:
        children = _child_frames(frame)
        if index >= len(children):
            raise BrowserValidationError(
                f"Browser ref frame path {list(frame_path)} is no longer available.",
            )
        frame = children[index]
    return frame


def _resolve_frame_from_selector(page, frame_selector: str):  # noqa: ANN001
    resolver = getattr(page, "resolve_frame_selector", None)
    if callable(resolver):
        frame = resolver(frame_selector)
        if frame is None:
            raise BrowserValidationError(
                f"Browser snapshot frame selector '{frame_selector}' did not resolve to a frame.",
            )
        return frame

    locator = page.locator(frame_selector)
    element_handle = locator.element_handle(**_timeout_kwargs(_probe_timeout(None)))
    if element_handle is None:
        raise BrowserValidationError(
            f"Browser snapshot frame selector '{frame_selector}' did not resolve to an iframe or frame element.",
        )
    content_frame = getattr(element_handle, "content_frame", None)
    if not callable(content_frame):
        raise BrowserValidationError(
            f"Browser snapshot frame selector '{frame_selector}' did not resolve to an iframe or frame element.",
        )
    frame = content_frame()
    if frame is None:
        raise BrowserValidationError(
            f"Browser snapshot frame selector '{frame_selector}' did not resolve to a frame.",
        )
    return frame


def _snapshot_frame_contexts(
    page,
    *,
    frame_selector: str | None,
) -> tuple[tuple[Any, tuple[int, ...]], ...]:  # noqa: ANN001
    resolved = _iter_frame_contexts(page)
    if frame_selector is None:
        return resolved
    selected_frame = _resolve_frame_from_selector(page, frame_selector)
    selected_path: tuple[int, ...] | None = None
    for frame, frame_path in resolved:
        if frame is selected_frame:
            selected_path = frame_path
            break
    if selected_path is None:
        raise BrowserValidationError(
            f"Browser snapshot frame selector '{frame_selector}' did not match a reachable frame.",
        )
    return tuple(
        (frame, frame_path)
        for frame, frame_path in resolved
        if frame_path[: len(selected_path)] == selected_path
    )


def _snapshot_root_contexts(
    page,
    *,
    frame_selector: str | None,
    root_selector: str | None,
) -> tuple[tuple[Any, tuple[int, ...]], ...]:  # noqa: ANN001
    if root_selector is None:
        return _snapshot_frame_contexts(page, frame_selector=frame_selector)
    if frame_selector is not None:
        scoped = _snapshot_frame_contexts(page, frame_selector=frame_selector)
        if not scoped:
            return ()
        return (scoped[0],)
    return ((_main_frame(page), ()),)


def _snapshot_root_locator(context, *, root_selector: str | None):  # noqa: ANN001
    return context.locator(root_selector or "body")


def _active_overlay_selector(page) -> str | None:  # noqa: ANN001
    resolver = getattr(page, "resolve_active_overlay_selector", None)
    if callable(resolver):
        resolved = resolver()
        if isinstance(resolved, str) and resolved.strip():
            return resolved.strip()
        return None
    evaluate = getattr(page, "evaluate", None)
    if not callable(evaluate):
        return None
    try:
        resolved = evaluate(_ACTIVE_OVERLAY_SELECTOR_EXPRESSION)
    except Exception:  # noqa: BLE001
        return None
    if isinstance(resolved, str) and resolved.strip():
        return resolved.strip()
    return None


def _associated_overlay_selector(  # noqa: ANN001
    page,
    *,
    overlay_kind: str | None = None,
    source_selector: str | None = None,
    source_scope_selector: str | None = None,
) -> str | None:
    resolver = getattr(page, "resolve_associated_overlay_selector", None)
    if callable(resolver):
        resolved = resolver(
            overlay_kind=overlay_kind,
            source_selector=source_selector,
            source_scope_selector=source_scope_selector,
        )
        if isinstance(resolved, str) and resolved.strip():
            return resolved.strip()
        return None
    evaluate = getattr(page, "evaluate", None)
    if not callable(evaluate):
        return None
    try:
        resolved = evaluate(
            _ASSOCIATED_OVERLAY_SELECTOR_EXPRESSION,
            {
                "overlayKind": _normalize_optional_text(overlay_kind),
                "sourceSelector": _normalize_optional_text(source_selector),
                "sourceScopeSelector": _normalize_optional_text(source_scope_selector),
            },
        )
    except Exception:  # noqa: BLE001
        return None
    if isinstance(resolved, str) and resolved.strip():
        return resolved.strip()
    return None

