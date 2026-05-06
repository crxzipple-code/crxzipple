from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Any
from xml.etree import ElementTree as ET

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
from crxzipple.modules.ocr.domain import OcrPoint, OcrResult

from .adb_client import AndroidAdbClient
from .vision_layout import VisionLayoutCandidate, detect_visual_layout_candidates

_ANDROID_KEYCODES = {
    "TAB": 61,
    "ENTER": 66,
    "BACK": 4,
    "HOME": 3,
    "DEL": 67,
    "A": 29,
    "CTRL_LEFT": 113,
}
_BOUNDS_PATTERN = re.compile(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]")
_REF_PATTERN = re.compile(r"^g(?P<generation>\d+)-m(?P<index>\d+)$")
_WAIT_POLL_SECONDS = 0.5
_SWIPE_DIRECTIONS = frozenset({"up", "down", "left", "right"})


@dataclass(frozen=True, slots=True)
class _ResolvedNode:
    text: str | None
    content_desc: str | None
    resource_id: str | None
    class_name: str | None
    xpath: str | None
    bounds: tuple[int, int, int, int] | None
    clickable: bool
    focusable: bool
    focused: bool
    enabled: bool


def _adb_timeout_seconds(timeout_ms: int | None) -> float:
    if timeout_ms is None:
        return 30.0
    return max(timeout_ms / 1000.0, 1.0)


def _require_device_serial(plan: MobileExecutionPlan) -> str:
    if plan.device is None:
        raise MobileExecutionError("Resolved mobile device is required.")
    serial = (plan.device.udid or plan.device.name).strip()
    if not serial:
        raise MobileExecutionError("Resolved mobile device does not include an adb serial.")
    return serial


def _make_client(plan: MobileExecutionPlan, *, timeout_ms: int | None) -> AndroidAdbClient:
    serial = _require_device_serial(plan)
    return AndroidAdbClient(
        adb_binary=plan.system.adb_binary,
        device_serial=serial,
        timeout_seconds=_adb_timeout_seconds(timeout_ms),
    )


def _parse_selector(selector: str) -> tuple[str, str]:
    normalized = selector.strip()
    if normalized.startswith("xpath="):
        return "xpath", normalized[6:]
    if normalized.startswith("id="):
        return "id", normalized[3:]
    if normalized.startswith("accessibility_id="):
        return "accessibility id", normalized[len("accessibility_id=") :]
    if normalized.startswith("text="):
        return "text", normalized[5:]
    if normalized.startswith("//"):
        return "xpath", normalized
    return "xpath", normalized


def _parse_bounds(raw: str | None) -> tuple[int, int, int, int] | None:
    if not raw:
        return None
    match = _BOUNDS_PATTERN.fullmatch(raw.strip())
    if match is None:
        return None
    left, top, right, bottom = (int(part) for part in match.groups())
    return left, top, right, bottom


