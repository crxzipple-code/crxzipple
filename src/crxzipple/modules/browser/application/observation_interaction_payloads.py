from __future__ import annotations

from typing import Any, Mapping

from .observation_values import _payload_text, _safe_int, _text_list

_FORM_FIELD_ROLES = frozenset(
    {
        "textbox",
        "searchbox",
        "combobox",
        "spinbutton",
        "checkbox",
        "radio",
        "switch",
        "listbox",
    }
)

_FORM_FIELD_TAGS = frozenset({"input", "textarea", "select"})

_FORM_ACTION_ROLES = frozenset({"button", "link", "menuitem", "tab"})

_FORM_ACTION_TAGS = frozenset({"button", "a"})

_OVERLAY_CANDIDATE_ROLES = frozenset(
    {
        "option",
        "menuitem",
        "listitem",
        "treeitem",
        "gridcell",
    }
)

_OVERLAY_CANDIDATE_EVIDENCE = frozenset({"picker-choice", "visual-fallback"})


def _form_payload(*, refs: tuple[dict[str, Any], ...]) -> dict[str, Any]:
    fields: list[dict[str, Any]] = []
    actions: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    for item in refs:
        ref = _interaction_ref_summary(item)
        if _is_form_field_ref(item):
            fields.append(ref)
            continue
        if _is_overlay_candidate_ref(item):
            candidates.append(ref)
            continue
        if _is_form_action_ref(item):
            actions.append(ref)
    return {
        "field_count": len(fields),
        "action_count": len(actions),
        "candidate_count": len(candidates),
        "fields": fields[:24],
        "actions": actions[:16],
        "candidates": candidates[:24],
        "guidance": _form_guidance(
            fields=fields, actions=actions, candidates=candidates
        ),
    }


def _overlay_payload(
    *,
    snapshot_result: Mapping[str, Any],
    refs: tuple[dict[str, Any], ...],
) -> dict[str, Any]:
    root_selector = _payload_text(snapshot_result.get("root_selector"))
    active_overlay = snapshot_result.get("active_overlay") is True
    candidates = [
        _interaction_ref_summary(item)
        for item in refs
        if _is_overlay_candidate_ref(item)
        or (
            root_selector is not None
            and _payload_text(item.get("scope_selector")) == root_selector
        )
    ]
    return {
        "active": bool(active_overlay or root_selector),
        "selector": root_selector,
        "candidate_count": len(candidates),
        "candidates": candidates[:32],
        "guidance": _overlay_guidance(
            active=bool(active_overlay or root_selector),
            candidates=candidates,
        ),
    }


def _interaction_ref_summary(item: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "ref": _payload_text(item.get("ref")),
        "label": _payload_text(item.get("label")) or _payload_text(item.get("text")),
        "role": _payload_text(item.get("role")),
        "tag": _payload_text(item.get("tag")),
        "selector": _payload_text(item.get("selector")),
        "scope_selector": _payload_text(item.get("scope_selector")),
        "text": _payload_text(item.get("text")),
        "evidence": _text_list(item.get("evidence"), limit=8),
        "confidence": item.get("confidence"),
    }


def _is_form_field_ref(item: Mapping[str, Any]) -> bool:
    role = (_payload_text(item.get("role")) or "").lower()
    tag = (_payload_text(item.get("tag")) or "").lower()
    evidence = set(_text_list(item.get("evidence"), limit=20))
    return bool(
        role in _FORM_FIELD_ROLES or tag in _FORM_FIELD_TAGS or "editable" in evidence
    )


def _is_form_action_ref(item: Mapping[str, Any]) -> bool:
    role = (_payload_text(item.get("role")) or "").lower()
    tag = (_payload_text(item.get("tag")) or "").lower()
    return bool(role in _FORM_ACTION_ROLES or tag in _FORM_ACTION_TAGS)


def _is_overlay_candidate_ref(item: Mapping[str, Any]) -> bool:
    role = (_payload_text(item.get("role")) or "").lower()
    evidence = set(_text_list(item.get("evidence"), limit=20))
    return bool(
        role in _OVERLAY_CANDIDATE_ROLES or evidence & _OVERLAY_CANDIDATE_EVIDENCE
    )


