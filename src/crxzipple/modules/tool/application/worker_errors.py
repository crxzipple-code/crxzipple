from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from crxzipple.modules.tool.application.service_support import (
    DISPATCH_LEASE_EXHAUSTED_REASON,
    DISPATCH_LEASE_EXPIRED_REASON,
)
from crxzipple.modules.tool.domain.value_objects import ToolRunError


def retry_exhausted_reason(reason: str) -> str:
    normalized = failure_message(reason)
    if normalized == DISPATCH_LEASE_EXPIRED_REASON:
        return DISPATCH_LEASE_EXHAUSTED_REASON
    return f"{normalized} (retry budget exhausted)"


def exception_message(exc: Exception) -> str:
    message = str(exc).strip()
    if message:
        return message
    return f"{exc.__class__.__name__} raised without an error message."


def exception_run_error(exc: Exception) -> ToolRunError:
    payload = exception_payload(exc)
    if payload is not None:
        message = failure_message(payload.get("message"))
        code = str(payload.get("code") or "execution_failed").strip() or "execution_failed"
        details = {
            str(key): safe_error_detail(value)
            for key, value in payload.items()
            if key not in {"message", "code"}
        }
        return ToolRunError(message=message, code=code, details=details)
    return ToolRunError(message=exception_message(exc))


def coerce_run_error(message: str | ToolRunError) -> ToolRunError:
    if isinstance(message, ToolRunError):
        return message
    return ToolRunError(message=failure_message(message))


def failure_message(message: object) -> str:
    normalized = str(message).strip()
    return normalized or "Tool run failed without an error message."


def exception_payload(exc: Exception) -> dict[str, Any] | None:
    to_payload = getattr(exc, "to_payload", None)
    if not callable(to_payload):
        return None
    try:
        payload = to_payload()
    except Exception:  # noqa: BLE001
        return None
    return dict(payload) if isinstance(payload, Mapping) else None


def safe_error_detail(value: Any) -> Any:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, Mapping):
        return {str(key): safe_error_detail(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [safe_error_detail(item) for item in value]
    return str(value)


__all__ = [
    "coerce_run_error",
    "exception_message",
    "exception_payload",
    "exception_run_error",
    "failure_message",
    "retry_exhausted_reason",
    "safe_error_detail",
]
