from __future__ import annotations

from typing import Any, Mapping

from crxzipple.modules.browser.domain import BrowserValidationError

from .action_engine_payloads import (
    _detach_cdp_session,
    _json_safe_payload,
    _new_page_cdp_session,
    _payload_text_any,
    _send_cdp_session_command,
)


def execute_cdp_raw(page: Any, payload: Mapping[str, Any]) -> dict[str, Any]:
    method = _payload_text_any(payload, "method")
    if method is None:
        raise BrowserValidationError("payload.method is required for cdp-raw.")
    params = payload.get("params")
    if params is None:
        params = {}
    if not isinstance(params, Mapping):
        raise BrowserValidationError("payload.params must be an object.")

    session = _new_page_cdp_session(page)
    try:
        raw_result = _send_cdp_session_command(session, method, params)
    finally:
        _detach_cdp_session(session)
    return {
        "kind": "cdp-raw",
        "method": method,
        "result": _json_safe_payload(raw_result),
    }
