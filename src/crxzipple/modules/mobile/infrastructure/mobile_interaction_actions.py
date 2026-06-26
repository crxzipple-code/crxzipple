from __future__ import annotations

import time

from crxzipple.modules.mobile.application.ports import MobileRefStore
from crxzipple.modules.mobile.domain import (
    MobileActionCommand,
    MobileActionResult,
    MobileDeviceRuntimeState,
    MobileExecutionError,
    MobileExecutionPlan,
    MobileValidationError,
)

from .adb_client import AndroidAdbClient
from .adb_engine_helpers import (
    ANDROID_KEYCODES as _ANDROID_KEYCODES,
    SWIPE_DIRECTIONS as _SWIPE_DIRECTIONS,
    WAIT_POLL_SECONDS as _WAIT_POLL_SECONDS,
    clear_and_type_text as _clear_and_type_text,
    coerce_int as _coerce_int,
    swipe_points_for_direction as _swipe_points_for_direction,
    verify_typed_text as _verify_typed_text,
    wait_for_input_ready as _wait_for_input_ready,
)
from .mobile_action_targets import resolve_target_node as _resolve_target_node
from .ui_node_resolution import (
    bounds_center as _bounds_center,
    find_nodes_by_selector as _find_nodes_by_selector,
)


def execute_tap(
    ref_store: MobileRefStore,
    *,
    plan: MobileExecutionPlan,
    command: MobileActionCommand,
    runtime_state: MobileDeviceRuntimeState,
    client: AndroidAdbClient,
) -> tuple[MobileActionResult, MobileDeviceRuntimeState]:
    target = _resolve_target_node(
        ref_store,
        plan=plan,
        command=command,
        runtime_state=runtime_state,
        client=client,
    )
    if target.bounds is None:
        raise MobileValidationError("Resolved mobile target does not include bounds for tap.")
    x, y = _bounds_center(target.bounds)
    client.tap(x=x, y=y)
    runtime_state.clear_error()
    return (
        MobileActionResult(
            ok=True,
            device_name=plan.device.name,
            message="Tapped mobile UI target.",
            command=command,
            value=None,
        ),
        runtime_state,
    )


def execute_type(
    ref_store: MobileRefStore,
    *,
    plan: MobileExecutionPlan,
    command: MobileActionCommand,
    runtime_state: MobileDeviceRuntimeState,
    client: AndroidAdbClient,
) -> tuple[MobileActionResult, MobileDeviceRuntimeState]:
    target = _resolve_target_node(
        ref_store,
        plan=plan,
        command=command,
        runtime_state=runtime_state,
        client=client,
    )
    if target.bounds is None:
        raise MobileValidationError("Resolved mobile target does not include bounds for type.")
    text = str(command.payload.get("text") or "").strip()
    if not text:
        raise MobileValidationError("type requires payload.text.")
    x, y = _bounds_center(target.bounds)
    if not target.focused:
        client.tap(x=x, y=y)
    _wait_for_input_ready(client=client, target=target)
    clear = bool(command.payload.get("clear", True))
    _clear_and_type_text(client=client, target=target, text=text, clear=clear)
    if not _verify_typed_text(client=client, target=target, expected_text=text):
        client.tap(x=x, y=y)
        _wait_for_input_ready(client=client, target=target)
        _clear_and_type_text(client=client, target=target, text=text, clear=clear)
    runtime_state.clear_error()
    return (
        MobileActionResult(
            ok=True,
            device_name=plan.device.name,
            message="Typed into mobile UI target.",
            command=command,
            value={"text_length": len(text)},
        ),
        runtime_state,
    )


