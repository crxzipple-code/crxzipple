from __future__ import annotations

from collections.abc import Callable
from typing import Any, Mapping

from crxzipple.modules.browser.domain import (
    BrowserExecutionPlan,
    BrowserPageActionCommand,
    BrowserProfileRuntimeState,
    BrowserTab,
    BrowserValidationError,
)

from .action_engine_payloads import (
    _count_batch_actions,
    _json_safe_payload,
    _MAX_BATCH_ACTIONS,
    _MAX_BATCH_DEPTH,
    _normalize_batch_action,
)

BrowserBatchInnerExecutor = Callable[
    [BrowserPageActionCommand, int],
    tuple[Any, str | None, tuple[int, ...] | None],
]


def execute_browser_batch(
    *,
    plan: BrowserExecutionPlan,
    tab: BrowserTab,
    runtime_state: BrowserProfileRuntimeState,
    command: BrowserPageActionCommand,
    batch_depth: int,
    execute_inner: BrowserBatchInnerExecutor,
) -> dict[str, Any]:
    if batch_depth > _MAX_BATCH_DEPTH:
        raise BrowserValidationError(
            f"Batch nesting depth exceeds maximum of {_MAX_BATCH_DEPTH}.",
        )
    raw_actions = command.payload.get("actions")
    if not isinstance(raw_actions, (list, tuple)) or not raw_actions:
        raise BrowserValidationError("batch requires actions.")
    if _count_batch_actions(raw_actions) > _MAX_BATCH_ACTIONS:
        raise BrowserValidationError(f"Batch exceeds maximum of {_MAX_BATCH_ACTIONS} actions.")

    actions: list[BrowserPageActionCommand] = []
    for raw_action in raw_actions:
        if not isinstance(raw_action, Mapping):
            raise BrowserValidationError("batch actions must be objects.")
        actions.append(
            _normalize_batch_action(
                raw_action=raw_action,
                profile_name=plan.profile.name,
                inherited_target_id=tab.target_id,
                inherited_timeout_ms=command.timeout_ms,
                depth=batch_depth + 1,
            )
        )
    if not actions:
        raise BrowserValidationError("batch requires actions.")
    stop_on_error = command.payload.get("stop_on_error")
    if not isinstance(stop_on_error, bool):
        stop_on_error = True

    results: list[dict[str, Any]] = []
    for action in actions:
        try:
            result_value, _selector, _frame_path = execute_inner(
                action,
                batch_depth + 1,
            )
            if action.kind == "snapshot" and isinstance(result_value, dict):
                runtime_state.remember_page_snapshot(
                    target_id=tab.target_id,
                    generation=int(result_value.get("generation") or 1),
                    snapshot_format=str(result_value.get("format") or "snapshot"),
                    ref_count=int(result_value.get("ref_count") or 0),
                    frame_count=int(result_value.get("frame_count") or 0),
                )
            results.append(
                {
                    "kind": action.kind,
                    "ok": True,
                    "target": {
                        "target_id": action.target.target_id,
                        "ref": action.target.ref,
                        "selector": action.target.selector,
                    },
                    "result": _json_safe_payload(result_value),
                }
            )
        except Exception as exc:  # noqa: BLE001
            error_payload = {
                "kind": action.kind,
                "ok": False,
                "target": {
                    "target_id": action.target.target_id,
                    "ref": action.target.ref,
                    "selector": action.target.selector,
                },
                "error": {
                    "type": exc.__class__.__name__,
                    "message": str(exc),
                },
            }
            results.append(error_payload)
            if stop_on_error:
                break

    return {
        "kind": "batch",
        "stop_on_error": stop_on_error,
        "results": results,
        "ok": all(item.get("ok") is True for item in results),
    }
