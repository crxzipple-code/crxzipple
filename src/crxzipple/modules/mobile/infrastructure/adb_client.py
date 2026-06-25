from __future__ import annotations

import base64
import re
import subprocess
import time
from dataclasses import dataclass
from typing import Any

from crxzipple.modules.mobile.domain import MobileExecutionError

_FOCUS_PATTERNS = (
    re.compile(
        r"(?:mCurrentFocus|mFocusedApp|topResumedActivity).+? (?P<package>[A-Za-z0-9._]+)/(?P<activity>[A-Za-z0-9.$_]+)",
    ),
)
_WINDOW_FOCUS_LINE_PREFIX = "mCurrentFocus="
_WINDOW_FOCUSED_APP_LINE_PREFIX = "mFocusedApp="
_AUTOFILL_SERVICE_KEY = "autofill_service"
_ENABLED_ACCESSIBILITY_SERVICES_KEY = "enabled_accessibility_services"
_ACCESSIBILITY_ENABLED_KEY = "accessibility_enabled"
_DEFAULT_INPUT_METHOD_KEY = "default_input_method"
_KNOWN_ACCESSIBILITY_INTERFERERS = ("com.vivo.dr/.WXAssistService",)
_ADB_KEYBOARD_IME = "com.android.adbkeyboard/.AdbIME"
_INPUT_METHOD_SERVED_CONNECTION_LINE_PREFIX = "mServedInputConnection="
_MAX_ADB_ERROR_OUTPUT_CHARS = 2_000


def _command_output(exc: subprocess.CalledProcessError) -> str:
    raw = _coerce_subprocess_output(exc.stderr) or _coerce_subprocess_output(exc.stdout)
    return _truncate_adb_output(raw or str(exc)).strip()


def _coerce_subprocess_output(value: object) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, str):
        return value
    return ""


def _truncate_adb_output(value: str) -> str:
    if len(value) <= _MAX_ADB_ERROR_OUTPUT_CHARS:
        return value
    omitted = len(value) - _MAX_ADB_ERROR_OUTPUT_CHARS
    return f"{value[:_MAX_ADB_ERROR_OUTPUT_CHARS]}... [truncated {omitted} chars]"


def _extract_xml(raw: str) -> str:
    for marker in ("<?xml", "<hierarchy"):
        index = raw.find(marker)
        if index >= 0:
            return raw[index:].strip()
    raise MobileExecutionError(
        "adb uiautomator dump did not return XML output.",
    )


def _extract_focus(raw: str) -> dict[str, str | None]:
    for pattern in _FOCUS_PATTERNS:
        match = pattern.search(raw)
        if match is not None:
            return {
                "package": match.group("package").strip(),
                "activity": match.group("activity").strip(),
                "raw": raw,
            }
    return {"package": None, "activity": None, "raw": raw}


def _extract_last_line(raw: str, prefix: str) -> str | None:
    found: str | None = None
    for line in raw.splitlines():
        stripped = line.strip()
        if stripped.startswith(prefix):
            found = stripped
    return found


def _normalize_setting(value: str | None) -> str | None:
    normalized = (value or "").strip()
    if not normalized or normalized.lower() in {"null", "none"}:
        return None
    return normalized


def _root_package_from_xml(source: str) -> str | None:
    xml = _extract_xml(source)
    try:
        import xml.etree.ElementTree as ET

        root = ET.fromstring(xml)
    except ET.ParseError:
        return None
    first = root.find("node")
    if first is None:
        return None
    package = (first.attrib.get("package") or "").strip()
    return package or None


@dataclass(frozen=True, slots=True)
class AndroidWindowState:
    current_focus_line: str | None
    current_focus_package: str | None
    current_focus_activity: str | None
    focused_app_line: str | None
    focused_app_package: str | None
    focused_app_activity: str | None
    raw: str


@dataclass(frozen=True, slots=True)
class AndroidUiDump:
    xml: str
    root_package: str | None
    current_package: str | None
    current_activity: str | None
    mitigations_applied: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AndroidDisplaySize:
    width: int
    height: int


