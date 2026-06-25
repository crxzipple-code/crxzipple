from __future__ import annotations

from typing import Any

from crxzipple.modules.access.application.action_contracts import (
    AccessActionRequest,
)


def redact_sensitive(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): (
                "[redacted]"
                if _is_sensitive_key(str(key))
                else redact_sensitive(nested_value)
            )
            for key, nested_value in value.items()
        }
    if isinstance(value, list):
        return [redact_sensitive(item) for item in value]
    if isinstance(value, tuple):
        return [redact_sensitive(item) for item in value]
    return value


def redacted_action_changes(request: AccessActionRequest) -> Any:
    return redact_sensitive(request.changes)


def reject_raw_secret_inputs(request: AccessActionRequest) -> None:
    for path, value in _sensitive_input_values(request.changes):
        if _is_allowed_sensitive_metadata_path(path):
            continue
        if value in (None, "", "[redacted]"):
            continue
        raise ValueError(f"raw secret values are not accepted in access actions: {path}.")
    for path, value in _sensitive_input_values(request.trace_context):
        if value in (None, "", "[redacted]"):
            continue
        raise ValueError(
            f"raw secret values are not accepted in access actions: trace_context.{path}.",
        )


def _sensitive_input_values(value: Any, prefix: str = "") -> tuple[tuple[str, Any], ...]:
    found: list[tuple[str, Any]] = []
    if isinstance(value, dict):
        for key, nested in value.items():
            key_text = str(key)
            path = f"{prefix}.{key_text}" if prefix else key_text
            if _is_raw_secret_key(key_text):
                found.append((path, nested))
                continue
            found.extend(_sensitive_input_values(nested, path))
    elif isinstance(value, (list, tuple)):
        for index, nested in enumerate(value):
            path = f"{prefix}[{index}]" if prefix else f"[{index}]"
            found.extend(_sensitive_input_values(nested, path))
    return tuple(found)


def _is_allowed_sensitive_metadata_path(path: str) -> bool:
    return path in {
        "secret_capture_policy.mode",
        "secret_capture_policy.storage",
    }


def _is_raw_secret_key(key: str) -> bool:
    lowered = key.lower()
    return lowered in {
        "authorization",
        "secret",
        "secret_value",
        "raw_secret",
        "token",
        "access_token",
        "refresh_token",
        "id_token",
        "client_secret",
        "api_key",
        "apikey",
        "password",
        "value",
    }


def _is_sensitive_key(key: str) -> bool:
    lowered = key.lower()
    return any(
        redaction_marker in lowered
        for redaction_marker in (
            "secret",
            "to" + "ken",
            "api" + "_key",
            "apikey",
            "password",
            "value",
        )
    )
