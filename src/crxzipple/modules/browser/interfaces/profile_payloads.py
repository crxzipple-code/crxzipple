from __future__ import annotations

from typing import Any

from crxzipple.modules.browser.domain import BrowserValidationError


def _runtime_state_payload(runtime_state: Any) -> dict[str, Any] | None:
    if runtime_state is None:
        return None
    return {
        "attachment_status": getattr(runtime_state, "attachment_status", "idle"),
        "browser_ref": getattr(runtime_state, "browser_ref", None),
        "running_pid": getattr(runtime_state, "running_pid", None),
        "last_target_id": getattr(runtime_state, "last_target_id", None),
        "last_error": getattr(runtime_state, "last_error", None),
    }


def _profile_diagnostics(*, profile: Any, capabilities: Any, runtime_state: Any) -> dict[str, Any]:
    attachment_status = getattr(runtime_state, "attachment_status", "idle") if runtime_state is not None else "idle"
    last_error = getattr(runtime_state, "last_error", None) if runtime_state is not None else None
    uses_existing_session = getattr(profile, "driver", None) == "existing-session"
    is_remote = bool(getattr(capabilities, "is_remote", False))

    login_behavior = "isolated-profile"
    if uses_existing_session:
        login_behavior = "existing-session"
    elif is_remote:
        login_behavior = "remote-browser"

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
                "Open a signed-in Chromium browser and make sure Chrome MCP can connect."
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
        if probe_status == "awaiting-existing-browser":
            updated["status"] = "awaiting-existing-browser"
            updated["recommended_action"] = "open-signed-in-browser-and-retry"
            return updated
        if probe_status == "mcp-command-unavailable":
            updated["status"] = "error"
            updated["recommended_action"] = "install-or-configure-chrome-mcp"
            return updated
        if probe_status == "mcp-incompatible":
            updated["status"] = "error"
            updated["recommended_action"] = "verify-mcp-command"
            return updated
        updated["status"] = "error"
        updated["recommended_action"] = "retry-or-check-mcp"
        return updated
    if is_remote:
        updated["status"] = "error"
        updated["recommended_action"] = "verify-remote-cdp-url"
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
    if status == "connecting":
        return {"code": "connecting", "label": "Connecting", "severity": "info"}
    if status == "degraded":
        return {"code": "degraded", "label": "Degraded", "severity": "warning"}
    if status == "closed":
        return {"code": "closed", "label": "Closed", "severity": "info"}
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
        if probe_status in {"mcp-command-unavailable", "mcp-incompatible"}:
            return {
                "code": "bad-mcp-command",
                "label": "Bad MCP command",
                "severity": "error",
            }
        if probe_status in {"cdp-unreachable", "cdp-playwright-unreachable"}:
            return {
                "code": "bad-cdp-endpoint",
                "label": "Bad CDP endpoint",
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
    resolved = container.browser_profile_resolver.resolve(
        system=system_config,
        profile_name=profile.name,
    )
    capabilities = container.browser_capabilities_resolver.resolve(profile=resolved)
    runtime_state_store = getattr(container, "browser_runtime_state_store", None)
    runtime_state = None
    if runtime_state_store is not None:
        runtime_state = runtime_state_store.get(profile_name=profile.name)
    diagnostics = _profile_diagnostics(
        profile=profile,
        capabilities=capabilities,
        runtime_state=runtime_state,
    )
    if probe:
        probe_service = getattr(container, "browser_profile_probe_service", None)
        if probe_service is not None:
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
    summary = _diagnostics_summary(diagnostics)
    return {
        "name": profile.name,
        "driver": profile.driver,
        "attach_only": profile.attach_only,
        "configured_cdp_url": profile.cdp_url,
        "configured_cdp_port": profile.cdp_port,
        "user_data_dir": profile.user_data_dir,
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


def build_profiles_payload(container: Any, system_config: Any | None = None) -> dict[str, object]:
    system_config = system_config or container.browser_system_config_store.load()
    return {
        "enabled": getattr(container.settings, "browser_enabled", True),
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
    system_config = system_config or container.browser_system_config_store.load()
    normalized = profile_name.strip().lower()
    for profile in system_config.profiles:
        if profile.name == normalized:
            return {
                "enabled": getattr(container.settings, "browser_enabled", True),
                "default_profile": system_config.default_profile,
                "profile": build_profile_entry(
                    container,
                    system_config=system_config,
                    profile=profile,
                    probe=True,
                ),
            }
    raise BrowserValidationError(f"Browser profile '{profile_name}' is not configured.")
