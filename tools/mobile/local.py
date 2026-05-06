from __future__ import annotations

import asyncio
import json
from typing import Any

from crxzipple.modules.mobile.domain import MobileExecutionError, MobileValidationError
from crxzipple.modules.mobile.interfaces import MobileActionRequest, MobileControlRequest
from crxzipple.modules.tool.domain import ToolExecutionContext, ToolRunResult
from crxzipple.shared.content_blocks import image_ref_content_block, text_content_block

_MOBILE_CONTROL_KINDS = frozenset(
    {
        "list-devices",
        "launch-app",
        "activate-app",
        "terminate-app",
    }
)
_MOBILE_ACTION_KINDS = frozenset(
    {
        "snapshot",
        "screenshot",
        "tap",
        "swipe",
        "type",
        "press",
        "wait",
    }
)
_MOBILE_SCRIPT_STABILIZE_KINDS = frozenset({"none", "micro", "auto"})
_MOBILE_SCRIPT_OBSERVE_AFTER_KINDS = frozenset(
    {"none", "interactive", "tree", "text", "interactive_text", "auto"}
)
_MOBILE_SINGLE_ACTION_AUTO_OBSERVE_KINDS = frozenset(
    {"tap", "type", "swipe", "press", "wait"}
)
_MOBILE_SINGLE_ACTION_AUTO_STABILIZE_KINDS = frozenset(
    {"tap", "type", "swipe", "press"}
)
_MOBILE_SCRIPT_MICRO_STABILIZE_MS = 200
_MOBILE_TOOL_ACTION_ONLY_MESSAGE = (
    "mobile tools do not expose control or lifecycle steps. "
    "Use action steps only, or use the mobile API/CLI for device-level debugging."
)


