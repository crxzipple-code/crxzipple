from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import time
from typing import Any, Mapping

from crxzipple.modules.browser.domain import (
    BrowserActionTarget,
    BrowserExecutionPlan,
    BrowserPageActionCommand,
    BrowserProfileRuntimeState,
    BrowserTab,
)

from .action_trace_envelope import (
    _trace_action_envelope,
    _trace_recommendation,
)
from .action_trace_network import _trace_network_payload
from .action_trace_payloads import (
    _json_safe_payload,
    _mapping_result,
    _payload_bool_any,
    _payload_int_any,
    _payload_text_any,
    _snapshot_result,
    _trace_capture_id,
    _trace_error_message,
)
from .action_trace_snapshot import (
    _action_trace_inner_command,
    _action_trace_snapshot_command,
    _action_trace_snapshot_payload,
    _serialize_frame_path,
    _trace_delta_items,
    _trace_snapshot_diff,
    _trace_snapshot_limit_for_action_ref,
    _trace_snapshot_payload,
)
from .action_trace_state import (
    _trace_lifecycle_delta,
    _trace_lifecycle_snapshot,
    _trace_storage_delta,
    _trace_storage_snapshot,
)

ActionTraceSnapshot = Callable[[BrowserPageActionCommand], Mapping[str, Any]]
ActionTraceNetworkAction = Callable[[BrowserPageActionCommand], Mapping[str, Any]]
ActionTraceInnerExecutor = Callable[
    [BrowserPageActionCommand, int],
    tuple[Any, str | None, tuple[int, ...] | None],
]
ActionTraceMessageReader = Callable[[int], list[dict[str, Any]]]

__all__ = (
    "ActionTraceInnerExecutor",
    "ActionTraceMessageReader",
    "ActionTraceNetworkAction",
    "ActionTraceSnapshot",
    "BrowserActionTraceService",
    "_trace_action_envelope",
    "_trace_recommendation",
    "_trace_snapshot_limit_for_action_ref",
    "_trace_snapshot_payload",
)


