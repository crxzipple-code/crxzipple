from __future__ import annotations

from typing import Any

from crxzipple.modules.settings.application.redaction import redact_value


def redacted_json_object(value: dict[str, Any] | None) -> dict[str, Any] | None:
    if value is None:
        return None
    redacted = redact_value(value)
    return redacted if isinstance(redacted, dict) else {}


__all__ = ["redacted_json_object"]
