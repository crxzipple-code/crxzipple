from __future__ import annotations

import re
from typing import Any, Mapping

from crxzipple.modules.browser.domain import (
    BrowserPageActionCommand,
    BrowserProfileRuntimeState,
    BrowserStoredRef,
    BrowserTab,
)

from .action_engine_payloads import (
    _payload_bool_any,
    _payload_int_any,
    _payload_text_any,
    _payload_value_any,
)
from .action_engine_snapshots import _active_overlay_selector

def _command_overlay_source_refs(command: BrowserPageActionCommand) -> tuple[str, ...]:
    candidates: list[str] = []
    overlay_source_ref = _payload_text_any(
        command.payload,
        "overlay_source_ref",
        "overlaySourceRef",
    )
    if overlay_source_ref is not None:
        candidates.append(overlay_source_ref)
    if command.target.ref is not None:
        candidates.append(command.target.ref)
    scope_ref = _scope_ref_id(command.payload)
    if scope_ref is not None:
        candidates.append(scope_ref)
    seen: set[str] = set()
    resolved: list[str] = []
    for candidate in candidates:
        normalized = str(candidate).strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        resolved.append(normalized)
    return tuple(resolved)


def _command_overlay_source_selectors(
    command: BrowserPageActionCommand,
    *,
    resolved_selector: str | None = None,
) -> tuple[str, ...]:
    candidates: list[str] = []
    overlay_source_selector = _payload_text_any(
        command.payload,
        "overlay_source_selector",
        "overlaySourceSelector",
    )
    if overlay_source_selector is not None:
        candidates.append(overlay_source_selector)
    if resolved_selector is not None and ">>" not in resolved_selector:
        candidates.append(resolved_selector)
    if command.target.selector is not None:
        candidates.append(command.target.selector)
    scope_selector = _scope_selector(command.payload)
    if scope_selector is not None:
        candidates.append(scope_selector)
    seen: set[str] = set()
    resolved: list[str] = []
    for candidate in candidates:
        normalized = str(candidate).strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        resolved.append(normalized)
    return tuple(resolved)


def _command_overlay_source_scope_selectors(
    command: BrowserPageActionCommand,
) -> tuple[str, ...]:
    candidates: list[str] = []
    explicit_scope_selector = _payload_text_any(
        command.payload,
        "overlay_source_scope_selector",
        "overlaySourceScopeSelector",
    )
    if explicit_scope_selector is not None:
        candidates.append(explicit_scope_selector)
    scope_selector = _scope_selector(command.payload)
    if scope_selector is not None:
        candidates.append(scope_selector)
    seen: set[str] = set()
    resolved: list[str] = []
    for candidate in candidates:
        normalized = str(candidate).strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        resolved.append(normalized)
    return tuple(resolved)


def _effective_root_selector(
    *,
    page,
    runtime_state: BrowserProfileRuntimeState,
    tab: BrowserTab,
    payload: Mapping[str, Any],
    root_selector: str | None,
) -> str | None:  # noqa: ANN001
    if root_selector is not None:
        return root_selector
    if not _active_overlay(payload):
        return None
    return runtime_state.active_overlay_selector(
        target_id=tab.target_id,
        source_refs=tuple(
            normalized
            for normalized in (
                _payload_text_any(payload, "overlay_source_ref", "overlaySourceRef"),
            )
            if normalized is not None
        ),
        source_selectors=tuple(
            normalized
            for normalized in (
                _payload_text_any(payload, "overlay_source_selector", "overlaySourceSelector"),
            )
            if normalized is not None
        ),
        source_scope_selectors=tuple(
            normalized
            for normalized in (
                _payload_text_any(
                    payload,
                    "overlay_source_scope_selector",
                    "overlaySourceScopeSelector",
                ),
                _scope_selector(payload),
            )
            if normalized is not None
        ),
    ) or _active_overlay_selector(page)


def _stored_ref_name(item: BrowserStoredRef) -> str | None:
    return item.label or item.text


def _devtools_ref_marker_value(item: BrowserStoredRef) -> str:
    raw = f"ref-{item.ref}-{item.backend_node_id}-{item.generation}"
    marker = re.sub(r"[^a-zA-Z0-9_-]+", "-", raw).strip("-")
    return marker or "ref"


def _scope_ref_id(payload: Mapping[str, Any]) -> str | None:
    return _payload_text_any(payload, "scope_ref", "scopeRef")


def _scope_selector(payload: Mapping[str, Any]) -> str | None:
    return _payload_text_any(payload, "scope_selector", "scopeSelector")


def _locator_ordinal(payload: Mapping[str, Any]) -> int | None:
    return _payload_int_any(payload, "ordinal", minimum=0)


def _locator_exact(payload: Mapping[str, Any]) -> bool:
    exact = _payload_bool_any(payload, "exact")
    return bool(exact)


def _active_overlay(payload: Mapping[str, Any]) -> bool:
    active_overlay = _payload_bool_any(payload, "active_overlay", "activeOverlay")
    return bool(active_overlay)


def _allows_implicit_selector_ordinal(command: BrowserPageActionCommand) -> bool:
    return command.kind in {"fill", "type", "wait", "select", "press"}


def _explicit_overlay_kind(payload: Mapping[str, Any]) -> str | None:
    return _payload_text_any(payload, "overlay_kind", "overlayKind")


def _wait_prefers_active_overlay(command: BrowserPageActionCommand) -> bool:
    if command.kind != "wait":
        return False
    if command.target.ref is not None or command.target.selector is not None:
        return False
    if _scope_ref_id(command.payload) is not None or _scope_selector(command.payload) is not None:
        return False
    return bool(
        _payload_value_any(command.payload, "text", "text_gone", "textGone") is not None,
    )

