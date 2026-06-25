from __future__ import annotations

from datetime import datetime
from typing import Any

from crxzipple.modules.llm.domain import LlmInvocation
from crxzipple.shared.time import coerce_utc_datetime


def token_total(invocations: list[LlmInvocation]) -> int:
    total = 0
    for invocation in invocations:
        total += invocation_token_total(invocation)
    return total


def invocation_token_total(invocation: LlmInvocation) -> int:
    if invocation.result is None or invocation.result.usage is None:
        return 0
    usage = invocation.result.usage
    if usage.total_tokens is not None:
        return usage.total_tokens
    return (usage.input_tokens or 0) + (usage.output_tokens or 0)


def invocation_input_tokens(invocation: LlmInvocation) -> int:
    if invocation.result is None or invocation.result.usage is None:
        return 0
    return invocation.result.usage.input_tokens or 0


def request_metadata(invocation: LlmInvocation) -> dict[str, object]:
    metadata = invocation.request_metadata
    return metadata if isinstance(metadata, dict) else {}


def metadata_int(invocation: LlmInvocation, key: str) -> int:
    value = request_metadata(invocation).get(key)
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


def metadata_int_label(invocation: LlmInvocation, key: str) -> str:
    return str(value) if (value := metadata_int(invocation, key)) else "-"


def metadata_text_label(invocation: LlmInvocation, key: str) -> str:
    value = _text(request_metadata(invocation).get(key))
    return value or "-"


def duration_seconds(invocation: LlmInvocation) -> float | None:
    if invocation.started_at is None or invocation.completed_at is None:
        return None
    return max(
        (
            coerce_utc_datetime(invocation.completed_at)
            - coerce_utc_datetime(invocation.started_at)
        ).total_seconds(),
        0.0,
    )


def duration_label(invocation: LlmInvocation) -> str:
    duration = duration_seconds(invocation)
    return seconds_label(duration)


def duration_or_age_label(invocation: LlmInvocation, *, now: datetime) -> str:
    duration = duration_seconds(invocation)
    if duration is not None:
        return seconds_label(duration)
    return age_label(invocation.started_at or invocation.created_at, now=now)


def age_label(value: datetime | None, *, now: datetime) -> str:
    if value is None:
        return "-"
    return seconds_label(age_seconds(value, now=now))


def age_seconds(value: datetime | None, *, now: datetime) -> int:
    if value is None:
        return 0
    return max(
        int((coerce_utc_datetime(now) - coerce_utc_datetime(value)).total_seconds()),
        0,
    )


def seconds_label(value: float | int | None) -> str:
    if value is None:
        return "-"
    seconds = max(float(value), 0.0)
    if seconds < 1:
        return f"{int(seconds * 1000)}ms"
    if seconds < 60:
        formatted = f"{seconds:.2f}".rstrip("0").rstrip(".")
        return f"{formatted}s"
    minutes, remaining = divmod(int(seconds), 60)
    if minutes < 60:
        return f"{minutes}m {remaining}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes}m"


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
