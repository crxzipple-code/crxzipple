from __future__ import annotations

from typing import Any


def runtime_int(
    runtime_bootstrap_config: Any | None,
    name: str,
    *,
    fallback: int | float | None = None,
) -> int | None:
    value = getattr(runtime_bootstrap_config, name, fallback)
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def runtime_float(
    runtime_bootstrap_config: Any | None,
    name: str,
    *,
    fallback: int | float | None = None,
) -> float | None:
    value = getattr(runtime_bootstrap_config, name, fallback)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def runtime_bool(runtime_bootstrap_config: Any | None, name: str) -> bool | None:
    value = getattr(runtime_bootstrap_config, name, None)
    if value is None:
        return None
    return bool(value)


def enabled_label(value: bool | None) -> str:
    if value is None:
        return "-"
    return "enabled" if value else "disabled"


def token_pair_label(
    reserve_tokens: int | None,
    soft_threshold_tokens: int | None,
) -> str:
    if reserve_tokens is None and soft_threshold_tokens is None:
        return "-"
    reserve = f"{reserve_tokens:,}" if reserve_tokens is not None else "-"
    soft = f"{soft_threshold_tokens:,}" if soft_threshold_tokens is not None else "-"
    return f"{reserve} / {soft} tokens"
