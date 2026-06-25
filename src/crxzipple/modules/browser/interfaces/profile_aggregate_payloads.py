from __future__ import annotations

from typing import Any

from crxzipple.interfaces.runtime_container import AppKey
from crxzipple.modules.browser.domain import BrowserValidationError

from .profile_entry_payloads import (
    build_allocation_entry,
    build_pool_entry,
    build_profile_entry,
)


def build_pools_payload(container: Any) -> dict[str, object]:
    system_config = container.require(AppKey.BROWSER_SYSTEM_CONFIG_STORE).load()
    pools = container.require(AppKey.BROWSER_PROFILE_POOL_SERVICE).list_pools()
    return {
        "default_profile": system_config.default_profile,
        "profile_count": len(system_config.profiles),
        "pools": [
            build_pool_entry(container, pool=pool, system_config=system_config)
            for pool in pools
        ],
    }


def build_allocations_payload(
    container: Any,
    *,
    status: str | None = None,
    pool_id: str | None = None,
    profile_name: str | None = None,
    active_only: bool = False,
) -> dict[str, object]:
    allocations = container.require(
        AppKey.BROWSER_PROFILE_ALLOCATOR_SERVICE
    ).list_allocations(
        status=status,
        pool_id=pool_id,
        profile_name=profile_name,
        active_only=active_only,
    )
    return {
        "allocations": [
            build_allocation_entry(allocation) for allocation in allocations
        ],
        "total": len(allocations),
    }


def build_profiles_payload(
    container: Any, system_config: Any | None = None
) -> dict[str, object]:
    settings = container.require(AppKey.CORE_SETTINGS)
    system_config = (
        system_config or container.require(AppKey.BROWSER_SYSTEM_CONFIG_STORE).load()
    )
    return {
        "enabled": settings.browser_enabled,
        "default_profile": system_config.default_profile,
        "managed_tab_limit": system_config.managed_tab_limit,
        "profiles": [
            build_profile_entry(
                container,
                system_config=system_config,
                profile=profile,
            )
            for profile in system_config.profiles
        ],
    }


def build_profile_diagnostics_payload(
    container: Any,
    *,
    profile_name: str,
    system_config: Any | None = None,
) -> dict[str, object]:
    settings = container.require(AppKey.CORE_SETTINGS)
    system_config = (
        system_config or container.require(AppKey.BROWSER_SYSTEM_CONFIG_STORE).load()
    )
    normalized = profile_name.strip().lower()
    for profile in system_config.profiles:
        if profile.name == normalized:
            return {
                "enabled": settings.browser_enabled,
                "default_profile": system_config.default_profile,
                "profile": build_profile_entry(
                    container,
                    system_config=system_config,
                    profile=profile,
                    probe=True,
                ),
            }
    raise BrowserValidationError(f"Browser profile '{profile_name}' is not configured.")
