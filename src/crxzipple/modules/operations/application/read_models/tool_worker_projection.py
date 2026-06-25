from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from crxzipple.modules.tool.domain import (
    ToolWorkerRegistration,
    ToolWorkerStatus,
)
from crxzipple.shared.time import coerce_utc_datetime

_WORKER_POOL_EXPIRED_GRACE_SECONDS = 300


def worker_registration_bucket(
    worker: ToolWorkerRegistration,
    *,
    now: datetime,
) -> str:
    if (
        worker.lease_expires_at is not None
        and coerce_utc_datetime(worker.lease_expires_at) <= coerce_utc_datetime(now)
    ):
        return "lease_expired"
    if worker.status.value == "stale":
        return "stale"
    if worker.current_in_flight >= worker.max_in_flight:
        return "busy"
    if worker.current_in_flight > 0:
        return "active"
    return "idle"


def worker_registration_counts_in_pool(
    worker: ToolWorkerRegistration,
    *,
    now: datetime,
) -> bool:
    if worker.lease_expires_at is not None:
        expires_at = coerce_utc_datetime(worker.lease_expires_at)
        if expires_at > coerce_utc_datetime(now):
            return True
        return expires_at >= coerce_utc_datetime(now) - timedelta(
            seconds=_WORKER_POOL_EXPIRED_GRACE_SECONDS,
        )
    if worker.status is ToolWorkerStatus.STALE:
        return coerce_utc_datetime(worker.heartbeat_at) >= coerce_utc_datetime(
            now,
        ) - timedelta(seconds=_WORKER_POOL_EXPIRED_GRACE_SECONDS)
    return True


def worker_registration_status(bucket: str) -> tuple[str, str]:
    return {
        "idle": ("Online", "success"),
        "active": ("Active", "info"),
        "busy": ("Busy", "warning"),
        "stale": ("Stale", "warning"),
        "lease_expired": ("Lease Expired", "danger"),
    }.get(bucket, ("Unknown", "neutral"))


def worker_runtime_count(worker: ToolWorkerRegistration) -> str:
    return str(len(worker_runtime_registrations(worker)))


def worker_provider_summary(worker: ToolWorkerRegistration) -> str:
    providers: set[str] = set()
    for registration in worker_runtime_registrations(worker):
        concurrency_key = _optional_str(registration.get("concurrency_key"))
        runtime_key = _optional_str(registration.get("runtime_key"))
        provider_key = concurrency_key or _provider_key_from_runtime_key(runtime_key)
        if provider_key:
            providers.add(_provider_label(provider_key))
    return _join_values(tuple(sorted(providers))) or "-"


def worker_capability_summary(worker: ToolWorkerRegistration) -> str:
    policy = worker.capabilities_payload.get("concurrency_policy")
    if not isinstance(policy, dict):
        return "-"
    parts: list[str] = []
    image_limit = _int_value(policy.get("image_max_in_flight"))
    shared_limit = _int_value(policy.get("shared_state_max_in_flight"))
    default_limit = _int_value(policy.get("default_max_in_flight"))
    if image_limit:
        parts.append(f"image {image_limit}/worker")
    if shared_limit:
        parts.append(f"shared {shared_limit}/worker")
    if default_limit:
        parts.append(f"default {default_limit}/worker")
    return _join_values(tuple(parts)) or "-"


def worker_runtime_registrations(
    worker: ToolWorkerRegistration,
) -> tuple[dict[str, Any], ...]:
    registry = worker.capabilities_payload.get("runtime_registry")
    if not isinstance(registry, dict):
        return ()
    registrations = registry.get("registrations")
    if not isinstance(registrations, list):
        return ()
    return tuple(item for item in registrations if isinstance(item, dict))


def worker_runtime_provider_label(registration: dict[str, Any]) -> str:
    concurrency_key = _optional_str(registration.get("concurrency_key"))
    runtime_key = _optional_str(registration.get("runtime_key"))
    provider_key = concurrency_key or _provider_key_from_runtime_key(runtime_key)
    return _provider_label(provider_key) if provider_key else "-"


def _provider_key_from_runtime_key(runtime_key: str | None) -> str | None:
    if runtime_key is None:
        return None
    runtime_key_lower = runtime_key.strip().lower()
    for prefix in ("openapi.", "mcp."):
        if runtime_key_lower.startswith(prefix):
            parts = runtime_key_lower.split(".")
            if len(parts) >= 2 and parts[1].strip():
                return f"{prefix.removesuffix('.')}:{parts[1].strip()}"
    if runtime_key_lower.startswith("openai_"):
        return "provider:openai"
    return runtime_key_lower or None


def _provider_label(provider_key: str) -> str:
    if provider_key.startswith("provider:"):
        return provider_key.removeprefix("provider:")
    if provider_key.startswith("openapi:"):
        return f"openapi / {provider_key.removeprefix('openapi:')}"
    if provider_key.startswith("mcp:"):
        return f"mcp / {provider_key.removeprefix('mcp:')}"
    return provider_key


def _int_value(value: object | None) -> int:
    if isinstance(value, bool) or value is None:
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and value.strip():
        try:
            return int(value)
        except ValueError:
            return 0
    return 0


def _optional_str(value: object | None) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _join_values(values: tuple[str, ...] | list[str]) -> str:
    normalized = [value.strip() for value in values if value and value.strip()]
    return ", ".join(normalized) if normalized else "-"
