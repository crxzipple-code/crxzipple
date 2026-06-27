from __future__ import annotations

from typing import Any, Mapping, Protocol

from crxzipple.modules.browser.domain import BrowserValidationError

from .storage_payloads import payload_bool_any, payload_number_any, payload_text_any


class StorageValueRedactor(Protocol):
    def __call__(self, value: Any, *, key_hint: str | None = None) -> Any: ...


def redact_cookie_payload(
    cookie: Mapping[str, Any],
    redact_value: StorageValueRedactor,
) -> dict[str, Any]:
    redacted = {
        str(key): redact_value(value, key_hint=str(key))
        for key, value in cookie.items()
    }
    if "value" in redacted:
        redacted["value"] = "[redacted]"
    return redacted


def cookie_payload(raw_cookie: Mapping[str, Any]) -> dict[str, Any]:
    name = payload_text_any(raw_cookie, "name")
    value = payload_text_any(raw_cookie, "value")
    if name is None or value is None:
        raise BrowserValidationError("payload.cookie.name and payload.cookie.value are required.")
    resolved: dict[str, Any] = {
        "name": name,
        "value": value,
    }
    for source_key, target_key in (
        ("url", "url"),
        ("domain", "domain"),
        ("path", "path"),
        ("sameSite", "sameSite"),
        ("same_site", "sameSite"),
    ):
        source_value = payload_text_any(raw_cookie, source_key)
        if source_value is not None:
            resolved[target_key] = source_value
    expires = payload_number_any(raw_cookie, "expires")
    if expires is not None:
        resolved["expires"] = expires
    for source_key, target_key in (
        ("httpOnly", "httpOnly"),
        ("http_only", "httpOnly"),
        ("secure", "secure"),
    ):
        source_value = payload_bool_any(raw_cookie, source_key)
        if source_value is not None:
            resolved[target_key] = source_value
    if "url" not in resolved and not ("domain" in resolved and "path" in resolved):
        raise BrowserValidationError(
            "payload.cookie requires url, or domain plus path.",
        )
    return resolved


__all__ = ["cookie_payload", "redact_cookie_payload"]
