from __future__ import annotations

from typing import Any


def resolver_replay_window_label(value: object) -> str:
    if not isinstance(value, dict):
        return "-"
    parts: list[str] = []
    from_sequence = optional_int_label(value.get("from_sequence_no"))
    to_sequence = optional_int_label(value.get("to_sequence_no"))
    if from_sequence != "-" or to_sequence != "-":
        parts.append(f"seq={from_sequence}..{to_sequence}")
    item_count = optional_int_label(value.get("item_count"))
    if item_count != "-":
        parts.append(f"items={item_count}")
    active_only = value.get("active_session_only")
    if isinstance(active_only, bool):
        parts.append(f"active_only={str(active_only).lower()}")
    protocol_call_ids = value.get("protocol_call_ids")
    if isinstance(protocol_call_ids, list) and protocol_call_ids:
        parts.append(f"calls={len(protocol_call_ids)}")
    return "; ".join(parts) if parts else "-"


def optional_int_label(value: Any) -> str:
    parsed = _int_value(value)
    return str(parsed) if parsed else "-"


def text_value(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _int_value(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return max(value, 0)
    if isinstance(value, float):
        return max(int(value), 0)
    if isinstance(value, str):
        try:
            return max(int(value), 0)
        except ValueError:
            return 0
    return 0
