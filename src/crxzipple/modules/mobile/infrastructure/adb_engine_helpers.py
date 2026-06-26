from __future__ import annotations

import re
import time
from xml.etree import ElementTree as ET

from crxzipple.modules.mobile.domain import (
    MobileExecutionError,
    MobileExecutionPlan,
    MobileValidationError,
)

from .adb_client import AndroidAdbClient
from .ui_node_resolution import (
    ResolvedNode,
    matches_target,
    resolved_nodes_from_source,
)

ANDROID_KEYCODES = {
    "TAB": 61,
    "ENTER": 66,
    "BACK": 4,
    "HOME": 3,
    "DEL": 67,
    "A": 29,
    "CTRL_LEFT": 113,
}
WAIT_POLL_SECONDS = 0.5
SWIPE_DIRECTIONS = frozenset({"up", "down", "left", "right"})

_REF_PATTERN = re.compile(r"^g(?P<generation>\d+)-m(?P<index>\d+)$")


def adb_timeout_seconds(timeout_ms: int | None) -> float:
    if timeout_ms is None:
        return 30.0
    return max(timeout_ms / 1000.0, 1.0)


def require_device_serial(plan: MobileExecutionPlan) -> str:
    if plan.device is None:
        raise MobileExecutionError("Resolved mobile device is required.")
    serial = (plan.device.udid or plan.device.name).strip()
    if not serial:
        raise MobileExecutionError("Resolved mobile device does not include an adb serial.")
    return serial


def make_client(plan: MobileExecutionPlan, *, timeout_ms: int | None) -> AndroidAdbClient:
    serial = require_device_serial(plan)
    return AndroidAdbClient(
        adb_binary=plan.system.adb_binary,
        device_serial=serial,
        timeout_seconds=adb_timeout_seconds(timeout_ms),
    )


def coerce_int(value: object, *, label: str) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise MobileValidationError(f"{label} must be an integer.") from exc


def swipe_points_for_direction(
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


def verify_typed_text(
    *,
    client: AndroidAdbClient,
    target: ResolvedNode,
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
            for candidate in resolved_nodes_from_source(source):
                if not matches_target(candidate, target):
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


def wait_for_input_ready(
    *,
    client: AndroidAdbClient,
    target: ResolvedNode,
) -> None:
    if not client.wait_for_input_connection(
        expected_resource_id=target.resource_id,
        timeout_seconds=0.8,
    ):
        time.sleep(0.2)


def clear_and_type_text(
    *,
    client: AndroidAdbClient,
    target: ResolvedNode,
    text: str,
    clear: bool,
) -> None:
    if clear:
        existing_text = (target.text or "").strip()
        if existing_text:
            try:
                client.press_key_combination(
                    keycodes=(
                        ANDROID_KEYCODES["CTRL_LEFT"],
                        ANDROID_KEYCODES["A"],
                    ),
                )
                time.sleep(0.1)
                client.press_keycode(keycode=ANDROID_KEYCODES["DEL"])
            except MobileExecutionError:
                for _ in existing_text:
                    client.press_keycode(keycode=ANDROID_KEYCODES["DEL"])
    client.input_text(text)


def ref_generation(ref: str) -> int:
    match = _REF_PATTERN.fullmatch(ref.strip().lower())
    if match is None:
        raise MobileValidationError(
            f"Mobile ref '{ref}' is invalid. Capture a new snapshot and use the returned ref.",
        )
    return max(int(match.group("generation")), 1)


__all__ = [
    "ANDROID_KEYCODES",
    "SWIPE_DIRECTIONS",
    "WAIT_POLL_SECONDS",
    "adb_timeout_seconds",
    "clear_and_type_text",
    "coerce_int",
    "make_client",
    "ref_generation",
    "require_device_serial",
    "swipe_points_for_direction",
    "verify_typed_text",
    "wait_for_input_ready",
]
