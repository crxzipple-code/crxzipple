from __future__ import annotations

from typing import Any, Mapping

JsonObject = dict[str, Any]


def redacted_mapping(value: Mapping[str, Any]) -> JsonObject:
    result: JsonObject = {}
    for key, item in value.items():
        lowered = str(key).lower()
        if any(marker in lowered for marker in ("token", "secret", "verifier", "code")):
            result[str(key)] = "[redacted]"
        else:
            result[str(key)] = item
    return result