def _escape_adb_text(text: str) -> str:
    if any(ord(char) > 127 for char in text):
        raise MobileExecutionError("adb-backed mobile_type currently supports ASCII text only.")
    escaped = text.replace(" ", "%s")
    for char in "\\()[]{}<>|;&*$\"'`":
        escaped = escaped.replace(char, f"\\{char}")
    return escaped
@dataclass(frozen=True, slots=True)
class AndroidAdbClient:
    adb_binary: str
    device_serial: str
    timeout_seconds: float = 30.0

    def _base(self) -> list[str]:
        return [self.adb_binary, "-s", self.device_serial]

    def _run(
        self,
        args: list[str],
        *,
        timeout_seconds: float | None = None,
        text: bool = True,
    ) -> str | bytes:
        completed = self._run_completed(
            args,
            timeout_seconds=timeout_seconds,
            text=text,
        )
        return completed.stdout

    def _run_completed(
        self,
        args: list[str],
        *,
        timeout_seconds: float | None = None,
        text: bool = True,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str] | subprocess.CompletedProcess[bytes]:
        try:
            completed = subprocess.run(
                [*self._base(), *args],
                check=check,
                capture_output=True,
                text=text,
                timeout=timeout_seconds or self.timeout_seconds,
            )
        except FileNotFoundError as exc:
            raise MobileExecutionError(f"adb is not available: {exc}") from exc
        except subprocess.CalledProcessError as exc:
            raise MobileExecutionError(_command_output(exc) or "adb command failed.") from exc
        except subprocess.TimeoutExpired as exc:
            raise MobileExecutionError(f"adb command timed out after {exc.timeout} seconds.") from exc
        except OSError as exc:
            raise MobileExecutionError(str(exc)) from exc
        return completed

    def _ui_dump_timeout_seconds(self) -> float:
        # Busy pages can keep UiAutomation from going idle for a long time. Cap
        # individual dump calls so snapshot can fall back quickly instead of
        # spending the whole request budget inside one dump attempt.
        return max(1.0, min(self.timeout_seconds, 4.0))

    def _read_window_state(self) -> AndroidWindowState:
        stdout = self._run(["shell", "dumpsys", "window", "windows"])
        assert isinstance(stdout, str)
        current_focus_line = _extract_last_line(stdout, _WINDOW_FOCUS_LINE_PREFIX)
        focused_app_line = _extract_last_line(stdout, _WINDOW_FOCUSED_APP_LINE_PREFIX)
        current_focus = _extract_focus(current_focus_line or "")
        focused_app = _extract_focus(focused_app_line or "")
        return AndroidWindowState(
            current_focus_line=current_focus_line,
            current_focus_package=current_focus["package"],
            current_focus_activity=current_focus["activity"],
            focused_app_line=focused_app_line,
            focused_app_package=focused_app["package"],
            focused_app_activity=focused_app["activity"],
            raw=stdout,
        )

    def _get_secure_setting(self, key: str) -> str | None:
        completed = self._run_completed(["shell", "settings", "get", "secure", key], check=False)
        stdout = completed.stdout if isinstance(completed.stdout, str) else ""
        return _normalize_setting(stdout)

    def _set_secure_setting(self, key: str, value: str | None) -> None:
        if value is None:
            self._run_completed(["shell", "settings", "delete", "secure", key], check=False)
            return
        self._run_completed(["shell", "settings", "put", "secure", key, value], check=False)

    def _reset_autofill(self) -> None:
        self._run_completed(["shell", "cmd", "autofill", "reset"], check=False)

    def _perform_tty_dump(self) -> str:
        dump_result = self._run_completed(
            ["shell", "uiautomator", "dump", "/dev/tty"],
            timeout_seconds=self._ui_dump_timeout_seconds(),
            check=False,
        )
        dump_stdout = dump_result.stdout if isinstance(dump_result.stdout, str) else ""
        dump_stderr = dump_result.stderr if isinstance(dump_result.stderr, str) else ""
        dump_output = "\n".join(
            item.strip()
            for item in (dump_stdout, dump_stderr)
            if item.strip()
        )
        normalized_output = dump_output.lower()
        if dump_result.returncode != 0 or "error:" in normalized_output:
            message = dump_output or f"uiautomator dump failed with exit code {dump_result.returncode}."
            raise MobileExecutionError(f"adb uiautomator dump failed: {message}")
        try:
            return _extract_xml(dump_stdout)
        except MobileExecutionError as exc:
            message = dump_output or "uiautomator dump did not return XML output."
            raise MobileExecutionError(f"adb uiautomator dump failed: {message}") from exc

    def _perform_compressed_file_dump(self) -> str:
        path = "/sdcard/window_dump.xml"
        self._run_completed(["shell", "rm", "-f", path], check=False)
        try:
            dump_result = self._run_completed(
                ["shell", "uiautomator", "dump", "--compressed"],
                timeout_seconds=self._ui_dump_timeout_seconds(),
                check=False,
            )
            dump_stdout = dump_result.stdout if isinstance(dump_result.stdout, str) else ""
            dump_stderr = dump_result.stderr if isinstance(dump_result.stderr, str) else ""
            dump_output = "\n".join(
                item.strip()
                for item in (dump_stdout, dump_stderr)
                if item.strip()
            )
            normalized_output = dump_output.lower()
            if dump_result.returncode != 0 or "error:" in normalized_output:
                message = dump_output or f"uiautomator dump failed with exit code {dump_result.returncode}."
                raise MobileExecutionError(f"adb uiautomator dump failed: {message}")
            file_result = self._run_completed(
                ["shell", "cat", path],
                timeout_seconds=self._ui_dump_timeout_seconds(),
                check=False,
            )
            file_stdout = file_result.stdout if isinstance(file_result.stdout, str) else ""
            file_stderr = file_result.stderr if isinstance(file_result.stderr, str) else ""
            if file_result.returncode != 0:
                message = file_stderr.strip() or file_stdout.strip() or "dump file was not created."
                raise MobileExecutionError(
                    f"adb uiautomator dump did not produce XML output: {message}",
                )
            return _extract_xml(file_stdout)
        finally:
            self._run_completed(["shell", "rm", "-f", path], check=False)

    def _perform_ui_dump(self) -> str:
        try:
            return self._perform_tty_dump()
        except MobileExecutionError as tty_error:
            message = str(tty_error)
            normalized_message = message.lower()
            fallback_indicators = (
                "did not return xml output",
                "/dev/tty",
                "timed out",
                "could not get idle state",
                "already registered",
                "uiautomationservice",
            )
            if not any(indicator in normalized_message for indicator in fallback_indicators):
                raise
            try:
                return self._perform_compressed_file_dump()
            except MobileExecutionError as file_error:
                raise MobileExecutionError(
                    f"{file_error} (tty dump also failed: {tty_error})",
                ) from file_error

    def _disable_known_accessibility_interferers(self) -> bool:
        current = self._get_secure_setting(_ENABLED_ACCESSIBILITY_SERVICES_KEY)
        if current is None:
            return False
        services = [part.strip() for part in current.split(":") if part.strip()]
        filtered = [item for item in services if item not in _KNOWN_ACCESSIBILITY_INTERFERERS]
        if filtered == services:
            return False
        self._set_secure_setting(
            _ENABLED_ACCESSIBILITY_SERVICES_KEY,
            ":".join(filtered) if filtered else None,
        )
        self._set_secure_setting(
            _ACCESSIBILITY_ENABLED_KEY,
            "1" if filtered else "0",
        )
        return True

    @staticmethod
    def _dump_matches_focus(*, xml: str, window_state: AndroidWindowState) -> bool:
        root_package = _root_package_from_xml(xml)
        expected_package = window_state.focused_app_package or window_state.current_focus_package
        if not root_package or not expected_package:
            return True
        return root_package == expected_package

    @staticmethod
    def _focus_indicates_autofill(window_state: AndroidWindowState | None) -> bool:
        if window_state is None or window_state.current_focus_line is None:
            return False
        return "autofill ui" in window_state.current_focus_line.lower()

    @staticmethod
    def _error_suggests_accessibility_interference(error: MobileExecutionError | None) -> bool:
        if error is None:
            return False
        message = str(error).lower()
        indicators = (
            "null root node",
            "wrong ui root",
            "already registered",
            "uiautomationservice",
            "uitestautomationbridge",
        )
        return any(indicator in message for indicator in indicators)

    def capture_ui_xml(self) -> AndroidUiDump:
        sentinel = object()
        original_autofill: object | str | None = sentinel
        original_accessibility_services: object | str | None = sentinel
        original_accessibility_enabled: object | str | None = sentinel
        applied: list[str] = []
        last_error: MobileExecutionError | None = None
        last_window_state: AndroidWindowState | None = None

        def attempt_dump() -> AndroidUiDump:
            nonlocal last_window_state
            window_state = self._read_window_state()
            last_window_state = window_state
            xml = self._perform_ui_dump()
            if not self._dump_matches_focus(xml=xml, window_state=window_state):
                root_package = _root_package_from_xml(xml)
                expected_package = window_state.focused_app_package or window_state.current_focus_package
                raise MobileExecutionError(
                    "adb uiautomator dump returned the wrong UI root "
                    f"(expected package '{expected_package}', got '{root_package}').",
                )
            current_package = window_state.focused_app_package or window_state.current_focus_package
            current_activity = window_state.focused_app_activity or window_state.current_focus_activity
            if current_package is None or current_activity is None:
                activity_stdout = self._run(["shell", "dumpsys", "activity", "activities"])
                assert isinstance(activity_stdout, str)
                activity_focus = _extract_focus(activity_stdout)
                current_package = current_package or activity_focus["package"]
                current_activity = current_activity or activity_focus["activity"]
            return AndroidUiDump(
                xml=xml,
                root_package=_root_package_from_xml(xml),
                current_package=current_package,
                current_activity=current_activity,
                mitigations_applied=tuple(applied),
            )

        try:
            try:
                return attempt_dump()
            except MobileExecutionError as exc:
                last_error = exc

            if self._focus_indicates_autofill(last_window_state):
                original_autofill = self._get_secure_setting(_AUTOFILL_SERVICE_KEY)
            if original_autofill is not sentinel and original_autofill is not None:
                self._set_secure_setting(_AUTOFILL_SERVICE_KEY, None)
                self._reset_autofill()
                applied.append("disable_autofill_service")
                try:
                    return attempt_dump()
                except MobileExecutionError as exc:
                    last_error = exc

            if self._error_suggests_accessibility_interference(last_error):
                original_accessibility_services = self._get_secure_setting(_ENABLED_ACCESSIBILITY_SERVICES_KEY)
                original_accessibility_enabled = self._get_secure_setting(_ACCESSIBILITY_ENABLED_KEY)
                if self._disable_known_accessibility_interferers():
                    applied.append("disable_accessibility_interferers")
                    try:
                        return attempt_dump()
                    except MobileExecutionError as exc:
                        last_error = exc

            if last_error is None:
                raise MobileExecutionError("adb uiautomator dump failed.")
            if applied:
                raise MobileExecutionError(
                    f"{last_error} (after mitigations: {', '.join(applied)})",
                ) from last_error
            raise last_error
        finally:
            if original_autofill is not sentinel:
                self._set_secure_setting(_AUTOFILL_SERVICE_KEY, original_autofill)
                self._reset_autofill()
            if original_accessibility_services is not sentinel:
                self._set_secure_setting(_ENABLED_ACCESSIBILITY_SERVICES_KEY, original_accessibility_services)
            if original_accessibility_enabled is not sentinel:
                self._set_secure_setting(_ACCESSIBILITY_ENABLED_KEY, original_accessibility_enabled)

    def dump_ui_xml(self) -> str:
        return self.capture_ui_xml().xml

    def take_screenshot(self) -> bytes:
        stdout = self._run(["exec-out", "screencap", "-p"], text=False)
        assert isinstance(stdout, bytes)
        return bytes(stdout)

    def display_size(self) -> AndroidDisplaySize:
        stdout = self._run(["shell", "wm", "size"])
        assert isinstance(stdout, str)
        for line in stdout.splitlines():
            match = re.search(r"(?:Physical|Override) size:\s*(\d+)x(\d+)", line)
            if match is not None:
                return AndroidDisplaySize(width=int(match.group(1)), height=int(match.group(2)))
        raise MobileExecutionError("Unable to determine Android display size from `wm size`.")

    def tap(self, *, x: int, y: int) -> None:
        self._run(["shell", "input", "tap", str(int(x)), str(int(y))])

    def wait_for_input_connection(
        self,
        *,
        expected_resource_id: str | None = None,
        timeout_seconds: float = 0.8,
        poll_seconds: float = 0.1,
    ) -> bool:
        deadline = time.monotonic() + max(float(timeout_seconds), 0.0)
        normalized_expected = (expected_resource_id or "").strip()
        expected_hints = {
            hint
            for hint in (
                normalized_expected,
                normalized_expected.rsplit("/", 1)[-1] if normalized_expected else "",
            )
            if hint
        }
        while True:
            remaining = deadline - time.monotonic()
            if remaining < 0:
                return False
            try:
                stdout = self._run(
                    ["shell", "dumpsys", "input_method"],
                    timeout_seconds=max(min(remaining, 1.0), 0.1),
                )
            except MobileExecutionError:
                stdout = ""
            if isinstance(stdout, str):
                served_line = _extract_last_line(stdout, _INPUT_METHOD_SERVED_CONNECTION_LINE_PREFIX)
                if served_line is not None and "finished=false" in served_line:
                    if not expected_hints:
                        return True
                    lowered = stdout.lower()
                    if any(hint.lower() in lowered for hint in expected_hints):
                        return True
            if remaining <= 0:
                return False
            time.sleep(min(max(poll_seconds, 0.01), remaining))

    def input_text(self, text: str) -> None:
        if any(ord(char) > 127 for char in text):
            self._input_text_via_adb_keyboard(text)
            return
        self._run(["shell", "input", "text", _escape_adb_text(text)])

    def _input_text_via_adb_keyboard(self, text: str) -> None:
        ime_list = self._run(["shell", "ime", "list", "-s"])
        assert isinstance(ime_list, str)
        installed_imes = {line.strip() for line in ime_list.splitlines() if line.strip()}
        if _ADB_KEYBOARD_IME not in installed_imes:
            raise MobileExecutionError(
                "adb-backed mobile_type requires com.android.adbkeyboard/.AdbIME for non-ASCII text.",
            )
        original_ime = self._get_secure_setting(_DEFAULT_INPUT_METHOD_KEY)
        try:
            self._run(["shell", "ime", "set", _ADB_KEYBOARD_IME])
            self._run(
                [
                    "shell",
                    "am",
                    "broadcast",
                    "-a",
                    "ADB_INPUT_B64",
                    "--es",
                    "msg",
                    base64.b64encode(text.encode("utf-8")).decode("ascii"),
                ]
            )
        finally:
            if original_ime:
                self._run_completed(["shell", "ime", "set", original_ime], check=False)

    def press_keycode(self, *, keycode: int) -> None:
        self._run(["shell", "input", "keyevent", str(int(keycode))])

    def press_key_combination(self, *, keycodes: tuple[int, ...]) -> None:
        normalized = tuple(int(keycode) for keycode in keycodes if int(keycode) >= 0)
        if not normalized:
            raise MobileExecutionError("At least one Android keycode is required.")
        self._run(
            [
                "shell",
                "input",
                "keycombination",
                *(str(keycode) for keycode in normalized),
            ]
        )

    def swipe(
        self,
        *,
        start_x: int,
        start_y: int,
        end_x: int,
        end_y: int,
        duration_ms: int | None = None,
    ) -> None:
        args = [
            "shell",
            "input",
            "swipe",
            str(int(start_x)),
            str(int(start_y)),
            str(int(end_x)),
            str(int(end_y)),
        ]
        if duration_ms is not None:
            args.append(str(max(int(duration_ms), 0)))
        self._run(args)

    def start_activity(self, *, app_package: str, app_activity: str) -> None:
        activity = app_activity
        if activity.startswith("."):
            activity = f"{app_package}{activity}"
        self._run(["shell", "am", "start", "-W", "-n", f"{app_package}/{activity}"])

    def activate_app(self, *, app_id: str, app_activity: str | None = None) -> None:
        if app_activity:
            self.start_activity(app_package=app_id, app_activity=app_activity)
            return
        self._run(
            [
                "shell",
                "monkey",
                "-p",
                app_id,
                "-c",
                "android.intent.category.LAUNCHER",
                "1",
            ]
        )

    def terminate_app(self, *, app_id: str) -> None:
        self._run(["shell", "am", "force-stop", app_id])

    def current_focus(self) -> dict[str, str | None]:
        window_state = self._read_window_state()
        if window_state.focused_app_package is not None and window_state.focused_app_activity is not None:
            return {
                "package": window_state.focused_app_package,
                "activity": window_state.focused_app_activity,
                "raw": window_state.raw,
            }
        if window_state.current_focus_package is not None and window_state.current_focus_activity is not None:
            return {
                "package": window_state.current_focus_package,
                "activity": window_state.current_focus_activity,
                "raw": window_state.raw,
            }
        stdout = self._run(["shell", "dumpsys", "activity", "activities"])
        assert isinstance(stdout, str)
        focus = _extract_focus(stdout)
        if focus["package"] is not None and focus["activity"] is not None:
            return focus
        return {
            "package": None,
            "activity": None,
            "raw": f"{window_state.raw}\n{stdout}",
        }

    @staticmethod
    def probe_adb_devices(*, adb_binary: str, timeout_seconds: float = 10.0) -> dict[str, Any]:
        base_payload: dict[str, Any] = {
            "adb_binary": adb_binary,
            "adb_available": False,
            "probe_ok": False,
            "adb_error": None,
            "connected": False,
            "device_count": 0,
            "connected_device_count": 0,
            "devices": [],
        }
        try:
            completed = subprocess.run(
                [adb_binary, "devices", "-l"],
                check=True,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
            )
        except FileNotFoundError as exc:
            base_payload["adb_error"] = str(exc)
            return base_payload
        except subprocess.CalledProcessError as exc:
            base_payload["adb_available"] = True
            base_payload["adb_error"] = _command_output(exc) or str(exc)
            return base_payload
        except (OSError, subprocess.SubprocessError) as exc:
            base_payload["adb_error"] = str(exc)
            return base_payload

        devices: list[dict[str, Any]] = []
        for line in completed.stdout.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("List of devices attached"):
                continue
            parts = stripped.split()
            if len(parts) < 2:
                continue
            serial = parts[0]
            state = parts[1]
            details: dict[str, str] = {}
            for item in parts[2:]:
                if ":" not in item:
                    continue
                key, value = item.split(":", 1)
                if key and value:
                    details[key] = value
            devices.append(
                {
                    "serial": serial,
                    "state": state,
                    "details": details,
                }
            )
        connected_device_count = sum(
            1 for item in devices if str(item.get("state") or "").strip().lower() == "device"
        )
        return {
            **base_payload,
            "adb_available": True,
            "probe_ok": True,
            "connected": connected_device_count > 0,
            "device_count": len(devices),
            "connected_device_count": connected_device_count,
            "devices": devices,
        }

    @staticmethod
    def list_adb_devices(*, adb_binary: str, timeout_seconds: float = 10.0) -> list[dict[str, Any]]:
        probe = AndroidAdbClient.probe_adb_devices(
            adb_binary=adb_binary,
            timeout_seconds=timeout_seconds,
        )
        if not bool(probe.get("adb_available")) or not bool(probe.get("probe_ok")):
            error_message = str(probe.get("adb_error") or "unknown adb error").strip()
            raise MobileExecutionError(f"adb devices failed: {error_message}")
        devices = probe.get("devices")
        if not isinstance(devices, list):
            return []
        return [dict(item) for item in devices if isinstance(item, dict)]