def execute_swipe(
    ref_store: MobileRefStore,
    *,
    plan: MobileExecutionPlan,
    command: MobileActionCommand,
    runtime_state: MobileDeviceRuntimeState,
    client: AndroidAdbClient,
) -> tuple[MobileActionResult, MobileDeviceRuntimeState]:
    payload = dict(command.payload)
    start_x = _coerce_int(payload.get("start_x"), label="payload.start_x")
    start_y = _coerce_int(payload.get("start_y"), label="payload.start_y")
    end_x = _coerce_int(payload.get("end_x"), label="payload.end_x")
    end_y = _coerce_int(payload.get("end_y"), label="payload.end_y")
    duration_ms = _coerce_int(payload.get("duration_ms"), label="payload.duration_ms")
    if duration_ms is None:
        duration_ms = 300
    if None not in (start_x, start_y, end_x, end_y):
        resolved_start_x = int(start_x)
        resolved_start_y = int(start_y)
        resolved_end_x = int(end_x)
        resolved_end_y = int(end_y)
    else:
        direction = str(payload.get("direction") or "up").strip().lower()
        if direction not in _SWIPE_DIRECTIONS:
            raise MobileValidationError(
                f"swipe direction must be one of {', '.join(sorted(_SWIPE_DIRECTIONS))}.",
            )
        if any(value is not None for value in (start_x, start_y, end_x, end_y)):
            raise MobileValidationError(
                "swipe requires all of payload.start_x/start_y/end_x/end_y, or use payload.direction.",
            )
        if command.target.ref or command.target.selector:
            target = _resolve_target_node(
                ref_store,
                plan=plan,
                command=command,
                runtime_state=runtime_state,
                client=client,
            )
            if target.bounds is None:
                raise MobileValidationError(
                    "Resolved mobile target does not include bounds for swipe.",
                )
            bounds = target.bounds
        else:
            display_size = client.display_size()
            bounds = (0, 0, display_size.width, display_size.height)
        resolved_start_x, resolved_start_y, resolved_end_x, resolved_end_y = (
            _swipe_points_for_direction(
                bounds=bounds,
                direction=direction,
            )
        )
    client.swipe(
        start_x=resolved_start_x,
        start_y=resolved_start_y,
        end_x=resolved_end_x,
        end_y=resolved_end_y,
        duration_ms=duration_ms,
    )
    runtime_state.clear_error()
    return (
        MobileActionResult(
            ok=True,
            device_name=plan.device.name,
            message="Swiped on Android device.",
            command=command,
            value={
                "start_x": resolved_start_x,
                "start_y": resolved_start_y,
                "end_x": resolved_end_x,
                "end_y": resolved_end_y,
                "duration_ms": duration_ms,
            },
        ),
        runtime_state,
    )


def execute_press(
    *,
    plan: MobileExecutionPlan,
    command: MobileActionCommand,
    runtime_state: MobileDeviceRuntimeState,
    client: AndroidAdbClient,
) -> tuple[MobileActionResult, MobileDeviceRuntimeState]:
    key = str(command.payload.get("key") or "").strip().upper()
    keycode = command.payload.get("keycode")
    if keycode is None:
        keycode = _ANDROID_KEYCODES.get(key)
    if keycode is None:
        raise MobileValidationError(
            "press requires payload.keycode or a supported payload.key.",
        )
    client.press_keycode(keycode=int(keycode))
    runtime_state.clear_error()
    return (
        MobileActionResult(
            ok=True,
            device_name=plan.device.name,
            message="Pressed Android keycode.",
            command=command,
            value={"keycode": int(keycode)},
        ),
        runtime_state,
    )


def execute_wait(
    *,
    plan: MobileExecutionPlan,
    command: MobileActionCommand,
    runtime_state: MobileDeviceRuntimeState,
    client: AndroidAdbClient,
) -> tuple[MobileActionResult, MobileDeviceRuntimeState]:
    payload = dict(command.payload)
    timeout_ms = command.timeout_ms or 30_000
    delay_ms = payload.get("delay_ms")
    if delay_ms is not None:
        time.sleep(max(int(delay_ms), 0) / 1000)
        runtime_state.clear_error()
        return (
            MobileActionResult(
                ok=True,
                device_name=plan.device.name,
                message="Wait condition satisfied on mobile device.",
                command=command,
                value=None,
            ),
            runtime_state,
        )
    selector = command.target.selector or payload.get("selector")
    text = str(payload.get("text") or "").strip()
    deadline = time.monotonic() + (timeout_ms / 1000)
    while time.monotonic() < deadline:
        source = client.dump_ui_xml()
        if selector:
            if _find_nodes_by_selector(source, str(selector)):
                runtime_state.clear_error()
                return (
                    MobileActionResult(
                        ok=True,
                        device_name=plan.device.name,
                        message="Wait condition satisfied on mobile device.",
                        command=command,
                        value=None,
                    ),
                    runtime_state,
                )
        elif text:
            if text in source:
                runtime_state.clear_error()
                return (
                    MobileActionResult(
                        ok=True,
                        device_name=plan.device.name,
                        message="Wait condition satisfied on mobile device.",
                        command=command,
                        value=None,
                    ),
                    runtime_state,
                )
        else:
            raise MobileValidationError("wait requires delay_ms, selector, or payload.text.")
        time.sleep(_WAIT_POLL_SECONDS)
    raise MobileExecutionError("Mobile wait timed out.")


__all__ = [
    "execute_press",
    "execute_swipe",
    "execute_tap",
    "execute_type",
    "execute_wait",
]
