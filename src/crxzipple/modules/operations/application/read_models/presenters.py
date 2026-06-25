from __future__ import annotations

from typing import Any


def health_label(health: str) -> str:
    return {
        "healthy": "Healthy",
        "warning": "Warning",
        "error": "Error",
    }.get(health, "Unknown")


def health_delta(health: str, *, healthy: str) -> str:
    return {
        "healthy": healthy,
        "warning": "Operator attention recommended",
        "error": "Operator action required",
    }.get(health, "Insufficient data")


def health_tone(health: str) -> str:
    return {
        "healthy": "success",
        "warning": "warning",
        "error": "danger",
    }.get(health, "neutral")


def title_label(value: str) -> str:
    return value.replace("_", " ").replace("-", " ").title()


def display_value(value: object | None) -> str:
    if value is None:
        return "-"
    text = str(value).strip()
    return text or "-"


def truncate_text(value: Any, max_length: int) -> str:
    text = str(value)
    if len(text) <= max_length:
        return text
    return f"{text[: max_length - 3]}..."


def status_label(status: str, *, fallback: str = "Observed") -> str:
    normalized = status.strip().replace("_", " ").replace("-", " ")
    return normalized.title() if normalized else fallback


def status_tone(
    status: str,
    *,
    danger: set[str] | frozenset[str] = frozenset(
        {"failed", "error", "dead-letter", "timed-out"},
    ),
    warning: set[str] | frozenset[str] = frozenset(
        {"waiting", "pending", "blocked", "degraded", "stale"},
    ),
    success: set[str] | frozenset[str] = frozenset(
        {"succeeded", "success", "completed", "ready", "delivered"},
    ),
    info: set[str] | frozenset[str] = frozenset(),
) -> str:
    normalized = status.strip().lower().replace("_", "-")
    if normalized in danger:
        return "danger"
    if normalized in warning:
        return "warning"
    if normalized in success:
        return "success"
    if normalized in info:
        return "info"
    return "neutral"