def _normalize_text(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _normalize_timeout(value: object) -> int | None:
    if value in (None, ""):
        return None
    try:
        numeric = int(value)
    except (TypeError, ValueError) as exc:
        raise MobileValidationError("timeout_ms must be an integer.") from exc
    if numeric < 1:
        raise MobileValidationError("timeout_ms must be greater than or equal to 1.")
    return numeric


def _coerce_payload(value: object) -> dict[str, Any]:
    if value in (None, ""):
        return {}
    if not isinstance(value, dict):
        raise MobileValidationError("payload must decode to an object.")
    return dict(value)


def _normalize_bool(value: object, *, label: str) -> bool | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off"}:
            return False
    raise MobileValidationError(f"{label} must be a boolean.")


def _normalize_script_stabilize(value: object, *, label: str) -> str | None:
    normalized = _normalize_text(value)
    if normalized is None:
        return None
    candidate = normalized.lower()
    if candidate not in _MOBILE_SCRIPT_STABILIZE_KINDS:
        raise MobileValidationError(
            f"{label} must be one of {', '.join(sorted(_MOBILE_SCRIPT_STABILIZE_KINDS))}.",
        )
    return candidate


def _normalize_script_observe_after(value: object, *, label: str) -> str | None:
    normalized = _normalize_text(value)
    if normalized is None:
        return None
    candidate = normalized.lower()
    if candidate not in _MOBILE_SCRIPT_OBSERVE_AFTER_KINDS:
        raise MobileValidationError(
            f"{label} must be one of {', '.join(sorted(_MOBILE_SCRIPT_OBSERVE_AFTER_KINDS))}.",
        )
    return candidate


def _coerce_script_steps(value: object) -> list[dict[str, Any]]:
    candidate = value
    if isinstance(candidate, str):
        try:
            candidate = json.loads(candidate)
        except json.JSONDecodeError as exc:
            raise MobileValidationError(
                "mobile script steps must be a JSON array or an array of step objects.",
            ) from exc
    if not isinstance(candidate, list):
        raise MobileValidationError(
            "mobile script steps must be a list of step objects.",
        )
    normalized: list[dict[str, Any]] = []
    for item in candidate:
        step = item
        if isinstance(step, str):
            try:
                step = json.loads(step)
            except json.JSONDecodeError as exc:
                raise MobileValidationError(
                    "mobile script steps must be objects. Do not wrap each step in a JSON string.",
                ) from exc
        if not isinstance(step, dict):
            raise MobileValidationError(
                "mobile script steps must be objects. Do not wrap each step in a JSON string.",
            )
        normalized.append(dict(step))
    return normalized


def _mobile_runtime(container: Any) -> tuple[Any, Any]:
    facade = getattr(container, "mobile_facade", None)
    serializer = getattr(container, "mobile_result_serializer", None)
    if facade is None or serializer is None:
        raise RuntimeError("Mobile tool runtime is not available.")
    return facade, serializer


def _tool_result(
    *,
    tool_id: str,
    content: list[dict[str, Any]],
    details: Any,
    execution_context: ToolExecutionContext | None,
    kind: str | None = None,
    device_name: str | None = None,
) -> ToolRunResult:
    return ToolRunResult.structured(
        content=content,
        details=details,
        metadata={
            "tool": tool_id,
            "kind": kind,
            "device_name": device_name,
            "execution_context": (
                execution_context.to_payload()
                if execution_context is not None
                else None
            ),
        },
    )


def _snapshot_blocks(result: dict[str, Any]) -> list[dict[str, Any]]:
    value = result.get("value")
    if not isinstance(value, dict):
        summary = _normalize_text(result.get("message")) or "Captured mobile UI snapshot."
        return [text_content_block(summary)]
    snapshot = _normalize_text(value.get("snapshot"))
    text_excerpt = _normalize_text(value.get("text"))
    format_name = _normalize_text(value.get("format")) or "interactive_text"
    parts: list[str] = []
    if snapshot is not None:
        parts.append(snapshot)
    if (
        text_excerpt is not None
        and text_excerpt not in parts
        and format_name.lower() != "text"
    ):
        parts.append(f"Text:\n{text_excerpt}")
    if not parts:
        parts.append(_normalize_text(result.get("message")) or "Captured mobile UI snapshot.")
    return [text_content_block("\n\n".join(parts))]


def _screenshot_blocks(result: dict[str, Any]) -> list[dict[str, Any]]:
    value = result.get("value")
    if not isinstance(value, dict):
        return [text_content_block(_normalize_text(result.get("message")) or "Captured mobile screenshot.")]
    artifact_id = _normalize_text(value.get("artifact_id"))
    mime_type = _normalize_text(value.get("mime_type")) or "image/png"
    name = _normalize_text(value.get("name"))
    width = value.get("width")
    height = value.get("height")
    blocks: list[dict[str, Any]] = [
        text_content_block(_normalize_text(result.get("message")) or "Captured mobile screenshot."),
    ]
    if artifact_id is not None:
        blocks.append(
            image_ref_content_block(
                artifact_id=artifact_id,
                mime_type=mime_type,
                name=name,
                width=width if isinstance(width, int) else None,
                height=height if isinstance(height, int) else None,
            )
        )
    return blocks


def _default_blocks(result: dict[str, Any]) -> list[dict[str, Any]]:
    message = _normalize_text(result.get("message")) or "Mobile action completed."
    return [text_content_block(message)]


def _device_name(arguments: dict[str, Any]) -> str | None:
    return _normalize_text(arguments.get("device"))


def _resolve_step_family(kind: str, family: str | None) -> str:
    if family is not None:
        normalized_family = family.strip().lower()
        if normalized_family == "action":
            return normalized_family
        if normalized_family == "control":
            raise MobileValidationError(_MOBILE_TOOL_ACTION_ONLY_MESSAGE)
        raise MobileValidationError("mobile script step family must be either 'action' or omitted.")
    if kind in _MOBILE_ACTION_KINDS:
        return "action"
    if kind in _MOBILE_CONTROL_KINDS:
        raise MobileValidationError(_MOBILE_TOOL_ACTION_ONLY_MESSAGE)
    raise MobileValidationError(f"Unsupported mobile script step kind '{kind}'.")


def _mobile_blocks_for_result(kind: str, result: dict[str, Any]) -> list[dict[str, Any]]:
    if kind == "snapshot":
        return _snapshot_blocks(result)
    if kind == "screenshot":
        return _screenshot_blocks(result)
    return _default_blocks(result)


def _mobile_blocks_with_post_state(
    *,
    kind: str,
    result: dict[str, Any],
    post_state_result: dict[str, Any] | None,
    post_state_error: str | None,
    intermediate_results: list[dict[str, Any]] | None = None,
    intermediate_kinds: list[str] | None = None,
    intermediate_labels: list[str] | None = None,
) -> list[dict[str, Any]]:
    blocks = _mobile_blocks_for_result(kind, result)
    if intermediate_results:
        labels = intermediate_labels or []
        kinds = intermediate_kinds or []
        for index, item in enumerate(intermediate_results):
            label = labels[index] if index < len(labels) else None
            item_kind = kinds[index] if index < len(kinds) else "wait"
            if label:
                blocks.append(text_content_block(f"{label}:"))
            blocks.extend(_mobile_blocks_for_result(item_kind, item))
    if post_state_result is not None:
        blocks.extend(_snapshot_blocks(post_state_result))
    elif post_state_error is not None:
        blocks.append(text_content_block(f"Post-action snapshot failed: {post_state_error}"))
    return blocks


def _mobile_script_step_summary(
    *,
    index: int,
    family: str,
    kind: str,
    result: dict[str, Any],
) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "index": index,
        "family": family,
        "kind": kind,
        "ok": bool(result.get("ok", True)),
        "device_name": result.get("device_name"),
        "message": result.get("message"),
    }
    value = result.get("value")
    if isinstance(value, dict):
        value_summary: dict[str, Any] = {}
        if isinstance(value.get("format"), str):
            value_summary["format"] = value["format"]
        if isinstance(value.get("artifact_id"), str):
            value_summary["artifact_id"] = value["artifact_id"]
        refs = value.get("refs")
        if isinstance(refs, list):
            value_summary["ref_count"] = len(refs)
        text_value = value.get("text")
        if isinstance(text_value, str):
            value_summary["text_chars"] = len(text_value)
        snapshot_value = value.get("snapshot")
        if isinstance(snapshot_value, str):
            value_summary["snapshot_chars"] = len(snapshot_value)
        if value_summary:
            summary["value"] = value_summary
    elif value is not None:
        summary["value"] = value
    return summary


