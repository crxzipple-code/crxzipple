from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from crxzipple.modules.browser.domain import BrowserValidationError

from .ports import (
    BrowserCapabilitiesResolver,
    BrowserProfileAllocationStore,
    BrowserProfilePoolStore,
    BrowserProfileResolver,
    BrowserRuntimeStateStore,
    BrowserSystemConfigStore,
)
from .runtime_payloads import (
    browser_runtime_state_applies_to_profile,
    browser_runtime_status_payload,
)


@dataclass(frozen=True, slots=True)
class BrowserProfileRuntimeRecord:
    name: str
    driver: str
    enabled: bool
    attach_only: bool
    configured_cdp_url: str | None
    configured_cdp_port: int | None
    resolved_cdp_url: str | None
    resolved_cdp_port: int | None
    user_data_dir: str | None
    profile_directory: str | None
    autostart: bool
    proxy_mode: str
    proxy_binding_id: str | None
    proxy_credential_kind: str
    close_targets_on_release: bool
    close_targets_on_expire: bool
    mode: str
    control_family: str
    action_family: str
    is_remote: bool
    supports_reset: bool
    supports_per_tab_ws: bool
    supports_json_tab_endpoints: bool
    supports_managed_tab_limit: bool
    runtime: dict[str, Any] | None
    diagnostics: dict[str, Any]


@dataclass(frozen=True, slots=True)
class BrowserProfilePoolRuntimeRecord:
    pool_id: str
    display_name: str | None
    enabled: bool
    status: str
    profile_names: tuple[str, ...]
    target_hosts: tuple[str, ...]
    selection_strategy: str
    max_concurrency_per_profile: int
    max_concurrency_total: int | None
    allocation_ttl_seconds: int
    cooldown_seconds: int
    failure_cooldown_seconds: int
    allow_attach_only: bool
    close_targets_on_release: bool
    close_targets_on_expire: bool
    profile_count: int
    ready_profile_count: int
    missing_profile_names: tuple[str, ...]
    disabled_profile_names: tuple[str, ...]
    attach_only_profile_names: tuple[str, ...]
    active_allocation_count: int
    diagnostics: dict[str, Any]


@dataclass(frozen=True, slots=True)
class BrowserProfileAllocationRuntimeRecord:
    allocation_id: str
    pool_id: str
    profile_name: str
    consumer_kind: str
    consumer_id: str
    target_host: str | None
    status: str
    raw_status: str
    acquired_at: datetime
    expires_at: datetime
    last_heartbeat_at: datetime | None
    released_at: datetime | None
    release_reason: str | None
    owned_target_ids: tuple[str, ...]
    metadata: dict[str, Any]