def _form_guidance(
    *,
    fields: list[dict[str, Any]],
    actions: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    if candidates:
        return {
            "next_action": "select-overlay-candidate",
            "reason": "Overlay candidates are visible; select one with browser.action.trace.",
            "suggested_tools": ["browser.action.trace", "browser.overlay.observe"],
        }
    if fields:
        return {
            "next_action": "trace-form-field-action",
            "reason": "Form fields are visible; trace fill/type/click to verify page state.",
            "suggested_tools": ["browser.action.trace", "browser.dom.inspect"],
        }
    if actions:
        return {
            "next_action": "trace-form-submit-action",
            "reason": "Action controls are visible but no fields were detected.",
            "suggested_tools": ["browser.action.trace", "browser.dom.clickability"],
        }
    return {
        "next_action": "observe-page-or-runtime",
        "reason": "No form fields, actions, or overlay candidates were detected.",
        "suggested_tools": ["browser.observe", "browser.runtime.inspect"],
    }


def _overlay_guidance(
    *, active: bool, candidates: list[dict[str, Any]]
) -> dict[str, Any]:
    if candidates:
        return {
            "next_action": "select-overlay-candidate",
            "reason": "The overlay exposes selectable candidates.",
            "suggested_tools": ["browser.action.trace", "browser.click"],
        }
    if active:
        return {
            "next_action": "inspect-overlay-dom",
            "reason": "An overlay root is active but no selectable candidates were detected.",
            "suggested_tools": ["browser.snapshot", "browser.dom.inspect"],
        }
    return {
        "next_action": "open-overlay",
        "reason": "No active overlay was detected.",
        "suggested_tools": ["browser.action.trace", "browser.click", "browser.type"],
    }


def _observation_guidance(
    *,
    refs: tuple[dict[str, Any], ...],
    errors: list[dict[str, Any]],
    runtime: Mapping[str, Any] | None,
    network: Mapping[str, Any],
    code: Mapping[str, Any],
    form: Mapping[str, Any],
    overlay: Mapping[str, Any],
) -> dict[str, Any]:
    return _primary_observation_guidance(
        refs=refs,
        errors=errors,
        runtime=runtime,
        network=network,
        code=code,
        form=form,
        overlay=overlay,
    )


def _primary_observation_guidance(
    *,
    refs: tuple[dict[str, Any], ...],
    errors: list[dict[str, Any]],
    runtime: Mapping[str, Any] | None,
    network: Mapping[str, Any],
    code: Mapping[str, Any],
    form: Mapping[str, Any],
    overlay: Mapping[str, Any],
) -> dict[str, Any]:
    if errors:
        return {
            "next_action": "inspect-observation-errors",
            "reason": "One or more observation sections failed.",
            "suggested_tools": [
                "browser.diagnostics.collect",
                "browser.runtime.inspect",
            ],
        }
    if (_safe_int(overlay.get("candidate_count")) or 0) > 0:
        return {
            "next_action": "select-overlay-candidate",
            "reason": "A visible overlay contains selectable candidates.",
            "suggested_tools": ["browser.action.trace", "browser.overlay.observe"],
        }
    capture = network.get("capture") if isinstance(network, Mapping) else None
    if isinstance(capture, Mapping):
        request_count = _safe_int(capture.get("request_count")) or 0
        if request_count > 0:
            return {
                "next_action": "inspect-network-capture",
                "reason": "Network capture already contains request activity.",
                "suggested_tools": [
                    "browser.network.list_requests",
                    "browser.network.get_response_body",
                    "browser.script.find_request",
                    "browser.script.extract_request",
                ],
            }
    request_matches = code.get("request_matches") if isinstance(code, Mapping) else None
    if (
        isinstance(request_matches, Mapping)
        and (_safe_int(request_matches.get("match_count")) or 0) > 0
    ):
        return {
            "next_action": "inspect-request-script",
            "reason": "Script request candidates are available.",
            "suggested_tools": [
                "browser.script.extract_request",
                "browser.script.inspect",
                "browser.network.replay_request",
            ],
        }
    search = code.get("search") if isinstance(code, Mapping) else None
    if isinstance(search, Mapping) and (_safe_int(search.get("match_count")) or 0) > 0:
        return {
            "next_action": "inspect-code-search-result",
            "reason": "Code search matched page scripts.",
            "suggested_tools": [
                "browser.script.extract_request",
                "browser.script.inspect",
                "browser.code.search",
            ],
        }
    if _has_runtime_or_script_signal(runtime=runtime, code=code):
        return {
            "next_action": "inspect-runtime-or-scripts",
            "reason": (
                "Runtime or script facts are available; inspect them before "
                "choosing state-changing page actions."
            ),
            "suggested_tools": [
                "browser.runtime.inspect",
                "browser.script.find_request",
                "browser.code.search",
                "browser.script.extract_request",
                "browser.network.inspect",
            ],
        }
    if (_safe_int(form.get("field_count")) or 0) > 0:
        return {
            "next_action": "trace-form-field-action",
            "reason": "Visible form fields are available.",
            "suggested_tools": ["browser.action.trace", "browser.form.inspect"],
        }
    if refs:
        return {
            "next_action": "trace-meaningful-action",
            "reason": "Interactive refs are available; use action trace to verify page effect.",
            "suggested_tools": ["browser.action.trace", "browser.dom.inspect"],
        }
    return {
        "next_action": "capture-current-state",
        "reason": "No strong interactive, network, runtime, or script signal was found.",
        "suggested_tools": ["browser.snapshot", "browser.screenshot"],
    }


def _has_runtime_or_script_signal(
    *,
    runtime: Mapping[str, Any] | None,
    code: Mapping[str, Any],
) -> bool:
    scripts = code.get("scripts") if isinstance(code, Mapping) else None
    script_count = (
        _safe_int(scripts.get("returned_scripts"))
        if isinstance(scripts, Mapping)
        else 0
    )
    if (script_count or 0) > 0:
        return True
    if not isinstance(runtime, Mapping):
        return False
    frameworks = runtime.get("frameworks")
    if isinstance(frameworks, Mapping) and _text_list(
        frameworks.get("detected"),
        limit=10,
    ):
        return True
    if isinstance(runtime.get("route_hints"), list | tuple) and runtime.get(
        "route_hints",
    ):
        return True
    if isinstance(runtime.get("globals"), list | tuple) and runtime.get("globals"):
        return True
    return False