@dataclass(slots=True)
class BrowserActionTraceService:
    def execute(
        self,
        *,
        plan: BrowserExecutionPlan,
        tab: BrowserTab,
        page: Any,
        runtime_state: BrowserProfileRuntimeState,
        command: BrowserPageActionCommand,
        batch_depth: int,
        snapshot: ActionTraceSnapshot,
        network_action: ActionTraceNetworkAction,
        execute_inner: ActionTraceInnerExecutor,
        console_messages: ActionTraceMessageReader,
        page_errors: ActionTraceMessageReader,
    ) -> dict[str, Any]:
        del runtime_state
        trace_id = _payload_text_any(command.payload, "trace_id", "traceId") or (
            f"trace-{tab.target_id}-{time.time_ns()}"
        )
        action_command = _action_trace_inner_command(command=command, tab=tab)
        snapshot_payload = _action_trace_snapshot_payload(
            command.payload,
            action_ref=action_command.target.ref,
        )
        include_network = _payload_bool_any(
            command.payload,
            "include_network",
            "includeNetwork",
        )
        if include_network is None:
            include_network = True
        include_storage_diff = _payload_bool_any(
            command.payload,
            "include_storage_diff",
            "includeStorageDiff",
        )
        if include_storage_diff is None:
            include_storage_diff = True
        include_lifecycle_diff = _payload_bool_any(
            command.payload,
            "include_lifecycle_diff",
            "includeLifecycleDiff",
        )
        if include_lifecycle_diff is None:
            include_lifecycle_diff = True
        console_limit = (
            _payload_int_any(
                command.payload,
                "console_limit",
                "consoleLimit",
                minimum=1,
            )
            or 50
        )
        page_error_limit = (
            _payload_int_any(
                command.payload,
                "page_error_limit",
                "pageErrorLimit",
                minimum=1,
            )
            or 50
        )

        before_snapshot = _snapshot_result(
            snapshot(
                _action_trace_snapshot_command(
                    command=command,
                    tab=tab,
                    payload=snapshot_payload,
                )
            ),
        )
        console_before = console_messages(console_limit)
        page_errors_before = page_errors(page_error_limit)
        storage_before = _trace_storage_snapshot(page) if include_storage_diff else None
        lifecycle_before = (
            _trace_lifecycle_snapshot(page) if include_lifecycle_diff else None
        )

        network_start: dict[str, Any] | None = None
        network_stop: dict[str, Any] | None = None
        network_list: dict[str, Any] | None = None
        capture_id: str | None = None
        trace_errors: list[dict[str, str]] = []
        if include_network:
            capture_id = _payload_text_any(command.payload, "capture_id", "captureId")
            if capture_id is None:
                capture_id = _trace_capture_id(trace_id)
            try:
                network_start = _mapping_result(
                    network_action(
                        BrowserPageActionCommand(
                            profile_name=command.profile_name,
                            kind="network-start-capture",
                            target=BrowserActionTarget(target_id=tab.target_id),
                            payload={
                                "capture_id": capture_id,
                                "max_requests": _payload_int_any(
                                    command.payload,
                                    "max_requests",
                                    "maxRequests",
                                    minimum=1,
                                )
                                or 200,
                                "max_body_bytes": _payload_int_any(
                                    command.payload,
                                    "max_body_bytes",
                                    "maxBodyBytes",
                                    minimum=0,
                                )
                                or 262_144,
                                "metadata": {
                                    "source": "browser.action_trace",
                                    "trace_id": trace_id,
                                    "action_kind": action_command.kind,
                                    "action_target": {
                                        "target_id": action_command.target.target_id,
                                        "ref": action_command.target.ref,
                                        "selector": action_command.target.selector,
                                    },
                                },
                            },
                            timeout_ms=command.timeout_ms,
                        )
                    ),
                )
            except Exception as exc:  # noqa: BLE001
                trace_errors.append(
                    {
                        "source": "network-start-capture",
                        "message": _trace_error_message(exc),
                    }
                )
                capture_id = None

        action_result: Any | None = None
        action_selector: str | None = None
        action_frame_path: tuple[int, ...] | None = None
        action_error: dict[str, str] | None = None
        try:
            action_result, action_selector, action_frame_path = execute_inner(
                action_command,
                batch_depth + 1,
            )
        except Exception as exc:  # noqa: BLE001
            action_error = {
                "type": exc.__class__.__name__,
                "message": _trace_error_message(exc),
            }

        stabilize_ms = _payload_int_any(
            command.payload,
            "stabilize_ms",
            "stabilizeMs",
            minimum=0,
        )
        if stabilize_ms is None:
            stabilize_ms = 200
        if stabilize_ms:
            try:
                page.wait_for_timeout(float(stabilize_ms))
            except Exception as exc:  # noqa: BLE001
                trace_errors.append(
                    {
                        "source": "stabilize",
                        "message": _trace_error_message(exc),
                    }
                )

        if include_network and capture_id is not None:
            try:
                network_stop = _mapping_result(
                    network_action(
                        BrowserPageActionCommand(
                            profile_name=command.profile_name,
                            kind="network-stop-capture",
                            target=BrowserActionTarget(target_id=tab.target_id),
                            payload={"capture_id": capture_id},
                            timeout_ms=command.timeout_ms,
                        )
                    ),
                )
            except Exception as exc:  # noqa: BLE001
                trace_errors.append(
                    {
                        "source": "network-stop-capture",
                        "message": _trace_error_message(exc),
                    }
                )
            try:
                network_list = _mapping_result(
                    network_action(
                        BrowserPageActionCommand(
                            profile_name=command.profile_name,
                            kind="network-list-requests",
                            target=BrowserActionTarget(target_id=tab.target_id),
                            payload={
                                "capture_id": capture_id,
                                "limit": _payload_int_any(
                                    command.payload,
                                    "network_limit",
                                    "networkLimit",
                                    minimum=1,
                                )
                                or 50,
                            },
                            timeout_ms=command.timeout_ms,
                        )
                    ),
                )
            except Exception as exc:  # noqa: BLE001
                trace_errors.append(
                    {
                        "source": "network-list-requests",
                        "message": _trace_error_message(exc),
                    }
                )

        after_snapshot = _snapshot_result(
            snapshot(
                _action_trace_snapshot_command(
                    command=command,
                    tab=tab,
                    payload=snapshot_payload,
                )
            ),
        )
        console_after = console_messages(console_limit)
        page_errors_after = page_errors(page_error_limit)
        storage_after = _trace_storage_snapshot(page) if include_storage_diff else None
        lifecycle_after = (
            _trace_lifecycle_snapshot(page) if include_lifecycle_diff else None
        )

        diff = _trace_snapshot_diff(before_snapshot, after_snapshot)
        console_delta = _trace_delta_items(console_before, console_after)
        page_error_delta = _trace_delta_items(page_errors_before, page_errors_after)
        storage_delta = (
            _trace_storage_delta(storage_before, storage_after)
            if storage_before is not None or storage_after is not None
            else None
        )
        lifecycle_delta = (
            _trace_lifecycle_delta(lifecycle_before, lifecycle_after)
            if lifecycle_before is not None or lifecycle_after is not None
            else None
        )
        network_payload = _trace_network_payload(
            capture_id=capture_id,
            start=network_start,
            stop=network_stop,
            listed=network_list,
        )
        recommendation = _trace_recommendation(
            action_error=action_error,
            diff=diff,
            network=network_payload,
            console_delta=console_delta,
            page_error_delta=page_error_delta,
            storage_delta=storage_delta,
            lifecycle_delta=lifecycle_delta,
        )
        return {
            "kind": "action-trace",
            "trace_id": trace_id,
            "profile_name": plan.profile.name,
            "target_id": tab.target_id,
            "action": {
                "kind": action_command.kind,
                "target": {
                    "target_id": action_command.target.target_id,
                    "ref": action_command.target.ref,
                    "selector": action_command.target.selector,
                },
                "payload": dict(action_command.payload),
                "ok": action_error is None,
                "error": action_error,
                "resolved_selector": action_selector,
                "frame_path": _serialize_frame_path(action_frame_path),
                "result": _json_safe_payload(action_result),
            },
            "before": _trace_snapshot_payload(before_snapshot),
            "after": _trace_snapshot_payload(after_snapshot),
            "diff": diff,
            "console": {
                "before_count": len(console_before),
                "after_count": len(console_after),
                "new": console_delta,
            },
            "page_errors": {
                "before_count": len(page_errors_before),
                "after_count": len(page_errors_after),
                "new": page_error_delta,
            },
            "network": network_payload,
            "storage": storage_delta,
            "lifecycle": lifecycle_delta,
            "recommendation": recommendation,
            "action_envelope": _trace_action_envelope(
                action_command=action_command,
                action_error=action_error,
                diff=diff,
                network=network_payload,
                console_delta=console_delta,
                page_error_delta=page_error_delta,
                storage_delta=storage_delta,
                lifecycle_delta=lifecycle_delta,
                recommendation=recommendation,
            ),
            "stabilize_ms": stabilize_ms,
            "errors": trace_errors,
        }