@dataclass(slots=True)
class BrowserProfileQueryService:
    system_config_store: BrowserSystemConfigStore
    runtime_state_store: BrowserRuntimeStateStore
    profile_resolver: BrowserProfileResolver
    capabilities_resolver: BrowserCapabilitiesResolver
    profile_pool_store: BrowserProfilePoolStore
    profile_allocation_store: BrowserProfileAllocationStore

    def list_profiles(self) -> tuple[BrowserProfileRuntimeRecord, ...]:
        system = self.system_config_store.load()
        records: list[BrowserProfileRuntimeRecord] = []
        for profile in system.profiles:
            runtime_state = self.runtime_state_store.get(profile_name=profile.name)
            try:
                resolved = self.profile_resolver.resolve(
                    system=system,
                    profile_name=profile.name,
                )
                capabilities = self.capabilities_resolver.resolve(profile=resolved)
                effective_runtime_state = (
                    runtime_state
                    if browser_runtime_state_applies_to_profile(
                        runtime_state,
                        resolved_profile=resolved,
                    )
                    else None
                )
                diagnostics = {"ok": True, "error": None}
            except BrowserValidationError as exc:
                resolved = None
                capabilities = None
                effective_runtime_state = runtime_state
                diagnostics = {"ok": False, "error": str(exc)}
            records.append(
                BrowserProfileRuntimeRecord(
                    name=profile.name,
                    driver=profile.driver,
                    enabled=bool(getattr(profile, "enabled", True)),
                    attach_only=profile.attach_only,
                    configured_cdp_url=profile.cdp_url,
                    configured_cdp_port=profile.cdp_port,
                    resolved_cdp_url=(
                        resolved.cdp_url if resolved is not None else None
                    ),
                    resolved_cdp_port=(
                        resolved.cdp_port if resolved is not None else None
                    ),
                    user_data_dir=profile.user_data_dir,
                    profile_directory=profile.profile_directory,
                    autostart=profile.autostart,
                    proxy_mode=profile.proxy_mode,
                    proxy_binding_id=profile.proxy_binding_id,
                    proxy_credential_kind=profile.proxy_credential_kind,
                    close_targets_on_release=profile.close_targets_on_release,
                    close_targets_on_expire=profile.close_targets_on_expire,
                    mode=capabilities.mode if capabilities is not None else "invalid",
                    control_family=(
                        capabilities.control_family
                        if capabilities is not None
                        else "invalid"
                    ),
                    action_family=(
                        capabilities.action_family
                        if capabilities is not None
                        else "invalid"
                    ),
                    is_remote=(
                        bool(capabilities.is_remote)
                        if capabilities is not None
                        else False
                    ),
                    supports_reset=(
                        bool(capabilities.supports_reset)
                        if capabilities is not None
                        else False
                    ),
                    supports_per_tab_ws=(
                        bool(capabilities.supports_per_tab_ws)
                        if capabilities is not None
                        else False
                    ),
                    supports_json_tab_endpoints=(
                        bool(capabilities.supports_json_tab_endpoints)
                        if capabilities is not None
                        else False
                    ),
                    supports_managed_tab_limit=(
                        bool(capabilities.supports_managed_tab_limit)
                        if capabilities is not None
                        else False
                    ),
                    runtime=(
                        browser_runtime_status_payload(effective_runtime_state)
                        if effective_runtime_state is not None
                        else None
                    ),
                    diagnostics=diagnostics,
                ),
            )
        return tuple(records)

    def list_pools(self) -> tuple[BrowserProfilePoolRuntimeRecord, ...]:
        system = self.system_config_store.load()
        profiles_by_name = {profile.name: profile for profile in system.profiles}
        now = datetime.now(timezone.utc)
        all_allocations = self.profile_allocation_store.list_allocations()
        active_allocations = tuple(
            allocation
            for allocation in all_allocations
            if allocation.is_active_at(now)
        )
        records: list[BrowserProfilePoolRuntimeRecord] = []
        for pool in self.profile_pool_store.list_pools():
            missing = tuple(
                profile_name
                for profile_name in pool.profile_names
                if profile_name not in profiles_by_name
            )
            disabled = tuple(
                profile_name
                for profile_name in pool.profile_names
                if profile_name in profiles_by_name
                and not bool(getattr(profiles_by_name[profile_name], "enabled", True))
            )
            attach_only = tuple(
                profile_name
                for profile_name in pool.profile_names
                if profile_name in profiles_by_name
                and (
                    bool(getattr(profiles_by_name[profile_name], "attach_only", False))
                    or getattr(profiles_by_name[profile_name], "driver", None)
                    == "existing-session"
                )
            )
            blocked_attach_only = attach_only if not pool.allow_attach_only else ()
            pool_allocations = tuple(
                allocation
                for allocation in active_allocations
                if allocation.pool_id == pool.pool_id
            )
            pool_history = tuple(
                allocation
                for allocation in all_allocations
                if allocation.pool_id == pool.pool_id
            )
            cooldown_summary = _pool_cooldown_summary(
                pool=pool,
                allocations=pool_history,
                now=now,
            )
            ready_profile_count = max(
                0,
                len(pool.profile_names)
                - len(missing)
                - len(disabled)
                - len(blocked_attach_only),
            )
            available_profile_count = max(
                0,
                ready_profile_count - len(cooldown_summary["cooling_profiles"]),
            )
            status = _pool_status(
                enabled=pool.enabled,
                missing=missing,
                ready_profile_count=ready_profile_count,
            )
            records.append(
                BrowserProfilePoolRuntimeRecord(
                    pool_id=pool.pool_id,
                    display_name=pool.display_name,
                    enabled=pool.enabled,
                    status=status,
                    profile_names=pool.profile_names,
                    target_hosts=pool.target_hosts,
                    selection_strategy=pool.selection_strategy,
                    max_concurrency_per_profile=pool.max_concurrency_per_profile,
                    max_concurrency_total=pool.max_concurrency_total,
                    allocation_ttl_seconds=pool.allocation_ttl_seconds,
                    cooldown_seconds=pool.cooldown_seconds,
                    failure_cooldown_seconds=pool.failure_cooldown_seconds,
                    allow_attach_only=pool.allow_attach_only,
                    close_targets_on_release=pool.close_targets_on_release,
                    close_targets_on_expire=pool.close_targets_on_expire,
                    profile_count=len(pool.profile_names),
                    ready_profile_count=ready_profile_count,
                    missing_profile_names=missing,
                    disabled_profile_names=disabled,
                    attach_only_profile_names=attach_only,
                    active_allocation_count=len(pool_allocations),
                    diagnostics={
                        "ok": status in {"active", "idle", "disabled"},
                        "available_profile_count": available_profile_count,
                        "missing_profiles": missing,
                        "disabled_profiles": disabled,
                        "attach_only_profiles": attach_only,
                        **cooldown_summary,
                    },
                ),
            )
        return tuple(records)

    def list_allocations(self) -> tuple[BrowserProfileAllocationRuntimeRecord, ...]:
        now = datetime.now(timezone.utc)
        records = [
            BrowserProfileAllocationRuntimeRecord(
                allocation_id=allocation.allocation_id,
                pool_id=allocation.pool_id,
                profile_name=allocation.profile_name,
                consumer_kind=allocation.consumer_kind,
                consumer_id=allocation.consumer_id,
                target_host=allocation.target_host,
                status=_allocation_effective_status(allocation, now=now),
                raw_status=allocation.status,
                acquired_at=allocation.acquired_at,
                expires_at=allocation.expires_at,
                last_heartbeat_at=getattr(allocation, "last_heartbeat_at", None),
                released_at=allocation.released_at,
                release_reason=allocation.release_reason,
                owned_target_ids=tuple(getattr(allocation, "owned_target_ids", ()) or ()),
                metadata=dict(allocation.metadata),
            )
            for allocation in self.profile_allocation_store.list_allocations()
        ]
        return tuple(
            sorted(
                records,
                key=lambda item: (item.acquired_at, item.allocation_id),
                reverse=True,
            ),
        )