def _mobile_script_content(
    *,
    step_summaries: list[dict[str, Any]],
    post_state_result: dict[str, Any] | None,
    last_result: dict[str, Any] | None,
    last_kind: str | None,
) -> list[dict[str, Any]]:
    lines = [f"Mobile script completed {len(step_summaries)} step(s).", ""]
    for item in step_summaries:
        message = _normalize_text(item.get("message")) or "Completed."
        lines.append(f"{item['index']}. {item['kind']}: {message}")
    blocks: list[dict[str, Any]] = [text_content_block("\n".join(lines))]
    if post_state_result is not None:
        blocks.extend(_snapshot_blocks(post_state_result))
        return blocks
    if last_result is not None and last_kind is not None:
        blocks.extend(_mobile_blocks_for_result(last_kind, last_result))
    return blocks


def _resolve_mobile_script_stabilize(mode: str | None) -> str | None:
    if mode is None:
        return None
    if mode == "auto":
        return "micro"
    return mode


def _resolve_mobile_script_observe_mode(mode: str | None) -> str | None:
    if mode is None:
        return None
    if mode == "auto":
        return "interactive_text"
    if mode == "interactive":
        return "interactive"
    return mode


def _resolve_mobile_single_action_observe_payload(
    *,
    kind: str,
    arguments: dict[str, Any],
) -> dict[str, Any] | None:
    observe_after = _normalize_bool(arguments.get("observe_after"), label="observe_after")
    observe_payload = _coerce_payload(arguments.get("observe_payload"))
    if observe_after is False:
        return None
    if observe_after is True or kind in _MOBILE_SINGLE_ACTION_AUTO_OBSERVE_KINDS:
        observe_payload.setdefault("format", "interactive_text")
        return observe_payload
    return None


def _resolve_mobile_single_action_stabilize(
    *,
    kind: str,
    arguments: dict[str, Any],
    observe_enabled: bool,
) -> tuple[str | None, int | None]:
    raw_mode = _normalize_script_stabilize(arguments.get("stabilize"), label="stabilize")
    timeout_ms = _normalize_timeout(arguments.get("stabilize_timeout_ms"))
    if (
        raw_mode is None
        and observe_enabled
        and kind in _MOBILE_SINGLE_ACTION_AUTO_STABILIZE_KINDS
    ):
        raw_mode = "micro"
    return _resolve_mobile_script_stabilize(raw_mode), timeout_ms


