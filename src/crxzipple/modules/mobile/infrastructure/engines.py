from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from crxzipple.modules.artifacts.application.services import ArtifactApplicationService
from crxzipple.modules.artifacts.domain.entities import ArtifactVariant
from crxzipple.modules.mobile.application.ports import MobileActionEngine, MobileControlEngine, MobileRefStore
from crxzipple.modules.mobile.domain import (
    MobileActionCommand,
    MobileActionResult,
    MobileControlCommand,
    MobileDeviceRuntimeState,
    MobileExecutionError,
    MobileExecutionPlan,
    MobileStoredRef,
    MobileValidationError,
)
from crxzipple.modules.ocr.application.services import OcrApplicationService

from .adb_client import AndroidAdbClient
from .adb_engine_helpers import (
    ANDROID_KEYCODES as _ANDROID_KEYCODES,
    SWIPE_DIRECTIONS as _SWIPE_DIRECTIONS,
    WAIT_POLL_SECONDS as _WAIT_POLL_SECONDS,
    clear_and_type_text as _clear_and_type_text,
    coerce_int as _coerce_int,
    make_client as _make_client,
    ref_generation as _ref_generation,
    swipe_points_for_direction as _swipe_points_for_direction,
    verify_typed_text as _verify_typed_text,
    wait_for_input_ready as _wait_for_input_ready,
)
from .snapshot_builders import (
    snapshot_from_ocr_result as _snapshot_from_ocr_result,
    snapshot_from_source as _snapshot_from_source,
    ui_tree_looks_low_quality as _ui_tree_looks_low_quality,
)
from .ui_node_resolution import (
    ResolvedNode as _ResolvedNode,
    bounds_center as _bounds_center,
    find_nodes_by_selector as _find_nodes_by_selector,
)
from .vision_layout import detect_visual_layout_candidates


@dataclass(frozen=True, slots=True)
class AdbControlEngine(MobileControlEngine):
    family: str = "adb-control"

    def execute(
        self,
        *,
        plan: MobileExecutionPlan,
        runtime_state: MobileDeviceRuntimeState | None,
    ) -> tuple[MobileActionResult, MobileDeviceRuntimeState | None]:
        command = plan.command
        if not isinstance(command, MobileControlCommand):
            raise MobileExecutionError("Invalid mobile control command.")
        if command.kind == "list-devices":
            probe = AndroidAdbClient.probe_adb_devices(adb_binary=plan.system.adb_binary)
            adb_available = bool(probe.get("adb_available"))
            probe_ok = bool(probe.get("probe_ok"))
            connected = bool(probe.get("connected"))
            connected_count = int(probe.get("connected_device_count") or 0)
            device_count = int(probe.get("device_count") or 0)
            adb_error = str(probe.get("adb_error") or "").strip() or None
            if not adb_available:
                message = "Unable to inspect Android devices because adb is not available."
            elif not probe_ok:
                message = "Unable to inspect Android devices because adb probing failed."
            elif connected:
                message = f"Detected {connected_count} connected Android device(s)."
            elif device_count > 0:
                message = "Android devices were detected, but none are currently online."
            else:
                message = "No Android devices are currently connected."
            return (
                MobileActionResult(
                    ok=True,
                    device_name=None,
                    message=message,
                    command=command,
                    value={
                        "adb_binary": plan.system.adb_binary,
                        "adb_available": adb_available,
                        "probe_ok": probe_ok,
                        "adb_error": adb_error,
                        "connected": connected,
                        "device_count": device_count,
                        "connected_device_count": connected_count,
                        "devices": probe.get("devices", []),
                    },
                ),
                None,
            )

        if plan.device is None:
            raise MobileValidationError("Resolved mobile device is required for this control command.")

        state = runtime_state or MobileDeviceRuntimeState(device_name=plan.device.name)
        client = _make_client(plan, timeout_ms=command.timeout_ms)
        try:
            if command.kind == "launch-app":
                app_package = str(command.payload.get("app_package") or plan.device.app_package or "").strip()
                app_activity = str(command.payload.get("app_activity") or plan.device.app_activity or "").strip()
                if not app_package or not app_activity:
                    raise MobileValidationError("launch-app requires app_package and app_activity.")
                client.start_activity(app_package=app_package, app_activity=app_activity)
                state.clear_error()
                return (
                    MobileActionResult(
                        ok=True,
                        device_name=plan.device.name,
                        message="Launched Android app activity.",
                        command=command,
                        value={"app_package": app_package, "app_activity": app_activity},
                    ),
                    state,
                )
            if command.kind == "activate-app":
                app_id = str(command.payload.get("app_id") or plan.device.app_package or "").strip()
                app_activity = str(command.payload.get("app_activity") or plan.device.app_activity or "").strip() or None
                if not app_id:
                    raise MobileValidationError("activate-app requires app_id or configured app_package.")
                client.activate_app(app_id=app_id, app_activity=app_activity)
                state.clear_error()
                return (
                    MobileActionResult(
                        ok=True,
                        device_name=plan.device.name,
                        message="Activated Android app.",
                        command=command,
                        value={"app_id": app_id, "app_activity": app_activity},
                    ),
                    state,
                )
            if command.kind == "terminate-app":
                app_id = str(command.payload.get("app_id") or plan.device.app_package or "").strip()
                if not app_id:
                    raise MobileValidationError("terminate-app requires app_id or configured app_package.")
                client.terminate_app(app_id=app_id)
                state.clear_error()
                return (
                    MobileActionResult(
                        ok=True,
                        device_name=plan.device.name,
                        message="Terminated Android app.",
                        command=command,
                        value={"app_id": app_id},
                    ),
                    state,
                )
        except MobileExecutionError as exc:
            state.mark_command_failed(str(exc))
            raise

        raise MobileValidationError(f"Unsupported mobile control kind '{command.kind}'.")