def _pool_status(
    *,
    enabled: bool,
    missing: tuple[str, ...],
    ready_profile_count: int,
) -> str:
    if not enabled:
        return "disabled"
    if missing or ready_profile_count <= 0:
        return "degraded"
    return "active"


def _allocation_effective_status(allocation: Any, *, now: datetime) -> str:
    if allocation.status == "active" and allocation.expires_at <= now:
        return "expired"
    return str(allocation.status)


def _pool_cooldown_summary(
    *,
    pool: Any,
    allocations: tuple[Any, ...],
    now: datetime,
) -> dict[str, Any]:
    failure_cooldown_profiles: list[str] = []
    release_cooldown_profiles: list[str] = []
    failed_allocation_count = 0
    released_allocation_count = 0
    for allocation in allocations:
        profile_name = str(getattr(allocation, "profile_name", "") or "").strip()
        if not profile_name:
            continue
        released_at = _released_at(allocation)
        status = str(getattr(allocation, "status", "") or "").strip().lower()
        if status == "failed":
            failed_allocation_count += 1
            if _within_cooldown(
                released_at,
                seconds=getattr(pool, "failure_cooldown_seconds", 0),
                now=now,
            ):
                failure_cooldown_profiles.append(profile_name)
        elif status == "released":
            released_allocation_count += 1
            if _within_cooldown(
                released_at,
                seconds=getattr(pool, "cooldown_seconds", 0),
                now=now,
            ):
                release_cooldown_profiles.append(profile_name)
    cooling_profiles = tuple(
        dict.fromkeys([*failure_cooldown_profiles, *release_cooldown_profiles]),
    )
    return {
        "cooling_profiles": cooling_profiles,
        "failure_cooldown_profiles": tuple(dict.fromkeys(failure_cooldown_profiles)),
        "release_cooldown_profiles": tuple(dict.fromkeys(release_cooldown_profiles)),
        "failed_allocation_count": failed_allocation_count,
        "released_allocation_count": released_allocation_count,
    }


def _within_cooldown(
    released_at: datetime | None,
    *,
    seconds: Any,
    now: datetime,
) -> bool:
    if released_at is None:
        return False
    try:
        cooldown_seconds = int(seconds)
    except (TypeError, ValueError):
        cooldown_seconds = 0
    if cooldown_seconds <= 0:
        return False
    return released_at + timedelta(seconds=cooldown_seconds) > now


def _released_at(allocation: Any) -> datetime | None:
    value = getattr(allocation, "released_at", None)
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
