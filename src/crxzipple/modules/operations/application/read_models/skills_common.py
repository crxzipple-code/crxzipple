from __future__ import annotations

from pathlib import Path
from typing import Any

from crxzipple.modules.operations.application.read_models.models import (
    OperationsTableSectionModel,
)
from crxzipple.modules.operations.application.read_models.skills_models import (
    SkillRecord,
)


def overview_rows(section: OperationsTableSectionModel) -> tuple[dict[str, str], ...]:
    return tuple(dict(row.cells) for row in section.rows[:80])


def search_blob(record: SkillRecord) -> str:
    requirements = getattr(record.package, "requirements", None)
    return " ".join(
        (
            skill_name(record.package),
            source(record.package),
            text(getattr(record.package, "description", "")),
            joined(getattr(record.package, "tags", ())),
            joined(getattr(requirements, "required_tools", ())),
            joined(getattr(requirements, "suggested_tools", ())),
            record.status,
        )
    ).lower()


def skill_name(package: Any) -> str:
    return text(getattr(package, "name", ""))


def skill_id(package: Any) -> str:
    return skill_name(package).replace(" ", "_")


def source(package: Any) -> str:
    return text(getattr(package, "source", None), "unknown")


def items(values: Any) -> tuple[str, ...]:
    if values is None:
        return ()
    if isinstance(values, str):
        return (values,) if values.strip() else ()
    if isinstance(values, (list, tuple, set)):
        return tuple(text(item, "") for item in values if text(item, ""))
    return (text(values),)


def dict_items(values: Any) -> tuple[dict[str, Any], ...]:
    if values is None:
        return ()
    if isinstance(values, dict):
        return (dict(values),)
    if isinstance(values, (list, tuple, set)):
        return tuple(dict(item) for item in values if isinstance(item, dict))
    return ()


def joined(values: Any) -> str:
    item_values = items(values)
    return ", ".join(item_values) if item_values else "-"


def status_label(status: Any) -> str:
    raw = getattr(status, "value", status)
    text_value = text(raw, "unknown").replace("_", " ").replace("-", " ")
    return " ".join(part.capitalize() for part in text_value.split()) or "-"


def normalized_filter(value: Any) -> str:
    text_value = text(value, "all").strip().lower().replace(" ", "_").replace("-", "_")
    return text_value or "all"


def int_value(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def health_label(health: str) -> str:
    if health == "error":
        return "Error"
    if health == "warning":
        return "Warning"
    return "Healthy"


def health_delta(health: str) -> str:
    if health == "error":
        return "Skill manager is not connected"
    if health == "warning":
        return "Some skill requirements need setup"
    return "Skill packages are queryable"


def health_tone(health: str) -> str:
    if health == "error":
        return "danger"
    if health == "warning":
        return "warning"
    return "success"


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


def duration_label(value: Any) -> str:
    if value is None:
        return "-"
    try:
        duration_ms = float(value)
    except (TypeError, ValueError):
        return text(value)
    if duration_ms < 1000:
        return f"{duration_ms:.0f} ms"
    return f"{duration_ms / 1000:.2f} s"


def short(value: Any, size: int = 80) -> str:
    text_value = text(value)
    if len(text_value) <= size:
        return text_value
    return f"{text_value[: max(8, size - 8)]}...{text_value[-5:]}"


def text(value: Any, default: str = "-") -> str:
    if value is None:
        return default
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (list, tuple, set)):
        return ", ".join(text(item, "") for item in value if text(item, ""))
    if isinstance(value, dict):
        return ", ".join(f"{key}={text(item, '')}" for key, item in sorted(value.items()))
    text_value = str(value).strip()
    return text_value if text_value else default