async def _execute_mobile_action_tool(
    *,
    facade: Any,
    serializer: Any,
    tool_id: str,
    kind: str,
    request: MobileActionRequest,
    arguments: dict[str, Any],
    execution_context: ToolExecutionContext | None,
) -> ToolRunResult:
    result = await asyncio.to_thread(facade.execute, request)
    serialized = serializer.serialize(result)
    current_device_name = _normalize_text(serialized.get("device_name")) or request.device_name
    observe_payload = _resolve_mobile_single_action_observe_payload(
        kind=kind,
        arguments=arguments,
    )
    stabilize_mode, stabilize_timeout_ms = _resolve_mobile_single_action_stabilize(
        kind=kind,
        arguments=arguments,
        observe_enabled=observe_payload is not None,
    )
    stabilize_result: dict[str, Any] | None = None
    stabilize_error: str | None = None
    post_state_result: dict[str, Any] | None = None
    post_state_error: str | None = None
    if stabilize_mode not in {None, "none"}:
        try:
            stabilize_result = await asyncio.to_thread(
                _run_mobile_script_stabilize,
                facade=facade,
                serializer=serializer,
                device_name=current_device_name,
                mode=stabilize_mode,
                timeout_ms=stabilize_timeout_ms,
            )
        except (MobileValidationError, MobileExecutionError) as exc:
            stabilize_error = str(exc)
    if observe_payload is not None:
        try:
            post_state_result = await asyncio.to_thread(
                _run_mobile_script_observe_after,
                facade=facade,
                serializer=serializer,
                device_name=current_device_name,
                mode=str(observe_payload.get("format") or "interactive_text"),
                payload=observe_payload,
                timeout_ms=_normalize_timeout(arguments.get("timeout_ms")),
            )
        except (MobileValidationError, MobileExecutionError) as exc:
            post_state_error = str(exc)
    details = dict(serialized)
    if stabilize_mode is not None:
        details["stabilize"] = stabilize_mode
    if stabilize_result is not None:
        details["stabilize_result"] = stabilize_result
    if stabilize_error is not None:
        details["stabilize_error"] = stabilize_error
    if post_state_result is not None:
        details["post_state"] = post_state_result
    if post_state_error is not None:
        details["post_state_error"] = post_state_error
    if observe_payload is not None:
        details["observe_after"] = dict(observe_payload)
    return _tool_result(
        tool_id=tool_id,
        kind=kind,
        device_name=current_device_name,
        execution_context=execution_context,
            content=_mobile_blocks_with_post_state(
                kind=kind,
                result=serialized,
                post_state_result=post_state_result,
                post_state_error=post_state_error,
                intermediate_results=(
                    [stabilize_result] if stabilize_result is not None else None
                ),
                intermediate_kinds=(["wait"] if stabilize_result is not None else None),
                intermediate_labels=(
                    ["Post-action stabilize"] if stabilize_result is not None else None
                ),
            ),
        details=details,
    )


def _run_mobile_script_stabilize(
    *,
    facade: Any,
    serializer: Any,
    device_name: str | None,
    mode: str | None,
    timeout_ms: int | None,
) -> dict[str, Any] | None:
    effective_mode = _resolve_mobile_script_stabilize(mode)
    if effective_mode in {None, "none"}:
        return None
    if effective_mode == "micro":
        delay_ms = timeout_ms or _MOBILE_SCRIPT_MICRO_STABILIZE_MS
        return serializer.serialize(
            facade.execute(
                MobileActionRequest(
                    device_name=device_name,
                    kind="wait",
                    payload={"delay_ms": delay_ms},
                    timeout_ms=delay_ms,
                )
            )
        )
    raise MobileValidationError(f"Unsupported mobile script stabilize mode '{effective_mode}'.")


def _run_mobile_script_observe_after(
    *,
    facade: Any,
    serializer: Any,
    device_name: str | None,
    mode: str | None,
    payload: dict[str, Any],
    timeout_ms: int | None,
) -> dict[str, Any] | None:
    format_name = _resolve_mobile_script_observe_mode(mode)
    if format_name in {None, "none"}:
        return None
    observe_payload = dict(payload)
    observe_payload.setdefault("format", format_name)
    return serializer.serialize(
        facade.execute(
            MobileActionRequest(
                device_name=device_name,
                kind="snapshot",
                payload=observe_payload,
                timeout_ms=timeout_ms,
            )
        )
    )


