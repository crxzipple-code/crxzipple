from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from crxzipple.modules.browser.domain import (
    BrowserControlCommand,
    BrowserExecutionPlan,
    BrowserProfileCapabilities,
    BrowserProfileRuntimeState,
    BrowserSystemConfig,
    BrowserValidationError,
    ResolvedBrowserProfile,
)

from .chrome_mcp import ChromeMcpClientPool
from .engines import CdpControlEngine


def _normalize_probe_message(value: object) -> str:
    return str(value or "").strip()


def _classify_mcp_failure(message: str) -> tuple[str, str]:
    normalized = message.lower()
    if "could not start command" in normalized:
        return (
            "mcp-command-unavailable",
            "Chrome MCP could not start. Install Node.js/NPX and make sure the configured MCP command is available.",
        )
    if "did not expose list_pages" in normalized or "invalid tools/list payload" in normalized:
        return (
            "mcp-incompatible",
            "Chrome MCP started, but the configured command did not expose the expected browser tools.",
        )
    if (
        "timed out while waiting" in normalized
        or "terminated while waiting" in normalized
        or "terminated unexpectedly" in normalized
        or "session for profile" in normalized
        or "returned an error for method" in normalized
    ):
        return (
            "awaiting-existing-browser",
            "Chrome MCP is available, but it could not attach to a running signed-in Chromium browser session yet.",
        )
    return (
        "mcp-unavailable",
        message or "Chrome MCP is not available for this profile.",
    )


def _probe_launch_policy(
    *,
    profile: ResolvedBrowserProfile,
    capabilities: BrowserProfileCapabilities,
) -> str:
    return "launch-if-missing" if capabilities.can_launch and not profile.attach_only else "attach-only"


def _probe_plan(
    *,
    system: BrowserSystemConfig,
    profile: ResolvedBrowserProfile,
    capabilities: BrowserProfileCapabilities,
) -> BrowserExecutionPlan:
    return BrowserExecutionPlan(
        command=BrowserControlCommand(
            profile_name=profile.name,
            kind="list-tabs",
        ),
        system=system,
        profile=profile,
        capabilities=capabilities,
        control_family=capabilities.control_family,
        action_family=capabilities.action_family,
        launch_policy=_probe_launch_policy(profile=profile, capabilities=capabilities),
        tab_selection_policy="explicit-only",
    )


@dataclass(frozen=True, slots=True)
class BrowserProfileProbeService:
    cdp_control: CdpControlEngine
    mcp_pool: ChromeMcpClientPool

    def probe(
        self,
        *,
        system: BrowserSystemConfig,
        profile: ResolvedBrowserProfile,
        capabilities: BrowserProfileCapabilities,
        runtime_state: BrowserProfileRuntimeState | None = None,
    ) -> dict[str, Any]:
        if capabilities.control_family == "mcp-control":
            return self._probe_mcp(
                system=system,
                profile=profile,
            )
        return self._probe_cdp(
            system=system,
            profile=profile,
            capabilities=capabilities,
            runtime_state=runtime_state,
        )

    def _probe_mcp(
        self,
        *,
        system: BrowserSystemConfig,
        profile: ResolvedBrowserProfile,
    ) -> dict[str, Any]:
        try:
            tabs = self.mcp_pool.list_tabs(
                profile_name=profile.name,
                system=system,
                user_data_dir=profile.user_data_dir,
            )
            return {
                "attempted": True,
                "ok": True,
                "status": "mcp-connected",
                "message": "Chrome MCP can attach to the existing browser session.",
                "pid": self.mcp_pool.get_pid(
                    profile_name=profile.name,
                    system=system,
                    user_data_dir=profile.user_data_dir,
                ),
                "tab_count": len(tabs),
            }
        except BrowserValidationError as exc:
            status, friendly_message = _classify_mcp_failure(_normalize_probe_message(exc))
            return {
                "attempted": True,
                "ok": False,
                "status": status,
                "message": friendly_message,
                "raw_message": _normalize_probe_message(exc),
            }

    def _probe_cdp(
        self,
        *,
        system: BrowserSystemConfig,
        profile: ResolvedBrowserProfile,
        capabilities: BrowserProfileCapabilities,
        runtime_state: BrowserProfileRuntimeState | None,
    ) -> dict[str, Any]:
        plan = _probe_plan(system=system, profile=profile, capabilities=capabilities)
        try:
            payload, base_url = self.cdp_control._request_cdp_json(  # noqa: SLF001
                plan=plan,
                runtime_state=runtime_state,
                path="/json/version",
            )
            tabs = self.cdp_control._list_tab_payloads(plan=plan)  # noqa: SLF001
            browser_ref = None
            if isinstance(payload, dict):
                raw_browser_ref = payload.get("webSocketDebuggerUrl")
                browser_ref = str(raw_browser_ref).strip() if raw_browser_ref else None
            return {
                "attempted": True,
                "ok": True,
                "status": "cdp-reachable",
                "message": "CDP endpoint is reachable.",
                "cdp_base_url": base_url,
                "browser_ref": browser_ref,
                "tab_count": len(tabs),
            }
        except BrowserValidationError as exc:
            if capabilities.mode != "local-managed":
                return {
                    "attempted": True,
                    "ok": False,
                    "status": "cdp-unreachable",
                    "message": str(exc),
                }

        executable_path = None
        executable_error = None
        try:
            executable_path = self.cdp_control._resolve_executable_path(plan=plan)  # noqa: SLF001
        except BrowserValidationError as exc:
            executable_error = str(exc)
        matching_process = self.cdp_control._find_matching_managed_process(plan=plan)  # noqa: SLF001
        port_process = self.cdp_control._find_process_for_cdp_port(plan=plan)  # noqa: SLF001
        user_data_dir = self.cdp_control._try_resolve_user_data_dir(plan=plan)  # noqa: SLF001
        if executable_path is not None:
            return {
                "attempted": True,
                "ok": False,
                "status": "launchable",
                "message": "Managed browser is not attached yet, but local launch prerequisites look valid.",
                "executable_path": executable_path,
                "user_data_dir": user_data_dir,
                "matching_process": matching_process,
                "port_process": port_process,
            }
        return {
            "attempted": True,
            "ok": False,
            "status": "unlaunchable",
            "message": executable_error or "Managed browser launch prerequisites are not satisfied.",
            "user_data_dir": user_data_dir,
            "matching_process": matching_process,
            "port_process": port_process,
        }
