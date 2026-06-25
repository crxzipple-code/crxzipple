from __future__ import annotations

from typing import Any, Mapping

from crxzipple.modules.browser.domain import BrowserPageActionCommand

from .action_trace_payloads import (
    _json_safe_payload,
    _payload_int_any,
    _payload_text_any,
)


def _trace_recommendation(
    *,
    action_error: Mapping[str, Any] | None,
    diff: Mapping[str, Any],
    network: Mapping[str, Any],
    console_delta: list[dict[str, Any]],
    page_error_delta: list[dict[str, Any]],
    storage_delta: Mapping[str, Any] | None = None,
    lifecycle_delta: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if action_error is not None and _trace_has_observable_effect(
        action_error=action_error,
        diff=diff,
        network=network,
        console_delta=console_delta,
        page_error_delta=page_error_delta,
        storage_delta=storage_delta,
        lifecycle_delta=lifecycle_delta,
    ):
        return {
            "next_action": "continue-from-after-snapshot",
            "reason": (
                "The wrapped page action reported failure, but page state changed. "
                "Treat the after snapshot and lifecycle delta as the current "
                "browser state before deciding the next step."
            ),
        }
    if action_error is not None:
        return {
            "next_action": "inspect-target",
            "reason": (
                "The wrapped page action failed. Inspect clickability, selector/ref "
                "freshness, or overlay state before retrying."
            ),
        }
    if page_error_delta:
        return {
            "next_action": "inspect-page-errors",
            "reason": "The action produced new page errors.",
        }
    request_count = _payload_int_any(network, "request_count", minimum=0) or 0
    if request_count > 0:
        causality = network.get("causality")
        script_frames = (
            causality.get("script_frames") if isinstance(causality, Mapping) else None
        )
        if isinstance(script_frames, list) and script_frames:
            return {
                "next_action": "inspect-script-initiator",
                "reason": (
                    "The action produced network activity with a script initiator. "
                    "Inspect the initiating script or replay the candidate request."
                ),
            }
        return {
            "next_action": "inspect-network-delta",
            "reason": "The action produced browser network activity that may reveal an API path.",
        }
    if lifecycle_delta is not None and bool(lifecycle_delta.get("changed")):
        return {
            "next_action": "inspect-page-lifecycle",
            "reason": "The action changed page lifecycle state such as URL, title, readiness, or focus.",
        }
    if storage_delta is not None and bool(storage_delta.get("changed")):
        return {
            "next_action": "inspect-storage-delta",
            "reason": "The action changed browser storage keys without visible network activity.",
        }
    if bool(diff.get("snapshot_changed")):
        return {
            "next_action": "continue-from-after-snapshot",
            "reason": "The visible interaction snapshot changed after the action.",
        }
    if console_delta:
        return {
            "next_action": "inspect-console-delta",
            "reason": "The action produced new console output without a visible snapshot change.",
        }
    return {
        "next_action": "observe-or-inspect-clickability",
        "reason": (
            "The action completed but no visible snapshot or network change was detected."
        ),
    }


def _trace_action_envelope(
    *,
    action_command: BrowserPageActionCommand,
    action_error: Mapping[str, Any] | None,
    diff: Mapping[str, Any],
    network: Mapping[str, Any],
    console_delta: list[dict[str, Any]],
    page_error_delta: list[dict[str, Any]],
    storage_delta: Mapping[str, Any] | None,
    lifecycle_delta: Mapping[str, Any] | None,
    recommendation: Mapping[str, Any],
) -> dict[str, Any]:
    tool_ok = action_error is None
    observed_effect = _trace_has_observable_effect(
        action_error=action_error,
        diff=diff,
        network=network,
        console_delta=console_delta,
        page_error_delta=page_error_delta,
        storage_delta=storage_delta,
        lifecycle_delta=lifecycle_delta,
    )
    page_effect_ok = observed_effect
    lifecycle_payload = lifecycle_delta if isinstance(lifecycle_delta, Mapping) else {}
    before = lifecycle_payload.get("before")
    after = lifecycle_payload.get("after")
    return {
        "kind": action_command.kind,
        "tool_ok": tool_ok,
        "page_effect_ok": page_effect_ok,
        "page_effect_status": (
            "action_failed_with_observed_effect"
            if not tool_ok and observed_effect
            else "action_failed"
            if not tool_ok
            else "observed_change"
            if page_effect_ok
            else "no_observable_change"
        ),
        "before": _trace_envelope_state(before),
        "after": _trace_envelope_state(after),
        "changes": _trace_envelope_changes(
            diff=diff,
            network=network,
            console_delta=console_delta,
            page_error_delta=page_error_delta,
            storage_delta=storage_delta,
            lifecycle_delta=lifecycle_delta,
        ),
        "result": {
            "recommendation": _json_safe_payload(recommendation),
        },
        "next_action": _payload_text_any(recommendation, "next_action"),
        "errors": [dict(action_error)] if isinstance(action_error, Mapping) else [],
    }


def _trace_has_observable_effect(
    *,
    action_error: Mapping[str, Any] | None,
    diff: Mapping[str, Any],
    network: Mapping[str, Any],
    console_delta: list[dict[str, Any]],
    page_error_delta: list[dict[str, Any]],
    storage_delta: Mapping[str, Any] | None,
    lifecycle_delta: Mapping[str, Any] | None,
) -> bool:
    request_count = _payload_int_any(network, "request_count", minimum=0) or 0
    network_changed = request_count > 0
    if action_error is not None and _trace_action_error_prevented_page_action(
        action_error,
    ):
        network_changed = False
    return bool(
        diff.get("snapshot_changed")
        or network_changed
        or console_delta
        or page_error_delta
        or (isinstance(storage_delta, Mapping) and storage_delta.get("changed"))
        or (isinstance(lifecycle_delta, Mapping) and lifecycle_delta.get("changed"))
    )


def _trace_action_error_prevented_page_action(action_error: Mapping[str, Any]) -> bool:
    message = (_payload_text_any(action_error, "message") or "").lower()
    if not message:
        return False
    return (
        "strict mode violation" in message
        or ("resolved to " in message and " elements" in message)
        or (
            "browser ref" in message
            and (
                "was not found" in message
                or "is stale" in message
                or "does not expose a supported locator" in message
                or "frame path" in message
                or "requires nth" in message
            )
        )
    )


def _trace_envelope_state(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    return {
        key: _json_safe_payload(value.get(key))
        for key in (
            "url",
            "title",
            "ready_state",
            "visibility_state",
            "focused",
            "history_length",
            "online",
        )
        if value.get(key) is not None
    }


def _trace_envelope_changes(
    *,
    diff: Mapping[str, Any],
    network: Mapping[str, Any],
    console_delta: list[dict[str, Any]],
    page_error_delta: list[dict[str, Any]],
    storage_delta: Mapping[str, Any] | None,
    lifecycle_delta: Mapping[str, Any] | None,
) -> dict[str, Any]:
    changes: dict[str, Any] = {
        "snapshot_changed": bool(diff.get("snapshot_changed")),
        "ref_count_delta": diff.get("ref_count_delta"),
        "network_request_count": _payload_int_any(
            network,
            "request_count",
            minimum=0,
        )
        or 0,
        "console_new_count": len(console_delta),
        "page_error_new_count": len(page_error_delta),
    }
    if isinstance(storage_delta, Mapping):
        changes["storage_changed"] = bool(storage_delta.get("changed"))
    if isinstance(lifecycle_delta, Mapping):
        changed_fields = lifecycle_delta.get("changed_fields")
        if isinstance(changed_fields, Mapping):
            changes["lifecycle_changed_fields"] = dict(changed_fields)
        changes["lifecycle_changed"] = bool(lifecycle_delta.get("changed"))
    return changes