def _build_mobile_script_request(
    *,
    family: str,
    kind: str,
    raw_step: dict[str, Any],
    device_name: str | None,
) -> MobileControlRequest | MobileActionRequest:
    timeout_ms = _normalize_timeout(raw_step.get("timeout_ms"))
    if family == "control":
        payload = _coerce_payload(raw_step.get("payload"))
        for key in ("app_package", "app_activity", "app_id"):
            value = _normalize_text(raw_step.get(key))
            if value is not None:
                payload.setdefault(key, value)
        return MobileControlRequest(
            device_name=device_name,
            kind=kind,
            payload=payload,
            timeout_ms=timeout_ms,
        )

    payload = _coerce_payload(raw_step.get("payload"))
    text = _normalize_text(raw_step.get("text"))
    if text is not None:
        payload.setdefault("text", text)
    key = _normalize_text(raw_step.get("key"))
    if key is not None:
        payload.setdefault("key", key)
    keycode = raw_step.get("keycode")
    if keycode is not None:
        payload.setdefault("keycode", keycode)
    format_name = _normalize_text(raw_step.get("format"))
    if format_name is not None:
        payload.setdefault("format", format_name)
    delay_ms = raw_step.get("delay_ms")
    if delay_ms is not None:
        payload.setdefault("delay_ms", delay_ms)
    return MobileActionRequest(
        device_name=device_name,
        kind=kind,
        ref=_normalize_text(raw_step.get("ref")),
        selector=_normalize_text(raw_step.get("selector")),
        payload=payload,
        timeout_ms=timeout_ms,
    )


def mobile_devices(container: Any):
    try:
        facade, serializer = _mobile_runtime(container)
    except RuntimeError:
        return None

    async def _handler(
        arguments: dict[str, Any],
        execution_context: ToolExecutionContext | None = None,
    ) -> ToolRunResult:
        del arguments
        result = await asyncio.to_thread(
            facade.execute,
            MobileControlRequest(
                device_name=None,
                kind="list-devices",
            ),
        )
        serialized = serializer.serialize(result)
        value = serialized.get("value", {})
        devices = value.get("devices") if isinstance(value, dict) else None
        adb_available = bool(value.get("adb_available")) if isinstance(value, dict) else False
        probe_ok = bool(value.get("probe_ok")) if isinstance(value, dict) else False
        adb_error = _normalize_text(value.get("adb_error")) if isinstance(value, dict) else None
        lines = ["# Mobile Devices", ""]
        if not adb_available:
            lines.append("Unable to inspect Android devices because `adb` is not available.")
            if adb_error is not None:
                lines.append("")
                lines.append(f"Error: {adb_error}")
        elif not probe_ok:
            lines.append("Unable to inspect Android devices because the `adb devices -l` probe failed.")
            if adb_error is not None:
                lines.append("")
                lines.append(f"Error: {adb_error}")
        elif isinstance(devices, list) and devices:
            for item in devices:
                if not isinstance(item, dict):
                    continue
                serial = _normalize_text(item.get("serial")) or "unknown"
                state = _normalize_text(item.get("state")) or "unknown"
                lines.append(f"- {serial} ({state})")
        else:
            lines.append("No Android devices are currently connected.")
        return _tool_result(
            tool_id="mobile_devices",
            kind="list-devices",
            device_name=None,
            execution_context=execution_context,
            content=[text_content_block("\n".join(lines))],
            details=serialized,
        )

    return _handler


def mobile_snapshot(container: Any):
    try:
        facade, serializer = _mobile_runtime(container)
    except RuntimeError:
        return None

    async def _handler(
        arguments: dict[str, Any],
        execution_context: ToolExecutionContext | None = None,
    ) -> ToolRunResult:
        payload = _coerce_payload(arguments.get("payload"))
        format_name = _normalize_text(arguments.get("format"))
        payload.setdefault("format", format_name or "interactive_text")
        result = await asyncio.to_thread(
            facade.execute,
            MobileActionRequest(
                device_name=_device_name(arguments),
                kind="snapshot",
                payload=payload,
                timeout_ms=_normalize_timeout(arguments.get("timeout_ms")),
            ),
        )
        serialized = serializer.serialize(result)
        return _tool_result(
            tool_id="mobile_snapshot",
            kind="snapshot",
            device_name=serialized.get("device_name"),
            execution_context=execution_context,
            content=_snapshot_blocks(serialized),
            details=serialized,
        )

    return _handler


