from __future__ import annotations

from typing import Any

from crxzipple.modules.operations.application.read_models.models import (
    OperationsTableSectionModel,
)
from crxzipple.modules.operations.application.read_models.access_values import (
    normalized_filter,
    text,
)


def overview_rows(section: OperationsTableSectionModel) -> tuple[dict[str, str], ...]:
    return tuple(dict(row.cells) for row in section.rows[:80])


def tone_for_status(status: Any) -> str:
    normalized = normalized_filter(status)
    if normalized in {"expired", "failed", "error"}:
        return "danger"
    if normalized in {"setup_needed", "waiting_user", "unsupported", "blocked"}:
        return "warning"
    if normalized in {"ready", "healthy", "available", "enabled"}:
        return "success"
    return "neutral"


def status_label(status: Any) -> str:
    value = text(status, "unknown").replace("_", " ").replace("-", " ")
    return " ".join(part.capitalize() for part in value.split()) or "-"


def kind_label(kind: str) -> str:
    mapping = {
        "env": "Env",
        "file": "File Credential",
        "oauth_account": "OAuth Account",
        "inline_credential": "Inline Credential",
        "credential_set": "Credential Set",
        "authorization_requirement": "Authorization Requirement",
        "unknown": "Unknown",
    }
    return mapping.get(kind, status_label(kind))


def kind_tone(kind: str) -> str:
    if kind in {"env", "file", "oauth_account"}:
        return "info"
    if kind == "inline_credential":
        return "warning"
    return "neutral"


def health_label(health: str) -> str:
    if health == "error":
        return "Error"
    if health == "warning":
        return "Warning"
    return "Healthy"


def health_delta(health: str) -> str:
    if health == "error":
        return "Access service is not connected"
    if health == "warning":
        return "Access setup is required"
    return "Access inventory is ready"


def health_tone(health: str) -> str:
    if health == "error":
        return "danger"
    if health == "warning":
        return "warning"
    return "success"


