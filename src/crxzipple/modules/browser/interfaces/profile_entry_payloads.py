from __future__ import annotations

from typing import Any

from crxzipple.interfaces.runtime_container import AppKey
from crxzipple.modules.browser.application.runtime_payloads import (
    browser_runtime_state_applies_to_profile,
)

from .profile_diagnostics_payloads import (
    _apply_probe_to_diagnostics,
    _apply_restart_needed_to_diagnostics,
    _daemon_metadata_for_profile,
    _diagnostics_summary,
    _diagnostics_summary_line,
    _profile_diagnostics,
    _profile_runtime_config_drift,
    _runtime_state_payload,
)


def build_profile_entry(
    container: Any,
    *,
    system_config: Any,
    profile: Any,
    probe: bool = False,
) -> dict[str, Any]:
    browser = container.require(AppKey.BROWSER_INFRASTRUCTURE)
    resolved = browser.profile_resolver.resolve(
        system=system_config,
        profile_name=profile.name,
    )
    capabilities = browser.capabilities_resolver.resolve(profile=resolved)
    runtime_state = browser.runtime_state_store.get(profile_name=profile.name)
    if not browser_runtime_state_applies_to_profile(
        runtime_state,
        resolved_profile=resolved,
    ):
        runtime_state = None
    diagnostics = _profile_diagnostics(
        profile=profile,
        capabilities=capabilities,
        runtime_state=runtime_state,
    )
    probe_service = getattr(browser, "profile_probe_service", None)
    if probe and probe_service is not None and bool(getattr(profile, "enabled", True)):
        probe_payload = probe_service.probe(
            system=system_config,
            profile=resolved,
            capabilities=capabilities,
            runtime_state=runtime_state,
        )
        diagnostics = _apply_probe_to_diagnostics(
            diagnostics=diagnostics,
            probe=probe_payload,
            profile=profile,
            capabilities=capabilities,
        )
    diagnostics = _apply_restart_needed_to_diagnostics(
        diagnostics=diagnostics,
        restart_fields=_profile_runtime_config_drift(
            profile=profile,
            runtime_state=runtime_state,
            daemon_metadata=_daemon_metadata_for_profile(container, profile.name),
        ),
    )
    summary = _diagnostics_summary(diagnostics)
    return {
        "name": profile.name,
        "driver": profile.driver,
        "enabled": bool(getattr(profile, "enabled", True)),
        "attach_only": profile.attach_only,
        "configured_cdp_url": profile.cdp_url,
        "configured_cdp_port": profile.cdp_port,
        "user_data_dir": profile.user_data_dir,
        "profile_directory": getattr(profile, "profile_directory", None),
        "autostart": getattr(profile, "autostart", False),
        "proxy": {
            "mode": getattr(profile, "proxy_mode", "none"),
            "server": getattr(profile, "proxy_server", None),
            "bypass_list": list(getattr(profile, "proxy_bypass_list", ())),
            "binding_id": getattr(profile, "proxy_binding_id", None),
            "credential_kind": getattr(profile, "proxy_credential_kind", "basic"),
        },
        "close_targets_on_release": getattr(profile, "close_targets_on_release", True),
        "close_targets_on_expire": getattr(profile, "close_targets_on_expire", True),
        "resolved_cdp_url": resolved.cdp_url,
        "resolved_cdp_port": resolved.cdp_port,
        "mode": capabilities.mode,
        "control_family": capabilities.control_family,
        "action_family": capabilities.action_family,
        "is_remote": capabilities.is_remote,
        "supports_reset": capabilities.supports_reset,
        "supports_per_tab_ws": capabilities.supports_per_tab_ws,
        "supports_json_tab_endpoints": capabilities.supports_json_tab_endpoints,
        "supports_managed_tab_limit": capabilities.supports_managed_tab_limit,
        "runtime": _runtime_state_payload(runtime_state),
        "diagnostics": {
            **diagnostics,
            "summary": summary,
            "summary_line": _diagnostics_summary_line(summary, diagnostics),
        },
    }


def build_pool_entry(
    container: Any,
    *,
    pool: Any,
    system_config: Any | None = None,
) -> dict[str, Any]:
    system_config = (
        system_config or container.require(AppKey.BROWSER_SYSTEM_CONFIG_STORE).load()
    )
    profiles = {profile.name: profile for profile in system_config.profiles}
    missing_profiles = [
        profile_name
        for profile_name in pool.profile_names
        if profile_name not in profiles
    ]
    disabled_profiles = [
        profile_name
        for profile_name in pool.profile_names
        if profile_name in profiles
        and not bool(getattr(profiles[profile_name], "enabled", True))
    ]
    attach_only_profiles = [
        profile_name
        for profile_name in pool.profile_names
        if profile_name in profiles
        and (
            bool(getattr(profiles[profile_name], "attach_only", False))
            or getattr(profiles[profile_name], "driver", None) == "existing-session"
        )
    ]
    eligible_profiles = [
        profile_name
        for profile_name in pool.profile_names
        if profile_name not in missing_profiles
        and profile_name not in disabled_profiles
        and (pool.allow_attach_only or profile_name not in attach_only_profiles)
    ]
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
        "health_policy": dict(pool.health_policy),
        "metadata": dict(pool.metadata),
        "profile_count": len(pool.profile_names),
        "eligible_profile_count": len(eligible_profiles),
        "missing_profiles": missing_profiles,
        "disabled_profiles": disabled_profiles,
        "attach_only_profiles": attach_only_profiles,
        "ready": bool(pool.enabled and eligible_profiles and not missing_profiles),
    }


def build_allocation_entry(allocation: Any) -> dict[str, Any]:
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
            if getattr(allocation, "last_heartbeat_at", None) is not None
            else None
        ),
        "released_at": (
            allocation.released_at.isoformat()
            if allocation.released_at is not None
            else None
        ),
        "release_reason": allocation.release_reason,
        "owned_target_ids": list(getattr(allocation, "owned_target_ids", ()) or ()),
        "metadata": dict(allocation.metadata),
    }