def mobile_tap(container: Any):
    try:
        facade, serializer = _mobile_runtime(container)
    except RuntimeError:
        return None

    async def _handler(
        arguments: dict[str, Any],
        execution_context: ToolExecutionContext | None = None,
    ) -> ToolRunResult:
        return await _execute_mobile_action_tool(
            facade=facade,
            serializer=serializer,
            tool_id="mobile_tap",
            kind="tap",
            request=MobileActionRequest(
                device_name=_device_name(arguments),
                kind="tap",
                ref=_normalize_text(arguments.get("ref")),
                selector=_normalize_text(arguments.get("selector")),
                payload=_coerce_payload(arguments.get("payload")),
                timeout_ms=_normalize_timeout(arguments.get("timeout_ms")),
            ),
            arguments=arguments,
            execution_context=execution_context,
        )

    return _handler


def mobile_type(container: Any):
    try:
        facade, serializer = _mobile_runtime(container)
    except RuntimeError:
        return None

    async def _handler(
        arguments: dict[str, Any],
        execution_context: ToolExecutionContext | None = None,
    ) -> ToolRunResult:
        text = _normalize_text(arguments.get("text"))
        if text is None:
            raise MobileValidationError("mobile_type requires text.")
        ref = _normalize_text(arguments.get("ref"))
        selector = _normalize_text(arguments.get("selector"))
        if ref is None and selector is None:
            raise MobileValidationError("mobile_type requires ref or selector.")
        payload = _coerce_payload(arguments.get("payload"))
        payload.setdefault("text", text)
        return await _execute_mobile_action_tool(
            facade=facade,
            serializer=serializer,
            tool_id="mobile_type",
            kind="type",
            request=MobileActionRequest(
                device_name=_device_name(arguments),
                kind="type",
                ref=ref,
                selector=selector,
                payload=payload,
                timeout_ms=_normalize_timeout(arguments.get("timeout_ms")),
            ),
            arguments=arguments,
            execution_context=execution_context,
        )

    return _handler


def mobile_swipe(container: Any):
    try:
        facade, serializer = _mobile_runtime(container)
    except RuntimeError:
        return None

    async def _handler(
        arguments: dict[str, Any],
        execution_context: ToolExecutionContext | None = None,
    ) -> ToolRunResult:
        payload = _coerce_payload(arguments.get("payload"))
        direction = _normalize_text(arguments.get("direction"))
        if direction is not None:
            payload.setdefault("direction", direction)
        for key in ("start_x", "start_y", "end_x", "end_y", "duration_ms"):
            value = arguments.get(key)
            if value is not None:
                payload.setdefault(key, value)
        return await _execute_mobile_action_tool(
            facade=facade,
            serializer=serializer,
            tool_id="mobile_swipe",
            kind="swipe",
            request=MobileActionRequest(
                device_name=_device_name(arguments),
                kind="swipe",
                ref=_normalize_text(arguments.get("ref")),
                selector=_normalize_text(arguments.get("selector")),
                payload=payload,
                timeout_ms=_normalize_timeout(arguments.get("timeout_ms")),
            ),
            arguments=arguments,
            execution_context=execution_context,
        )

    return _handler


def mobile_press(container: Any):
    try:
        facade, serializer = _mobile_runtime(container)
    except RuntimeError:
        return None

    async def _handler(
        arguments: dict[str, Any],
        execution_context: ToolExecutionContext | None = None,
    ) -> ToolRunResult:
        payload = _coerce_payload(arguments.get("payload"))
        key = _normalize_text(arguments.get("key"))
        if key is not None:
            payload.setdefault("key", key)
        keycode = arguments.get("keycode")
        if keycode is not None:
            payload.setdefault("keycode", keycode)
        return await _execute_mobile_action_tool(
            facade=facade,
            serializer=serializer,
            tool_id="mobile_press",
            kind="press",
            request=MobileActionRequest(
                device_name=_device_name(arguments),
                kind="press",
                payload=payload,
                timeout_ms=_normalize_timeout(arguments.get("timeout_ms")),
            ),
            arguments=arguments,
            execution_context=execution_context,
        )

    return _handler


