from __future__ import annotations

from typing import Any

from crxzipple.interfaces.runtime_container import AppKey
from crxzipple.modules.browser.application.runtime_payloads import (
    browser_runtime_state_applies_to_profile,
    browser_runtime_status_payload,
)
from crxzipple.modules.browser.domain import BrowserValidationError


def _runtime_state_payload(runtime_state: Any) -> dict[str, Any] | None:
    if runtime_state is None:
        return None
    return browser_runtime_status_payload(runtime_state)


def _daemon_metadata_for_profile(container: Any, profile_name: str) -> dict[str, Any]:
    try:
        daemon_manager = container.require(AppKey.DAEMON_MANAGER)
    except Exception:
        return {}
    list_instances = getattr(daemon_manager, "list_instances", None)
    if not callable(list_instances):
        return {}
    service_key = f"host:browser:{profile_name}"
    try:
        instances = list_instances(service_key=service_key, refresh=False)
    except TypeError:
        try:
            instances = list_instances(refresh=False)
        except TypeError:
            instances = list_instances()
    except Exception:
        return {}
    matching = tuple(
        instance
        for instance in instances or ()
        if getattr(instance, "service_key", None) == service_key
    )
    instance = _preferred_daemon_instance(matching)
    if instance is None:
        return {}
    metadata = getattr(instance, "metadata", None)
    return dict(metadata) if isinstance(metadata, dict) else {}


def _preferred_daemon_instance(instances: tuple[Any, ...]) -> Any | None:
    if not instances:
        return None
    return max(instances, key=_daemon_instance_sort_key)


def _daemon_instance_sort_key(instance: Any) -> tuple[int, str, str]:
    status = str(getattr(instance, "status", "") or "").strip().lower()
    status_rank = {
        "ready": 5,
        "starting": 4,
        "degraded": 3,
        "stopping": 2,
        "failed": 1,
        "stopped": 0,
    }.get(status, 0)
    last_healthcheck = getattr(instance, "last_healthcheck_at", None)
    started_at = getattr(instance, "started_at", None)
    return (
        status_rank,
        last_healthcheck.isoformat() if hasattr(last_healthcheck, "isoformat") else "",
        started_at.isoformat() if hasattr(started_at, "isoformat") else "",
    )


def _profile_runtime_config_drift(
    *,
    profile: Any,
    runtime_state: Any,
    daemon_metadata: dict[str, Any],
) -> tuple[str, ...]:
    if runtime_state is None or not daemon_metadata:
        return ()
    if getattr(runtime_state, "attachment_status", None) not in {
        "attached",
        "degraded",
        "recovering",
    }:
        return ()
    proxy_mode = getattr(profile, "proxy_mode", "none")
    fields = {
        "cdp_url": getattr(profile, "cdp_url", None),
        "cdp_port": getattr(profile, "cdp_port", None),
        "profile_directory": getattr(profile, "profile_directory", None),
        "proxy_mode": proxy_mode,
    }
    if proxy_mode == "static":
        fields["proxy_server"] = getattr(profile, "proxy_server", None)
    if proxy_mode == "access_binding":
        fields["proxy_binding_id"] = getattr(profile, "proxy_binding_id", None)
        fields["proxy_credential_kind"] = getattr(profile, "proxy_credential_kind", "basic")
    changed: list[str] = []
    for field_name, expected in fields.items():
        observed = daemon_metadata.get(field_name)
        if _same_optional_value(expected, observed):
            continue
        changed.append(field_name)
    user_data_dir = getattr(profile, "user_data_dir", None)
    observed_user_data_dir = daemon_metadata.get("user_data_dir")
    if user_data_dir and observed_user_data_dir and str(user_data_dir) != str(observed_user_data_dir):
        changed.append("user_data_dir")
    return tuple(changed)


def _same_optional_value(expected: Any, observed: Any) -> bool:
    if expected in {None, "", "none"} and observed in {None, "", "none"}:
        return True
    return str(expected) == str(observed)


def _apply_restart_needed_to_diagnostics(
    *,
    diagnostics: dict[str, Any],
    restart_fields: tuple[str, ...],
) -> dict[str, Any]:
    if not restart_fields:
        return diagnostics
    updated = dict(diagnostics)
    updated["ready"] = True
    updated["status"] = "restart-needed"
    updated["message"] = (
        "Browser profile configuration changed after this host started. "
        "Restart the profile to apply the new settings."
    )
    updated["recommended_action"] = "restart-profile"
    updated["restart_needed"] = True
    updated["restart_fields"] = list(restart_fields)
    return updated