@dataclass(frozen=True, slots=True)
class AdbBackedMobileActionEngine(MobileActionEngine):
    ref_store: MobileRefStore
    artifact_service: ArtifactApplicationService | None = None
    ocr_service: OcrApplicationService | None = None
    family: str = "adb-backed"

    def _capture_ocr_snapshot(
        self,
        *,
        plan: MobileExecutionPlan,
        client: AndroidAdbClient,
        generation: int,
    ) -> tuple[str, tuple[MobileStoredRef, ...], str, int, str, dict[str, str | None]]:
        if self.artifact_service is None or self.ocr_service is None:
            raise MobileExecutionError("OCR fallback is unavailable because OCR services are not configured.")
        image_bytes = client.take_screenshot()
        artifact = self.artifact_service.create_artifact(
            data=image_bytes,
            mime_type="image/png",
            name=f"{plan.device.name}-ocr-fallback.png",
        )
        ocr_result = self.ocr_service.analyze_artifact(
            artifact_id=artifact.id,
            variant=ArtifactVariant.ORIGINAL,
        )
        vision_candidates = detect_visual_layout_candidates(
            image_bytes=image_bytes,
            ocr_result=ocr_result,
        )
        focus = client.current_focus()
        tree_text, refs, text_excerpt, node_count = _snapshot_from_ocr_result(
            result=ocr_result,
            generation=generation,
            vision_candidates=vision_candidates,
        )
        return tree_text, refs, text_excerpt, node_count, artifact.id, focus

    def execute(
        self,
        *,
        plan: MobileExecutionPlan,
        runtime_state: MobileDeviceRuntimeState,
    ) -> tuple[MobileActionResult, MobileDeviceRuntimeState]:
        command = plan.command
        if not isinstance(command, MobileActionCommand):
            raise MobileExecutionError("Invalid mobile action command.")
        if plan.device is None:
            raise MobileExecutionError("Resolved mobile device is required for mobile actions.")
        client = _make_client(plan, timeout_ms=command.timeout_ms)
        try:
            if command.kind == "snapshot":
                return self._snapshot(plan=plan, command=command, runtime_state=runtime_state, client=client)
            if command.kind == "screenshot":
                return self._screenshot(plan=plan, command=command, runtime_state=runtime_state, client=client)
            if command.kind == "tap":
                return self._tap(plan=plan, command=command, runtime_state=runtime_state, client=client)
            if command.kind == "swipe":
                return self._swipe(plan=plan, command=command, runtime_state=runtime_state, client=client)
            if command.kind == "type":
                return self._type(plan=plan, command=command, runtime_state=runtime_state, client=client)
            if command.kind == "press":
                return self._press(plan=plan, command=command, runtime_state=runtime_state, client=client)
            if command.kind == "wait":
                return self._wait(plan=plan, command=command, runtime_state=runtime_state, client=client)
        except MobileExecutionError as exc:
            runtime_state.mark_command_failed(str(exc))
            raise
        raise MobileValidationError(f"Unsupported mobile action kind '{command.kind}'.")

    def _snapshot(
        self,
        *,
        plan: MobileExecutionPlan,
        command: MobileActionCommand,
        runtime_state: MobileDeviceRuntimeState,
        client: AndroidAdbClient,
    ) -> tuple[MobileActionResult, MobileDeviceRuntimeState]:
        generation = runtime_state.next_ref_generation()
        previous_generation = runtime_state.current_ref_generation
        source_length: int | None = None
        mitigations_applied: tuple[str, ...] = ()
        observation_mode = "ui_tree"
        ocr_artifact_id: str | None = None
        low_quality_ui_tree = False
        try:
            capture = client.capture_ui_xml()
            source = capture.xml
            focus = {
                "package": capture.current_package,
                "activity": capture.current_activity,
            }
            tree_text, refs, text_excerpt, node_count = _snapshot_from_source(
                source=source,
                generation=generation,
            )
            source_length = len(source)
            mitigations_applied = capture.mitigations_applied
            if (
                self.artifact_service is not None
                and self.ocr_service is not None
                and _ui_tree_looks_low_quality(
                    refs=refs,
                    text_excerpt=text_excerpt,
                    node_count=node_count,
                    current_package=capture.current_package,
                )
            ):
                try:
                    (
                        tree_text,
                        refs,
                        text_excerpt,
                        node_count,
                        ocr_artifact_id,
                        focus,
                    ) = self._capture_ocr_snapshot(
                        plan=plan,
                        client=client,
                        generation=generation,
                    )
                    observation_mode = "ocr"
                    low_quality_ui_tree = True
                except MobileExecutionError as ocr_error:
                    runtime_state.metadata["last_snapshot_fallback_error"] = str(ocr_error)
        except MobileExecutionError as xml_error:
            (
                tree_text,
                refs,
                text_excerpt,
                node_count,
                ocr_artifact_id,
                focus,
            ) = self._capture_ocr_snapshot(
                plan=plan,
                client=client,
                generation=generation,
            )
            observation_mode = "ocr"
            mitigations_applied = ()
            source_length = None
            runtime_state.metadata["last_snapshot_fallback_error"] = str(xml_error)
        if low_quality_ui_tree:
            runtime_state.metadata["last_snapshot_fallback_error"] = "low_quality_ui_tree"
        if previous_generation is not None and previous_generation != generation:
            self.ref_store.delete_refs(
                device_name=plan.device.name,
                generation=previous_generation,
            )
        self.ref_store.save_refs(
            device_name=plan.device.name,
            generation=generation,
            refs=refs,
        )
        format_name = str(command.payload.get("format") or "interactive_text").strip().lower()
        runtime_state.remember_snapshot(
            generation=generation,
            ref_count=len(refs),
            snapshot_format=format_name,
            package_name=(focus.get("package") or None),
            activity_name=(focus.get("activity") or None),
            source_length=source_length,
        )
        if format_name == "text":
            snapshot_body = text_excerpt
        elif format_name == "interactive_text":
            snapshot_body = f"{tree_text}\n\nText:\n{text_excerpt}".strip()
        else:
            snapshot_body = tree_text
        return (
            MobileActionResult(
                ok=True,
                device_name=plan.device.name,
                message="Captured mobile UI snapshot.",
                command=command,
                value={
                    "format": format_name,
                    "snapshot": snapshot_body,
                    "text": text_excerpt,
                    "source_length": source_length,
                    "observation_mode": observation_mode,
                    "node_count": node_count,
                    "refs": refs,
                    "ref_count": len(refs),
                    "generation": generation,
                    "current_package": focus.get("package"),
                    "current_activity": focus.get("activity"),
                    "mitigations_applied": mitigations_applied,
                    "ocr_artifact_id": ocr_artifact_id,
                    "ref_source_counts": {
                        "ui_tree": sum(1 for ref in refs if ref.source == "ui_tree"),
                        "ocr": sum(1 for ref in refs if ref.source == "ocr"),
                        "vision": sum(1 for ref in refs if ref.source == "vision"),
                    },
                },
            ),
            runtime_state,
        )

    def _screenshot(
        self,
        *,
        plan: MobileExecutionPlan,
        command: MobileActionCommand,
        runtime_state: MobileDeviceRuntimeState,
        client: AndroidAdbClient,
    ) -> tuple[MobileActionResult, MobileDeviceRuntimeState]:
        image_bytes = client.take_screenshot()
        runtime_state.clear_error()
        if self.artifact_service is not None:
            artifact = self.artifact_service.create_artifact(
                data=image_bytes,
                mime_type="image/png",
                name=f"{plan.device.name}-screenshot.png",
            )
            value: dict[str, Any] = {
                "artifact_id": artifact.id,
                "mime_type": artifact.mime_type,
                "name": artifact.name,
                "width": artifact.width,
                "height": artifact.height,
            }
        else:
            value = {
                "mime_type": "image/png",
                "bytes": len(image_bytes),
            }
        return (
            MobileActionResult(
                ok=True,
                device_name=plan.device.name,
                message="Captured mobile screenshot.",
                command=command,
                value=value,
            ),
            runtime_state,
        )

    def _tap(
        self,
        *,
        plan: MobileExecutionPlan,
        command: MobileActionCommand,
        runtime_state: MobileDeviceRuntimeState,
        client: AndroidAdbClient,
    ) -> tuple[MobileActionResult, MobileDeviceRuntimeState]:
        target = self._resolve_target_node(
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

    def _type(
        self,
        *,
        plan: MobileExecutionPlan,
        command: MobileActionCommand,
        runtime_state: MobileDeviceRuntimeState,
        client: AndroidAdbClient,
    ) -> tuple[MobileActionResult, MobileDeviceRuntimeState]:
        target = self._resolve_target_node(
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

    def _swipe(
        self,
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
                target = self._resolve_target_node(
                    plan=plan,
                    command=command,
                    runtime_state=runtime_state,
                    client=client,
                )
                if target.bounds is None:
                    raise MobileValidationError("Resolved mobile target does not include bounds for swipe.")
                bounds = target.bounds
            else:
                display_size = client.display_size()
                bounds = (0, 0, display_size.width, display_size.height)
            resolved_start_x, resolved_start_y, resolved_end_x, resolved_end_y = _swipe_points_for_direction(
                bounds=bounds,
                direction=direction,
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

    def _press(
        self,
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
            raise MobileValidationError("press requires payload.keycode or a supported payload.key.")
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

    def _wait(
        self,
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

    def _resolve_ref(
        self,
        *,
        device_name: str,
        runtime_state: MobileDeviceRuntimeState,
        ref: str,
    ) -> MobileStoredRef:
        generation = _ref_generation(ref)
        current_generation = runtime_state.current_ref_generation
        if current_generation is None:
            raise MobileValidationError("No mobile snapshot is available. Capture a new snapshot first.")
        if generation != current_generation:
            raise MobileValidationError(
                f"Mobile ref '{ref}' is stale. Capture a new snapshot before continuing.",
            )
        refs = self.ref_store.get_refs(device_name=device_name, generation=generation)
        normalized = ref.strip().lower()
        for item in refs:
            if item.ref == normalized:
                return item
        raise MobileValidationError(f"Mobile ref '{ref}' was not found.")

    def _resolve_target_node(
        self,
        *,
        plan: MobileExecutionPlan,
        command: MobileActionCommand,
        runtime_state: MobileDeviceRuntimeState,
        client: AndroidAdbClient,
    ) -> _ResolvedNode:
        if command.target.ref:
            ref = self._resolve_ref(
                device_name=plan.device.name,
                runtime_state=runtime_state,
                ref=command.target.ref,
            )
            return _ResolvedNode(
                text=ref.text,
                content_desc=ref.content_desc,
                resource_id=ref.resource_id,
                class_name=ref.class_name,
                xpath=ref.xpath,
                bounds=ref.bounds,
                clickable=ref.clickable,
                focusable=ref.focusable,
                focused=ref.focused,
                enabled=ref.enabled,
            )
        if command.target.selector:
            matches = _find_nodes_by_selector(client.dump_ui_xml(), command.target.selector)
            if not matches:
                raise MobileValidationError(
                    f"Mobile selector '{command.target.selector}' did not match any node.",
                )
            return matches[0]
        raise MobileValidationError(f"{command.kind} requires ref or selector.")