def mobile_wait(container: Any):
    try:
        facade, serializer = _mobile_runtime(container)
    except RuntimeError:
        return None

    async def _handler(
        arguments: dict[str, Any],
        execution_context: ToolExecutionContext | None = None,
    ) -> ToolRunResult:
        payload = _coerce_payload(arguments.get("payload"))
        text = _normalize_text(arguments.get("text"))
        if text is not None:
            payload.setdefault("text", text)
        delay_ms = arguments.get("delay_ms")
        if delay_ms is not None:
            payload.setdefault("delay_ms", delay_ms)
        selector = _normalize_text(arguments.get("selector"))
        return await _execute_mobile_action_tool(
            facade=facade,
            serializer=serializer,
            tool_id="mobile_wait",
            kind="wait",
            request=MobileActionRequest(
                device_name=_device_name(arguments),
                kind="wait",
                selector=selector,
                payload=payload,
                timeout_ms=_normalize_timeout(arguments.get("timeout_ms")),
            ),
            arguments=arguments,
            execution_context=execution_context,
        )

    return _handler


def mobile_screenshot(container: Any):
    try:
        facade, serializer = _mobile_runtime(container)
    except RuntimeError:
        return None

    async def _handler(
        arguments: dict[str, Any],
        execution_context: ToolExecutionContext | None = None,
    ) -> ToolRunResult:
        result = await asyncio.to_thread(
            facade.execute,
            MobileActionRequest(
                device_name=_device_name(arguments),
                kind="screenshot",
                payload=_coerce_payload(arguments.get("payload")),
                timeout_ms=_normalize_timeout(arguments.get("timeout_ms")),
            ),
        )
        serialized = serializer.serialize(result)
        return _tool_result(
            tool_id="mobile_screenshot",
            kind="screenshot",
            device_name=serialized.get("device_name"),
            execution_context=execution_context,
            content=_screenshot_blocks(serialized),
            details=serialized,
        )

    return _handler