def _profile_diagnostics(*, profile: Any, capabilities: Any, runtime_state: Any) -> dict[str, Any]:
    attachment_status = getattr(runtime_state, "attachment_status", "idle") if runtime_state is not None else "idle"
    last_error = getattr(runtime_state, "last_error", None) if runtime_state is not None else None
    uses_existing_session = getattr(profile, "driver", None) == "existing-session"
    is_remote = bool(getattr(capabilities, "is_remote", False))
    enabled = bool(getattr(profile, "enabled", True))

    login_behavior = "isolated-profile"
    if uses_existing_session:
        login_behavior = "existing-session"
    elif is_remote:
        login_behavior = "remote-browser"

    if not enabled:
        return {
            "ready": False,
            "status": "disabled",
            "message": "Browser profile is disabled and will not accept browser actions.",
            "recommended_action": "enable-profile",
            "login_behavior": login_behavior,
            "can_reuse_personal_login_state": uses_existing_session,
        }

    if attachment_status == "attached":
        if uses_existing_session:
            message = "Attached to an existing browser session and can reuse its current login state."
        elif is_remote:
            message = "Attached to the configured remote CDP browser."
        else:
            message = "Managed browser is attached. Login state is stored inside this isolated profile."
        return {
            "ready": True,
            "status": "ready",
            "message": message,
            "recommended_action": "use-profile",
            "login_behavior": login_behavior,
            "can_reuse_personal_login_state": uses_existing_session,
        }

    if attachment_status in {"attaching", "recovering"}:
        return {
            "ready": False,
            "status": "connecting",
            "message": "Browser attachment is in progress.",
            "recommended_action": "wait-and-retry",
            "login_behavior": login_behavior,
            "can_reuse_personal_login_state": uses_existing_session,
        }

    if attachment_status == "degraded":
        return {
            "ready": False,
            "status": "degraded",
            "message": last_error or "Browser connection is degraded and may need recovery.",
            "recommended_action": "retry-action",
            "login_behavior": login_behavior,
            "can_reuse_personal_login_state": uses_existing_session,
        }

    if attachment_status == "failed":
        if uses_existing_session:
            default_message = (
                "Could not attach to your existing Chromium browser session. "
                "Open it with remote debugging enabled and retry."
            )
            recommended_action = "open-signed-in-browser-and-retry"
        elif is_remote:
            default_message = "Could not reach the configured remote CDP endpoint."
            recommended_action = "verify-remote-cdp-url"
        else:
            default_message = "Managed browser launch or attachment failed."
            recommended_action = "retry-or-reset-profile"
        return {
            "ready": False,
            "status": "error",
            "message": last_error or default_message,
            "recommended_action": recommended_action,
            "login_behavior": login_behavior,
            "can_reuse_personal_login_state": uses_existing_session,
        }

    if attachment_status == "closed":
        if uses_existing_session:
            message = "Existing-session profile is closed. Open your signed-in browser and run a browser action to reattach."
            recommended_action = "open-signed-in-browser-and-retry"
        elif is_remote:
            message = "Remote CDP profile is closed. Reconnect before use."
            recommended_action = "verify-remote-cdp-url"
        else:
            message = "Managed profile is closed and will relaunch on first use."
            recommended_action = "run-open-tab"
        return {
            "ready": False,
            "status": "closed",
            "message": message,
            "recommended_action": recommended_action,
            "login_behavior": login_behavior,
            "can_reuse_personal_login_state": uses_existing_session,
        }

    if uses_existing_session:
        return {
            "ready": False,
            "status": "awaiting-existing-browser",
            "message": (
                "This profile uses your already signed-in Chromium browser. "
                "Open that browser and keep it running, then run a browser action to attach."
            ),
            "recommended_action": "open-signed-in-browser-and-retry",
            "login_behavior": login_behavior,
            "can_reuse_personal_login_state": True,
        }

    if is_remote:
        return {
            "ready": False,
            "status": "awaiting-remote-cdp",
            "message": "This profile expects an existing remote CDP endpoint and will attach when that endpoint is reachable.",
            "recommended_action": "verify-remote-cdp-url",
            "login_behavior": login_behavior,
            "can_reuse_personal_login_state": False,
        }

    return {
        "ready": False,
        "status": "ready-to-launch",
        "message": (
            "This managed profile is isolated from your everyday browser. "
            "A separate browser window will launch on first use, and any login state will live inside this profile."
        ),
        "recommended_action": "run-open-tab",
        "login_behavior": login_behavior,
        "can_reuse_personal_login_state": False,
    }


