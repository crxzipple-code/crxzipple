from __future__ import annotations

from typing import Any


def status_label(status: Any) -> str:
    value = text(status, "unknown").replace("_", " ").replace("-", " ")
    return " ".join(part.capitalize() for part in value.split()) or "-"


def normalized_filter(value: Any) -> str:
    value_text = text(value, "all").strip().lower().replace(" ", "_").replace("-", "_")
    return value_text or "all"


def format_bytes(size: int) -> str:
    units = ("B", "KB", "MB", "GB")
    value = float(max(size, 0))
    unit = units[0]
    for unit in units:
        if value < 1024 or unit == units[-1]:
            break
        value /= 1024
    if unit == "B":
        return f"{int(value)} B"
    return f"{value:.1f} {unit}"


def duration_label_from_ms(value: Any) -> str:
    if isinstance(value, str) and value.strip():
        try:
            milliseconds = float(value)
        except ValueError:
            return value
    elif isinstance(value, (int, float)):
        milliseconds = float(value)
    else:
        return "-"
    if milliseconds < 1000:
        return f"{round(milliseconds)}ms"
    return f"{milliseconds / 1000:.2f}s"


def percent(part: int, total: int) -> str:
    if total <= 0:
        return "0%"
    return f"{round((part / total) * 100, 1)}%"


def short(value: Any, size: int = 80) -> str:
    value_text = text(value)
    if len(value_text) <= size:
        return value_text
    return f"{value_text[: max(8, size - 8)]}...{value_text[-5:]}"


def text(value: Any, default: str = "-") -> str:
    if value is None:
        return default
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, tuple, set)):
        return ", ".join(text(item, "") for item in value if text(item, ""))
    if isinstance(value, dict):
        return ", ".join(
            f"{key}={text(item, '')}" for key, item in sorted(value.items())
        )
    value_text = str(value).strip()
    return value_text if value_text else default