def mobile_script(container: Any):
    try:
        facade, serializer = _mobile_runtime(container)
    except RuntimeError:
        return None

    async def _handler(
        arguments: dict[str, Any],
        execution_context: ToolExecutionContext | None = None,
    ) -> ToolRunResult:
        steps = _coerce_script_steps(arguments.get("steps"))
        if not steps:
            raise MobileValidationError("mobile_script requires at least one step.")

        stop_on_error = _normalize_bool(
            arguments.get("stop_on_error"),
            label="stop_on_error",
        )
        if stop_on_error is None:
            stop_on_error = True
        default_stabilize = _normalize_script_stabilize(
            arguments.get("default_stabilize"),
            label="default_stabilize",
        )
        default_stabilize_timeout_ms = _normalize_timeout(
            arguments.get("default_stabilize_timeout_ms"),
        )
        default_observe_after = _normalize_script_observe_after(
            arguments.get("default_observe_after"),
            label="default_observe_after",
        )
        default_observe_payload = _coerce_payload(
            arguments.get("default_observe_payload"),
        )

        final_observe = _coerce_payload(arguments.get("final_observe"))
        observe_after = _normalize_bool(
            arguments.get("observe_after"),
            label="observe_after",
        )
        if not final_observe and observe_after:
            final_observe = {"format": "interactive_text"}
        elif final_observe and "format" not in final_observe:
            final_observe["format"] = "interactive_text"

        current_device_name = _device_name(arguments)
        step_summaries: list[dict[str, Any]] = []
        last_result: dict[str, Any] | None = None
        last_kind: str | None = None
        latest_observed_result: dict[str, Any] | None = None

        for index, raw_step in enumerate(steps, start=1):
            kind = _normalize_text(raw_step.get("kind"))
            if kind is None:
                raise MobileValidationError(f"mobile script step {index} requires kind.")
            family = _resolve_step_family(
                kind,
                _normalize_text(raw_step.get("family")),
            )
            step_device_name = _normalize_text(raw_step.get("device")) or current_device_name
            request = _build_mobile_script_request(
                family=family,
                kind=kind,
                raw_step=raw_step,
                device_name=step_device_name,
            )
            try:
                result = await asyncio.to_thread(facade.execute, request)
            except (MobileValidationError, MobileExecutionError):
                if stop_on_error:
                    raise
                break
            serialized = serializer.serialize(result)
            current_device_name = _normalize_text(serialized.get("device_name")) or current_device_name
            raw_step_stabilize = _normalize_script_stabilize(
                raw_step.get("stabilize"),
                label=f"steps[{index}].stabilize",
            )
            step_stabilize = raw_step_stabilize or default_stabilize
            if family == "control" and raw_step_stabilize is None:
                step_stabilize = None
            step_stabilize_timeout_ms = _normalize_timeout(
                raw_step.get("stabilize_timeout_ms"),
            ) or default_stabilize_timeout_ms
            stabilize_result = await asyncio.to_thread(
                _run_mobile_script_stabilize,
                facade=facade,
                serializer=serializer,
                device_name=current_device_name,
                mode=step_stabilize,
                timeout_ms=step_stabilize_timeout_ms,
            )
            raw_step_observe_after = _normalize_script_observe_after(
                raw_step.get("observe_after"),
                label=f"steps[{index}].observe_after",
            )
            step_observe_after = raw_step_observe_after or default_observe_after
            if family == "control" and raw_step_observe_after is None:
                step_observe_after = None
            step_observe_payload = dict(default_observe_payload)
            step_observe_payload.update(_coerce_payload(raw_step.get("observe_payload")))
            post_state_result = await asyncio.to_thread(
                _run_mobile_script_observe_after,
                facade=facade,
                serializer=serializer,
                device_name=current_device_name,
                mode=step_observe_after,
                payload=step_observe_payload,
                timeout_ms=_normalize_timeout(raw_step.get("timeout_ms")),
            )
            if post_state_result is not None:
                latest_observed_result = post_state_result
            step_summaries.append(
                _mobile_script_step_summary(
                    index=index,
                    family=family,
                    kind=kind,
                    result=serialized,
                )
            )
            step_summaries[-1]["stabilize"] = _resolve_mobile_script_stabilize(
                step_stabilize,
            ) or "none"
            step_summaries[-1]["observe_after"] = (
                _resolve_mobile_script_observe_mode(step_observe_after) or "none"
            )
            if stabilize_result is not None:
                step_summaries[-1]["stabilize_result"] = _mobile_script_step_summary(
                    index=index,
                    family="action",
                    kind="wait",
                    result=stabilize_result,
                )
            if post_state_result is not None:
                step_summaries[-1]["post_state"] = _mobile_script_step_summary(
                    index=index,
                    family="action",
                    kind="snapshot",
                    result=post_state_result,
                )
            last_result = serialized
            last_kind = kind

        if not step_summaries:
            raise MobileValidationError("mobile script completed without any successful steps.")

        post_state_result: dict[str, Any] | None = None
        if final_observe:
            observe_request = MobileActionRequest(
                device_name=current_device_name,
                kind="snapshot",
                payload=dict(final_observe),
                timeout_ms=_normalize_timeout(arguments.get("timeout_ms")),
            )
            post_state_result = serializer.serialize(
                await asyncio.to_thread(facade.execute, observe_request)
            )

        return _tool_result(
            tool_id="mobile_script",
            kind="script",
            device_name=current_device_name,
            execution_context=execution_context,
            content=_mobile_script_content(
                step_summaries=step_summaries,
                post_state_result=post_state_result or latest_observed_result,
                last_result=last_result,
                last_kind=last_kind,
            ),
            details={
                "steps": step_summaries,
                "stop_on_error": stop_on_error,
                "default_stabilize": _resolve_mobile_script_stabilize(default_stabilize)
                or "none",
                "default_observe_after": (
                    _resolve_mobile_script_observe_mode(default_observe_after) or "none"
                ),
                "final_observe": _mobile_script_step_summary(
                    index=len(step_summaries) + 1,
                    family="action",
                    kind="snapshot",
                    result=post_state_result,
                )
                if post_state_result is not None
                else None,
            },
        )

    return _handler