def _bounds_center(bounds: tuple[int, int, int, int]) -> tuple[int, int]:
    left, top, right, bottom = bounds
    return ((left + right) // 2, (top + bottom) // 2)


def _coerce_int(value: object, *, label: str) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise MobileValidationError(f"{label} must be an integer.") from exc


def _swipe_points_for_direction(
    *,
    bounds: tuple[int, int, int, int],
    direction: str,
) -> tuple[int, int, int, int]:
    left, top, right, bottom = bounds
    width = max(right - left, 1)
    height = max(bottom - top, 1)
    x_mid = left + width // 2
    y_mid = top + height // 2
    horizontal_margin = max(int(width * 0.2), 1)
    vertical_margin = max(int(height * 0.2), 1)
    if direction == "up":
        return (x_mid, bottom - vertical_margin, x_mid, top + vertical_margin)
    if direction == "down":
        return (x_mid, top + vertical_margin, x_mid, bottom - vertical_margin)
    if direction == "left":
        return (right - horizontal_margin, y_mid, left + horizontal_margin, y_mid)
    return (left + horizontal_margin, y_mid, right - horizontal_margin, y_mid)


def _is_truthy(value: str | None) -> bool:
    return (value or "").strip().lower() == "true"


def _label_for_node(node: ET.Element) -> str:
    for key in ("text", "content-desc", "resource-id"):
        raw = (node.attrib.get(key) or "").strip()
        if raw:
            return raw
    class_name = (node.attrib.get("class") or node.tag or "").strip()
    return class_name or "node"


def _is_interactive_node(node: ET.Element) -> bool:
    class_name = (node.attrib.get("class") or "").strip()
    return (
        _is_truthy(node.attrib.get("clickable"))
        or _is_truthy(node.attrib.get("focusable"))
        or class_name.endswith("EditText")
        or class_name.endswith("Button")
        or class_name.endswith("CheckBox")
        or class_name.endswith("Switch")
    )


def _iter_nodes(root: ET.Element) -> tuple[tuple[ET.Element, str], ...]:
    items: list[tuple[ET.Element, str]] = []

    def walk(node: ET.Element, xpath: str) -> None:
        items.append((node, xpath))
        sibling_counts: dict[str, int] = {}
        for child in list(node):
            child_tag = child.tag
            sibling_counts[child_tag] = sibling_counts.get(child_tag, 0) + 1
            child_xpath = f"{xpath}/{child_tag}[{sibling_counts[child_tag]}]"
            walk(child, child_xpath)

    walk(root, f"/{root.tag}[1]")
    return tuple(items)


def _resolved_node(node: ET.Element, xpath: str) -> _ResolvedNode:
    class_name = (node.attrib.get("class") or node.tag or "").strip() or None
    return _ResolvedNode(
        text=(node.attrib.get("text") or None),
        content_desc=(node.attrib.get("content-desc") or None),
        resource_id=(node.attrib.get("resource-id") or None),
        class_name=class_name,
        xpath=xpath,
        bounds=_parse_bounds(node.attrib.get("bounds")),
        clickable=_is_truthy(node.attrib.get("clickable")),
        focusable=_is_truthy(node.attrib.get("focusable")),
        focused=_is_truthy(node.attrib.get("focused")),
        enabled=not ((node.attrib.get("enabled") or "").strip().lower() == "false"),
    )


def _coerce_xpath_selector(value: str) -> str:
    selector = value.strip()
    if selector.startswith("//"):
        return f".{selector}"
    return selector


def _find_nodes_by_selector(source: str, selector: str) -> tuple[_ResolvedNode, ...]:
    root = ET.fromstring(source)
    items = _iter_nodes(root)
    using, value = _parse_selector(selector)
    if using == "id":
        return tuple(
            _resolved_node(node, xpath)
            for node, xpath in items
            if (node.attrib.get("resource-id") or "").strip() == value
        )
    if using == "accessibility id":
        return tuple(
            _resolved_node(node, xpath)
            for node, xpath in items
            if (node.attrib.get("content-desc") or "").strip() == value
        )
    if using == "text":
        return tuple(
            _resolved_node(node, xpath)
            for node, xpath in items
            if (node.attrib.get("text") or "").strip() == value
        )
    if using == "xpath":
        try:
            matched = root.findall(_coerce_xpath_selector(value))
        except SyntaxError as exc:
            raise MobileValidationError(f"Unsupported xpath selector '{selector}'.") from exc
        xpath_lookup = {id(node): xpath for node, xpath in items}
        return tuple(
            _resolved_node(node, xpath_lookup.get(id(node), ""))
            for node in matched
            if isinstance(node, ET.Element)
        )
    raise MobileValidationError(f"Unsupported mobile selector strategy '{using}'.")


def _resolved_nodes_from_source(source: str) -> tuple[_ResolvedNode, ...]:
    root = ET.fromstring(source)
    return tuple(_resolved_node(node, xpath) for node, xpath in _iter_nodes(root))


def _matches_target(candidate: _ResolvedNode, target: _ResolvedNode) -> bool:
    if target.resource_id and candidate.resource_id == target.resource_id:
        return True
    if target.xpath and candidate.xpath == target.xpath:
        return True
    if (
        target.bounds is not None
        and candidate.bounds == target.bounds
        and target.class_name
        and candidate.class_name == target.class_name
    ):
        return True
    return False


def _verify_typed_text(
    *,
    client: AndroidAdbClient,
    target: _ResolvedNode,
    expected_text: str,
    timeout_seconds: float = 0.8,
    poll_seconds: float = 0.1,
) -> bool:
    expected = expected_text.strip()
    if not expected:
        return True
    deadline = time.monotonic() + max(float(timeout_seconds), 0.0)
    while True:
        try:
            source = client.dump_ui_xml()
            for candidate in _resolved_nodes_from_source(source):
                if not _matches_target(candidate, target):
                    continue
                candidate_text = (candidate.text or "").strip()
                if candidate_text == expected or expected in candidate_text:
                    return True
        except (MobileExecutionError, ET.ParseError, MobileValidationError):
            pass
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return False
        time.sleep(min(max(poll_seconds, 0.01), remaining))


def _wait_for_input_ready(
    *,
    client: AndroidAdbClient,
    target: _ResolvedNode,
) -> None:
    if not client.wait_for_input_connection(
        expected_resource_id=target.resource_id,
        timeout_seconds=0.8,
    ):
        time.sleep(0.2)


def _clear_and_type_text(
    *,
    client: AndroidAdbClient,
    target: _ResolvedNode,
    text: str,
    clear: bool,
) -> None:
    if clear:
        existing_text = (target.text or "").strip()
        if existing_text:
            try:
                client.press_key_combination(
                    keycodes=(
                        _ANDROID_KEYCODES["CTRL_LEFT"],
                        _ANDROID_KEYCODES["A"],
                    ),
                )
                time.sleep(0.1)
                client.press_keycode(keycode=_ANDROID_KEYCODES["DEL"])
            except MobileExecutionError:
                for _ in existing_text:
                    client.press_keycode(keycode=_ANDROID_KEYCODES["DEL"])
    client.input_text(text)


def _snapshot_from_source(
    *,
    source: str,
    generation: int,
) -> tuple[str, tuple[MobileStoredRef, ...], str, int]:
    root = ET.fromstring(source)
    lines: list[str] = []
    refs: list[MobileStoredRef] = []
    text_lines: list[str] = []
    node_count = 0

    def walk(node: ET.Element, depth: int, xpath: str) -> None:
        nonlocal node_count
        node_count += 1
        label = _label_for_node(node)
        class_name = (node.attrib.get("class") or node.tag or "").strip()
        bounds = _parse_bounds(node.attrib.get("bounds"))
        interactive = _is_interactive_node(node)
        ref_label: str | None = None
        if interactive:
            ref_label = f"g{generation}-m{len(refs) + 1}"
            refs.append(
                MobileStoredRef(
                    ref=ref_label,
                    generation=generation,
                    source="ui_tree",
                    text=node.attrib.get("text"),
                    content_desc=node.attrib.get("content-desc"),
                    resource_id=node.attrib.get("resource-id"),
                    class_name=class_name,
                    xpath=xpath,
                    bounds=bounds,
                    clickable=_is_truthy(node.attrib.get("clickable")),
                    focusable=_is_truthy(node.attrib.get("focusable")),
                    focused=_is_truthy(node.attrib.get("focused")),
                    enabled=not ((node.attrib.get("enabled") or "").strip().lower() == "false"),
                )
            )
        suffix = f" [ref={ref_label}]" if ref_label is not None else ""
        lines.append(f"{'  ' * depth}- {class_name or 'node'} \"{label}\"{suffix}")
        label_text = label.strip()
        if label_text and label_text not in text_lines:
            text_lines.append(label_text)
        sibling_counts: dict[str, int] = {}
        for child in list(node):
            child_tag = child.tag
            sibling_counts[child_tag] = sibling_counts.get(child_tag, 0) + 1
            child_xpath = f"{xpath}/{child_tag}[{sibling_counts[child_tag]}]"
            walk(child, depth + 1, child_xpath)

    walk(root, 0, f"/{root.tag}[1]")
    return "\n".join(lines), tuple(refs), "\n".join(text_lines[:200]), node_count


def _meaningful_snapshot_lines(text_excerpt: str) -> tuple[str, ...]:
    meaningful: list[str] = []
    for raw_line in text_excerpt.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        lowered = line.lower()
        if lowered in {"hierarchy", "node"}:
            continue
        if lowered.startswith("android.widget.") or lowered.startswith("android.view."):
            continue
        if ":id/" in lowered:
            continue
        meaningful.append(line)
    return tuple(meaningful)


def _ui_tree_looks_low_quality(
    *,
    refs: tuple[MobileStoredRef, ...],
    text_excerpt: str,
    node_count: int,
    current_package: str | None,
) -> bool:
    if refs:
        return False
    meaningful_lines = _meaningful_snapshot_lines(text_excerpt)
    if node_count <= 3:
        return True
    if not meaningful_lines:
        return True
    if (current_package or "").startswith("com.tencent.mm") and len(meaningful_lines) <= 2:
        return True
    return False


def _bounds_from_ocr_polygon(
    polygon: tuple[OcrPoint, ...],
) -> tuple[int, int, int, int] | None:
    if not polygon:
        return None
    xs = [int(round(point.x)) for point in polygon]
    ys = [int(round(point.y)) for point in polygon]
    if not xs or not ys:
        return None
    left = min(xs)
    right = max(xs)
    top = min(ys)
    bottom = max(ys)
    if right <= left or bottom <= top:
        return None
    return (left, top, right, bottom)


def _group_ocr_rows(
    blocks: tuple[tuple[str, tuple[int, int, int, int] | None], ...],
) -> tuple[tuple[tuple[str, tuple[int, int, int, int] | None], ...], ...]:
    if not blocks:
        return ()
    heights = [
        bounds[3] - bounds[1]
        for _, bounds in blocks
        if bounds is not None and bounds[3] > bounds[1]
    ]
    threshold = 40
    if heights:
        sorted_heights = sorted(heights)
        median_height = sorted_heights[len(sorted_heights) // 2]
        threshold = max(24, int(median_height * 0.8))
    rows: list[list[tuple[str, tuple[int, int, int, int] | None]]] = []
    row_tops: list[int] = []
    for item in blocks:
        _, bounds = item
        top = bounds[1] if bounds is not None else (row_tops[-1] if row_tops else 0)
        if rows and abs(top - row_tops[-1]) <= threshold:
            rows[-1].append(item)
            row_tops[-1] = min(row_tops[-1], top)
            continue
        rows.append([item])
        row_tops.append(top)
    normalized_rows: list[tuple[tuple[str, tuple[int, int, int, int] | None], ...]] = []
    for row in rows:
        normalized_rows.append(
            tuple(
                sorted(
                    row,
                    key=lambda item: item[1][0] if item[1] is not None else 0,
                )
            )
        )
    return tuple(normalized_rows)


def _snapshot_from_ocr_result(
    *,
    result: OcrResult,
    generation: int,
    vision_candidates: tuple[VisionLayoutCandidate, ...] = (),
) -> tuple[str, tuple[MobileStoredRef, ...], str, int]:
    ordered_blocks = tuple(
        sorted(
            (
                (
                    block.text.strip(),
                    _bounds_from_ocr_polygon(block.polygon),
                    block.confidence,
                )
                for block in result.blocks
                if block.text.strip()
            ),
            key=lambda item: (
                item[1][1] if item[1] is not None else 0,
                item[1][0] if item[1] is not None else 0,
            ),
        )
    )
    rows = _group_ocr_rows(tuple((text, bounds) for text, bounds, _ in ordered_blocks))
    refs: list[MobileStoredRef] = []
    lines = ["- ocr.page"]
    text_lines: list[str] = []
    for row_index, row in enumerate(rows, start=1):
        lines.append(f"  - ocr.row #{row_index}")
        for text, bounds in row:
            ref_label: str | None = None
            if bounds is not None:
                ref_label = f"g{generation}-m{len(refs) + 1}"
                refs.append(
                    MobileStoredRef(
                        ref=ref_label,
                        generation=generation,
                        source="ocr",
                        text=text,
                        class_name="ocr.block",
                        bounds=bounds,
                        clickable=True,
                        focusable=False,
                        focused=False,
                        enabled=True,
                    )
                )
            suffix = f" [ref={ref_label}]" if ref_label is not None else ""
            lines.append(f'    - ocr.block "{text}"{suffix}')
            if text not in text_lines:
                text_lines.append(text)
    vision_rows = _group_ocr_rows(
        tuple(
            (
                (candidate.label or candidate.kind).strip(),
                candidate.bounds,
            )
            for candidate in vision_candidates
        )
    )
    if vision_rows:
        lines.append("  - vision.layout")
    for row_index, row in enumerate(vision_rows, start=1):
        lines.append(f"    - vision.row #{row_index}")
        for label, bounds in row:
            matched_candidate = next(
                (
                    candidate
                    for candidate in vision_candidates
                    if candidate.bounds == bounds and (candidate.label or candidate.kind).strip() == label
                ),
                None,
            )
            if matched_candidate is None:
                continue
            ref_label = f"g{generation}-m{len(refs) + 1}"
            refs.append(
                MobileStoredRef(
                    ref=ref_label,
                    generation=generation,
                    source="vision",
                    text=matched_candidate.label,
                    class_name=matched_candidate.kind,
                    bounds=matched_candidate.bounds,
                    clickable=True,
                    focusable=matched_candidate.kind == "vision.input",
                    focused=False,
                    enabled=True,
                )
            )
            lines.append(
                f'      - {matched_candidate.kind} "{(matched_candidate.label or matched_candidate.kind)}" [ref={ref_label}]'
            )
            label_text = (matched_candidate.label or "").strip()
            if label_text and label_text not in text_lines:
                text_lines.append(label_text)
    node_count = 1 + len(rows) + len(ordered_blocks) + (1 if vision_rows else 0) + len(vision_rows) + len(vision_candidates)
    return "\n".join(lines), tuple(refs), "\n".join(text_lines[:200]), node_count


def _ref_generation(ref: str) -> int:
    match = _REF_PATTERN.fullmatch(ref.strip().lower())
    if match is None:
        raise MobileValidationError(
            f"Mobile ref '{ref}' is invalid. Capture a new snapshot and use the returned ref.",
        )
    return max(int(match.group("generation")), 1)


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
