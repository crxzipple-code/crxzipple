from __future__ import annotations

from typing import Any

from crxzipple.interfaces.runtime_container import AppKey
from crxzipple.modules.browser.application.runtime_payloads import (
    browser_runtime_status_payload,
)


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
        fields["proxy_credential_kind"] = getattr(
            profile, "proxy_credential_kind", "basic"
        )
    changed: list[str] = []
    for field_name, expected in fields.items():
        observed = daemon_metadata.get(field_name)
        if _same_optional_value(expected, observed):
            continue
        changed.append(field_name)
    user_data_dir = getattr(profile, "user_data_dir", None)
    observed_user_data_dir = daemon_metadata.get("user_data_dir")
    if (
        user_data_dir
        and observed_user_data_dir
        and str(user_data_dir) != str(observed_user_data_dir)
    ):
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


def _profile_diagnostics(
    *, profile: Any, capabilities: Any, runtime_state: Any
) -> dict[str, Any]:
    attachment_status = (
        getattr(runtime_state, "attachment_status", "idle")
        if runtime_state is not None
        else "idle"
    )
    last_error = (
        getattr(runtime_state, "last_error", None)
        if runtime_state is not None
        else None
    )
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
            "message": last_error
            or "Browser connection is degraded and may need recovery.",
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
        return {
            "code": "restart-needed",
            "label": "Restart needed",
            "severity": "warning",
        }
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
