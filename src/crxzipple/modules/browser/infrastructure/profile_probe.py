from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from typing import Callable

from crxzipple.modules.browser.domain import (
    BrowserControlCommand,
    BrowserExecutionPlan,
    BrowserProfileCapabilities,
    BrowserProfileRuntimeState,
    BrowserSystemConfig,
    BrowserValidationError,
    ResolvedBrowserProfile,
)

from .engines import CdpControlEngine
from .engines_cdp_io import has_expected_remote_allow_origins


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
    playwright_probe: Callable[..., None] | None = None

    def probe(
        self,
        *,
        system: BrowserSystemConfig,
        profile: ResolvedBrowserProfile,
        capabilities: BrowserProfileCapabilities,
        runtime_state: BrowserProfileRuntimeState | None = None,
    ) -> dict[str, Any]:
        return self._probe_cdp(
            system=system,
            profile=profile,
            capabilities=capabilities,
            runtime_state=runtime_state,
        )

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
            profile_mismatch = self._local_managed_profile_mismatch(plan=plan)
            if profile_mismatch is not None:
                return {
                    "attempted": True,
                    "ok": False,
                    "status": "cdp-profile-mismatch",
                    "message": (
                        "CDP endpoint responded, but the process on that port does not "
                        "match this managed browser profile. Stop or restart the profile."
                    ),
                    "cdp_base_url": base_url,
                    "browser_ref": browser_ref,
                    "tab_count": len(tabs),
                    **profile_mismatch,
                }
            if (
                callable(self.playwright_probe)
                and capabilities.action_family == "cdp-backed-playwright"
            ):
                try:
                    self.playwright_probe(profile=profile, timeout_ms=2_000)
                except BrowserValidationError as exc:
                    return {
                        "attempted": True,
                        "ok": False,
                        "status": "cdp-playwright-unreachable",
                        "message": (
                            "CDP endpoint responded, but Playwright could not attach. "
                            "Retry or reset this managed profile."
                        ),
                        "raw_message": str(exc),
                        "cdp_base_url": base_url,
                        "browser_ref": browser_ref,
                        "tab_count": len(tabs),
                    }
            return {
                "attempted": True,
                "ok": True,
                "status": "cdp-reachable",
                "message": (
                    "CDP endpoint is reachable."
                    if capabilities.action_family != "cdp-backed-playwright"
                    else "CDP endpoint is reachable and Playwright can attach."
                ),
                "cdp_base_url": base_url,
                "browser_ref": browser_ref,
                "tab_count": len(tabs),
            }
        except BrowserValidationError as exc:
            message = str(exc)
            if capabilities.mode != "local-managed":
                return {
                    "attempted": True,
                    "ok": False,
                    "status": (
                        "cdp-not-configured"
                        if "requires a configured CDP URL or port" in message
                        else "cdp-unreachable"
                    ),
                    "message": message,
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

    def _local_managed_profile_mismatch(
        self,
        *,
        plan: BrowserExecutionPlan,
    ) -> dict[str, Any] | None:
        if plan.capabilities.mode != "local-managed" or plan.profile.cdp_port is None:
            return None
        matching_process = self.cdp_control._find_matching_managed_process(plan=plan)  # noqa: SLF001
        if matching_process is not None:
            if bool(matching_process.get("headless")) == bool(plan.system.headless):
                return None
            return {
                "mismatch_reason": "headless-mode",
                "conflict_pid": matching_process.get("pid"),
            }
        port_process = self.cdp_control._find_process_for_cdp_port(plan=plan)  # noqa: SLF001
        if port_process is None:
            return None
        expected_user_data_dir = self.cdp_control._try_resolve_user_data_dir(plan=plan)  # noqa: SLF001
        port_command = str(port_process.get("command", "")).strip()
        expected_headless = bool(plan.system.headless)
        actual_headless = "--headless" in port_command
        matches_remote_allow_origins = has_expected_remote_allow_origins(
            command=port_command,
            host=plan.system.cdp_host,
            port=int(plan.profile.cdp_port),
        )
        matches_user_data_dir = (
            expected_user_data_dir is not None
            and f"--user-data-dir={expected_user_data_dir}" in port_command
        )
        if matches_user_data_dir and actual_headless == expected_headless and matches_remote_allow_origins:
            return None
        mismatch_fields: list[str] = []
        if not matches_user_data_dir:
            mismatch_fields.append("user_data_dir")
        if actual_headless != expected_headless:
            mismatch_fields.append("headless")
        if not matches_remote_allow_origins:
            mismatch_fields.append("remote_allow_origins")
        return {
            "mismatch_reason": "port-process",
            "mismatch_fields": mismatch_fields,
            "conflict_pid": port_process.get("pid"),
            "expected_user_data_dir": expected_user_data_dir,
        }
