from __future__ import annotations

import base64
from collections.abc import Callable
from dataclasses import dataclass
import mimetypes
from pathlib import Path
import tempfile
from typing import Any, Mapping

from crxzipple.modules.browser.domain import BrowserValidationError


@dataclass(frozen=True, slots=True)
class BrowserPeripheralActionService:
    def execute_console(
        self,
        *,
        session_pool: Any,
        page: Any,
        payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        level = _payload_text_any(payload, "level")
        limit = _payload_int_any(payload, "limit", minimum=1)
        clear = bool(_payload_bool_any(payload, "clear"))
        messages = session_pool.get_console_messages(
            page=page,
            level=level,
            limit=limit,
            clear=clear,
        )
        return {
            "kind": "console",
            "messages": messages,
            "count": len(messages),
            "level": level.strip().lower() if isinstance(level, str) and level.strip() else None,
            "limit": limit,
            "cleared": clear,
        }

    def execute_dialog(
        self,
        *,
        page: Any,
        payload: Mapping[str, Any],
        timeout_ms: float | None,
    ) -> dict[str, Any]:
        wait_for_event = getattr(page, "wait_for_event", None)
        if not callable(wait_for_event):
            raise BrowserValidationError(
                "Playwright page does not support wait_for_event().",
            )
        dialog = wait_for_event("dialog", **_timeout_kwargs(timeout_ms))
        accept = payload.get("accept")
        if accept is None:
            accept = True
        prompt_text = _payload_text_any(payload, "prompt_text", "promptText")
        if bool(accept):
            accept_method = getattr(dialog, "accept", None)
            if not callable(accept_method):
                raise BrowserValidationError(
                    "Playwright dialog does not support accept().",
                )
            if prompt_text is not None:
                accept_method(prompt_text)
            else:
                accept_method()
            result = _serialize_dialog(dialog)
            result["handled_as"] = "accept"
            if prompt_text is not None:
                result["prompt_text"] = prompt_text
            return result
        dismiss_method = getattr(dialog, "dismiss", None)
        if not callable(dismiss_method):
            raise BrowserValidationError(
                "Playwright dialog does not support dismiss().",
            )
        dismiss_method()
        result = _serialize_dialog(dialog)
        result["handled_as"] = "dismiss"
        return result

    def execute_download(
        self,
        *,
        page: Any,
        timeout_ms: float | None,
        trigger: Callable[[], Any],
    ) -> dict[str, Any]:
        expect_download = getattr(page, "expect_download", None)
        if not callable(expect_download):
            raise BrowserValidationError(
                "Playwright page does not support expect_download().",
            )
        with expect_download(**_timeout_kwargs(timeout_ms)) as download_info:
            trigger()
        return _serialize_download(download_info.value)

    def execute_wait_download(
        self,
        *,
        page: Any,
        timeout_ms: float | None,
    ) -> dict[str, Any]:
        wait_for_event = getattr(page, "wait_for_event", None)
        if not callable(wait_for_event):
            raise BrowserValidationError(
                "Playwright page does not support wait_for_event().",
            )
        return _serialize_download(
            wait_for_event("download", **_timeout_kwargs(timeout_ms)),
        )

    def execute_screenshot(
        self,
        *,
        page: Any,
        payload: Mapping[str, Any],
        timeout_ms: float | None,
    ) -> dict[str, Any]:
        image_type = _payload_text_any(payload, "type") or "png"
        screenshot_kwargs: dict[str, Any] = {
            "full_page": bool(payload.get("full_page", False)),
            "type": image_type,
        }
        screenshot_kwargs.update(_timeout_kwargs(timeout_ms))
        screenshot = page.screenshot(**screenshot_kwargs)
        return {
            "kind": "screenshot",
            "content_type": f"image/{image_type}",
            "encoding": "base64",
            "data": base64.b64encode(screenshot).decode("ascii"),
        }

    def execute_pdf(
        self,
        *,
        page: Any,
        payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        pdf = page.pdf(print_background=bool(payload.get("print_background", True)))
        return {
            "kind": "pdf",
            "content_type": "application/pdf",
            "encoding": "base64",
            "data": base64.b64encode(pdf).decode("ascii"),
        }

    def execute_evaluate(
        self,
        *,
        page: Any,
        locator: Any,
        payload: Mapping[str, Any],
    ) -> Any:
        expression = _payload_text_any(payload, "expression", "fn", "script")
        if expression is None:
            raise BrowserValidationError(
                "payload.expression, payload.fn, or payload.script is required.",
            )
        if locator is not None:
            if "arg" in payload:
                return locator.evaluate(expression, payload.get("arg"))
            return locator.evaluate(expression)
        if "arg" in payload:
            return page.evaluate(expression, payload.get("arg"))
        return page.evaluate(expression)


def _timeout_kwargs(timeout: float | None) -> dict[str, float]:
    if timeout is None:
        return {}
    return {"timeout": timeout}


def _payload_text_any(payload: Mapping[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _payload_value_any(payload: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in payload:
            return payload.get(key)
    return None


def _payload_bool_any(payload: Mapping[str, Any], *keys: str) -> bool | None:
    value = _payload_value_any(payload, *keys)
    if isinstance(value, bool):
        return value
    return None


def _payload_int_any(
    payload: Mapping[str, Any],
    *keys: str,
    minimum: int = 0,
) -> int | None:
    value = _payload_value_any(payload, *keys)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise BrowserValidationError(f"payload.{keys[0]} must be an integer.")
    resolved = int(value)
    if resolved < minimum:
        raise BrowserValidationError(
            f"payload.{keys[0]} must be greater than or equal to {minimum}.",
        )
    return resolved


def _download_name(download: Any) -> str | None:
    suggested = getattr(download, "suggested_filename", None)
    if callable(suggested):
        try:
            suggested = suggested()
        except Exception:  # noqa: BLE001
            suggested = None
    if isinstance(suggested, str) and suggested.strip():
        return suggested.strip()
    return None


def _download_failure(download: Any) -> str | None:
    failure = getattr(download, "failure", None)
    if callable(failure):
        try:
            failure = failure()
        except Exception as exc:  # noqa: BLE001
            failure = str(exc)
    if isinstance(failure, str) and failure.strip():
        return failure.strip()
    return None


def _download_bytes(download: Any) -> bytes:
    path_value: str | None = None
    path_getter = getattr(download, "path", None)
    if callable(path_getter):
        try:
            raw_path = path_getter()
        except Exception:  # noqa: BLE001
            raw_path = None
        if isinstance(raw_path, str) and raw_path.strip():
            path_value = raw_path.strip()
    if path_value is not None:
        return Path(path_value).read_bytes()
    save_as = getattr(download, "save_as", None)
    if callable(save_as):
        with tempfile.NamedTemporaryFile(delete=False) as temp_file:
            temp_path = temp_file.name
        try:
            save_as(temp_path)
            return Path(temp_path).read_bytes()
        finally:
            Path(temp_path).unlink(missing_ok=True)
    raise BrowserValidationError(
        "Playwright download does not expose a readable path.",
    )


def _download_content_type(*, filename: str | None) -> str:
    if filename is not None:
        guessed, _ = mimetypes.guess_type(filename)
        if guessed:
            return guessed
    return "application/octet-stream"


def _serialize_download(download: Any) -> dict[str, Any]:
    failure = _download_failure(download)
    if failure is not None:
        raise BrowserValidationError(f"Browser download failed: {failure}")
    filename = _download_name(download)
    data = _download_bytes(download)
    content_type = _download_content_type(filename=filename)
    result: dict[str, Any] = {
        "kind": "download",
        "content_type": content_type,
        "encoding": "base64",
        "data": base64.b64encode(data).decode("ascii"),
    }
    if filename is not None:
        result["name"] = filename
    return result


def _serialize_dialog(dialog: Any) -> dict[str, Any]:
    dialog_type = getattr(dialog, "type", None)
    message = getattr(dialog, "message", None)
    default_value = getattr(dialog, "default_value", None)
    result: dict[str, Any] = {
        "kind": "dialog",
        "type": str(dialog_type).strip() if dialog_type is not None else None,
        "message": str(message) if message is not None else "",
    }
    if default_value is not None:
        result["default_value"] = str(default_value)
    return result


__all__ = ["BrowserPeripheralActionService"]