def _apply_probe_to_diagnostics(
    *,
    diagnostics: dict[str, Any],
    probe: dict[str, Any] | None,
    profile: Any,
    capabilities: Any,
) -> dict[str, Any]:
    if probe is None:
        return diagnostics

    updated = dict(diagnostics)
    updated["probe"] = probe
    if not probe.get("attempted"):
        return updated

    uses_existing_session = getattr(profile, "driver", None) == "existing-session"
    is_remote = bool(getattr(capabilities, "is_remote", False))
    probe_ok = bool(probe.get("ok"))
    probe_status = str(probe.get("status", "")).strip().lower()
    probe_message = str(probe.get("message", "")).strip() or updated["message"]

    if probe_ok:
        updated["ready"] = True
        updated["status"] = "ready"
        updated["message"] = probe_message
        updated["recommended_action"] = "use-profile"
        return updated

    updated["ready"] = False
    updated["message"] = probe_message
    if uses_existing_session:
        if probe_status == "cdp-not-configured":
            updated["status"] = "awaiting-existing-browser"
            updated["recommended_action"] = "configure-cdp-endpoint"
            return updated
        if probe_status == "awaiting-existing-browser":
            updated["status"] = "awaiting-existing-browser"
            updated["recommended_action"] = "open-signed-in-browser-and-retry"
            return updated
        if probe_status == "cdp-unreachable":
            updated["status"] = "awaiting-existing-browser"
            updated["recommended_action"] = "open-signed-in-browser-and-retry"
            return updated
        if probe_status == "cdp-playwright-unreachable":
            updated["status"] = "error"
            updated["recommended_action"] = "retry-or-check-cdp"
            return updated
        updated["status"] = "error"
        updated["recommended_action"] = "retry-or-check-cdp"
        return updated
    if is_remote:
        updated["status"] = "error"
        updated["recommended_action"] = "verify-remote-cdp-url"
        return updated
    if probe_status == "cdp-profile-mismatch":
        updated["status"] = "error"
        updated["recommended_action"] = "restart-profile"
        return updated
    if probe_status == "cdp-playwright-unreachable":
        updated["status"] = "error"
        updated["recommended_action"] = "retry-or-reset-profile"
        return updated
    if probe_status == "launchable":
        updated["status"] = "ready-to-launch"
        updated["recommended_action"] = "run-open-tab"
        return updated
    updated["status"] = "error"
    updated["recommended_action"] = "configure-browser-executable"
    return updated


def _diagnostics_summary(diagnostics: dict[str, Any]) -> dict[str, Any]:
    status = str(diagnostics.get("status", "")).strip().lower()
    probe = diagnostics.get("probe")
    probe_status = ""
    if isinstance(probe, dict):
        probe_status = str(probe.get("status", "")).strip().lower()

    if status == "ready":
        return {"code": "ready", "label": "Ready", "severity": "ok"}
    if status == "restart-needed":
        return {"code": "restart-needed", "label": "Restart needed", "severity": "warning"}
    if status == "connecting":
        return {"code": "connecting", "label": "Connecting", "severity": "info"}
    if status == "degraded":
        return {"code": "degraded", "label": "Degraded", "severity": "warning"}
    if status == "closed":
        return {"code": "closed", "label": "Closed", "severity": "info"}
    if status == "disabled":
        return {"code": "disabled", "label": "Disabled", "severity": "warning"}
    if status == "awaiting-existing-browser":
        return {
            "code": "waiting-browser",
            "label": "Waiting for browser",
            "severity": "warning",
        }
    if status == "awaiting-remote-cdp":
        return {
            "code": "waiting-remote-cdp",
            "label": "Waiting for remote CDP",
            "severity": "warning",
        }
    if status == "ready-to-launch":
        return {"code": "launchable", "label": "Launchable", "severity": "info"}
    if status == "error":
        if probe_status == "legacy-browser-bridge-retired":
            return {
                "code": "browser-legacy-bridge-retired",
                "label": "Legacy browser bridge retired",
                "severity": "error",
            }
        if probe_status in {"cdp-unreachable", "cdp-playwright-unreachable"}:
            return {
                "code": "bad-cdp-endpoint",
                "label": "Bad CDP endpoint",
                "severity": "error",
            }
        if probe_status == "cdp-profile-mismatch":
            return {
                "code": "profile-mismatch",
                "label": "Profile mismatch",
                "severity": "error",
            }
        return {"code": "error", "label": "Error", "severity": "error"}
    return {"code": "unknown", "label": "Unknown", "severity": "warning"}


def _diagnostics_summary_line(
    summary: dict[str, Any],
    diagnostics: dict[str, Any],
) -> str:
    label = str(summary.get("label", "Unknown")).strip() or "Unknown"
    message = str(diagnostics.get("message", "")).strip()
    if not message:
        return label
    return f"{label}: {message}"


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
        system_config
        or container.require(AppKey.BROWSER_SYSTEM_CONFIG_STORE).load()
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


def build_allocations_payload(
    container: Any,
    *,
    status: str | None = None,
    pool_id: str | None = None,
    profile_name: str | None = None,
    active_only: bool = False,
) -> dict[str, object]:
    allocations = container.require(AppKey.BROWSER_PROFILE_ALLOCATOR_SERVICE).list_allocations(
        status=status,
        pool_id=pool_id,
        profile_name=profile_name,
        active_only=active_only,
    )
    return {
        "allocations": [build_allocation_entry(allocation) for allocation in allocations],
        "total": len(allocations),
    }


def build_profiles_payload(container: Any, system_config: Any | None = None) -> dict[str, object]:
    settings = container.require(AppKey.CORE_SETTINGS)
    system_config = (
        system_config
        or container.require(AppKey.BROWSER_SYSTEM_CONFIG_STORE).load()
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
        system_config
        or container.require(AppKey.BROWSER_SYSTEM_CONFIG_STORE).load()
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
