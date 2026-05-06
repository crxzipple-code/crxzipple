from __future__ import annotations

from crxzipple.modules.session.domain.exceptions import SessionValidationError


def session_lane_key(session_key: str) -> str:
    normalized = session_key.strip()
    if not normalized:
        raise SessionValidationError("Session route session_key cannot be empty.")
    return f"session:{normalized}"
