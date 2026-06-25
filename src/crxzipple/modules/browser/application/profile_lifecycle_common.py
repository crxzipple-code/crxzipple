from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from crxzipple.modules.browser.domain import (
    BrowserProfileAllocation,
    BrowserProfileConfig,
    BrowserProfilePool,
    BrowserValidationError,
    BrowserSystemConfig,
)

UNSET = object()


def require_positive_int(value: object, *, label: str) -> int:
    try:
        numeric = int(value)
    except (TypeError, ValueError) as exc:
        raise BrowserValidationError(f"{label} must be an integer.") from exc
    if numeric < 1:
        raise BrowserValidationError(f"{label} must be greater than or equal to 1.")
    return numeric


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def changed_profile_fields(
    before: BrowserProfileConfig,
    after: BrowserProfileConfig,
) -> tuple[str, ...]:
    field_names = (
        "driver",
        "enabled",
        "cdp_url",
        "cdp_port",
        "user_data_dir",
        "profile_directory",
        "attach_only",
        "autostart",
        "proxy_mode",
        "proxy_server",
        "proxy_bypass_list",
        "proxy_binding_id",
        "proxy_credential_kind",
        "close_targets_on_release",
        "close_targets_on_expire",
    )
    return tuple(name for name in field_names if getattr(before, name) != getattr(after, name))


def profile_event_payload(
    profile: BrowserProfileConfig,
    *,
    system: BrowserSystemConfig,
    changed_fields: tuple[str, ...] = (),
) -> dict[str, Any]:
    return {
        "profile_name": profile.name,
        "driver": profile.driver,
        "enabled": profile.enabled,
        "default_profile": system.default_profile,
        "is_default": system.default_profile == profile.name,
        "attach_only": profile.attach_only,
        "autostart": profile.autostart,
        "has_cdp_url": profile.cdp_url is not None,
        "cdp_port": profile.cdp_port,
        "profile_directory_configured": profile.profile_directory is not None,
        "user_data_dir_configured": profile.user_data_dir is not None,
        "proxy_mode": profile.proxy_mode,
        "proxy_binding_id": profile.proxy_binding_id,
        "proxy_credential_kind": profile.proxy_credential_kind,
        "close_targets_on_release": profile.close_targets_on_release,
        "close_targets_on_expire": profile.close_targets_on_expire,
        "proxy_configured": profile.proxy_server is not None or profile.proxy_binding_id is not None,
        "changed_fields": list(changed_fields),
    }


def sanitize_profile_egress_result(result: Mapping[str, Any]) -> dict[str, Any]:
    sanitized: dict[str, Any] = {}
    for key in ("status", "ip", "url", "http_status"):
        value = result.get(key)
        if value is not None:
            sanitized[key] = value
    reason = result.get("reason")
    if reason is not None:
        sanitized["reason"] = str(reason)[:240]
    return sanitized


def changed_pool_fields(
    before: BrowserProfilePool,
    after: BrowserProfilePool,
) -> tuple[str, ...]:
    field_names = (
        "display_name",
        "enabled",
        "profile_names",
        "target_hosts",
        "selection_strategy",
        "max_concurrency_per_profile",
        "max_concurrency_total",
        "allocation_ttl_seconds",
        "cooldown_seconds",
        "failure_cooldown_seconds",
        "allow_attach_only",
        "close_targets_on_release",
        "close_targets_on_expire",
        "health_policy",
        "metadata",
    )
    return tuple(name for name in field_names if getattr(before, name) != getattr(after, name))


def pool_event_payload(
    pool: BrowserProfilePool,
    *,
    changed_fields: tuple[str, ...] = (),
) -> dict[str, Any]:
    return {
        "pool_id": pool.pool_id,
        "display_name": pool.display_name,
        "enabled": pool.enabled,
        "profile_names": list(pool.profile_names),
        "target_hosts": list(pool.target_hosts),
        "selection_strategy": pool.selection_strategy,
        "max_concurrency_per_profile": pool.max_concurrency_per_profile,
        "max_concurrency_total": pool.max_concurrency_total,
        "allocation_ttl_seconds": pool.allocation_ttl_seconds,
        "cooldown_seconds": pool.cooldown_seconds,
        "failure_cooldown_seconds": pool.failure_cooldown_seconds,
        "allow_attach_only": pool.allow_attach_only,
        "close_targets_on_release": pool.close_targets_on_release,
        "close_targets_on_expire": pool.close_targets_on_expire,
        "changed_fields": list(changed_fields),
    }


def allocation_event_payload(
    allocation: BrowserProfileAllocation,
) -> dict[str, Any]:
    return {
        "allocation_id": allocation.allocation_id,
        "pool_id": allocation.pool_id,
        "profile_name": allocation.profile_name,
        "consumer_kind": allocation.consumer_kind,
        "consumer_id": allocation.consumer_id,
        "target_host": allocation.target_host,
        "status": allocation.status,
        "acquired_at": allocation.acquired_at.isoformat(),
        "expires_at": allocation.expires_at.isoformat(),
        "last_heartbeat_at": (
            allocation.last_heartbeat_at.isoformat()
            if allocation.last_heartbeat_at is not None
            else None
        ),
        "released_at": (
            allocation.released_at.isoformat()
            if allocation.released_at is not None
            else None
        ),
        "release_reason": allocation.release_reason,
        "owned_target_ids": list(allocation.owned_target_ids),
        "metadata": dict(allocation.metadata),
    }
