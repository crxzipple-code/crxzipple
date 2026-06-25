from __future__ import annotations

from typing import Any

from crxzipple.modules.operations.application.read_models.browser_values import int_value


def status_tone(status: str, *, driver: str = "-") -> str:
    if status == "attached":
        return "success"
    if status in {"failed", "degraded"}:
        if driver == "existing-session":
            return "warning"
        return "danger"
    if status in {"attaching", "recovering"}:
        return "warning"
    if status == "disabled":
        return "neutral"
    return "neutral"


def daemon_tone(status: str) -> str:
    normalized = status.lower()
    if normalized == "ready":
        return "success"
    if normalized in {"failed", "degraded"}:
        return "danger"
    if normalized in {"starting", "configured"}:
        return "warning"
    return "neutral"


def pool_tone(status: str, *, diagnostics: dict[str, Any] | None = None) -> str:
    normalized = status.lower()
    if normalized == "active":
        diagnostics = diagnostics or {}
        if int_value(diagnostics.get("failed_allocation_count")) > 0:
            return "warning"
        if diagnostics.get("cooling_profiles"):
            return "warning"
        return "success"
    if normalized == "degraded":
        return "danger"
    if normalized == "disabled":
        return "neutral"
    return "warning"


def allocation_tone(status: str) -> str:
    normalized = status.lower()
    if normalized == "active":
        return "success"
    if normalized in {"failed"}:
        return "danger"
    if normalized in {"expired", "released"}:
        return "neutral"
    return "warning"


def health_tone(health: str) -> str:
    if health == "healthy":
        return "success"
    if health == "error":
        return "danger"
    return "warning"


def health_delta(health: str) -> str:
    if health == "healthy":
        return "Browser runtime state is queryable"
    if health == "error":
        return "Operator action required"
    return "Operator attention recommended"
