from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, get_args
from urllib.parse import urlsplit

from crxzipple.modules.browser.domain import (
    BrowserActionTarget,
    BrowserCommand,
    BrowserControlCommand,
    BrowserControlKind,
    BrowserExecutionPlan,
    BrowserPageActionCommand,
    BrowserPageActionKind,
    BrowserProfileCapabilities,
    BrowserProfileRuntimeState,
    BrowserSystemConfig,
    BrowserTab,
    BrowserValidationError,
    ResolvedBrowserProfile,
)

from .ports import (
    BrowserAllocationTargetInspector,
    BrowserAllocationTargetRecycler,
    BrowserCapabilitiesResolver,
    BrowserControlCommandAssembler,
    BrowserExecutionCoordinator,
    BrowserExecutionPlanner,
    BrowserPageActionAssembler,
    BrowserProfileResolver,
    BrowserProfileSelectionOps,
    BrowserProfileSelectionOpsFactory,
    BrowserProfileTabOps,
    BrowserProfileTabOpsFactory,
)

_ALLOWED_CONTROL_KINDS = frozenset(get_args(BrowserControlKind))
_ALLOWED_PAGE_ACTION_KINDS = frozenset(get_args(BrowserPageActionKind))
_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


def _normalize_control_kind(value: str) -> str:
    normalized = value.strip().lower()
    if normalized not in _ALLOWED_CONTROL_KINDS:
        raise BrowserValidationError(
            f"Unsupported browser control kind '{value}'.",
        )
    return normalized


def _normalize_page_action_kind(value: str) -> str:
    normalized = value.strip().lower()
    if normalized not in _ALLOWED_PAGE_ACTION_KINDS:
        raise BrowserValidationError(
            f"Unsupported browser page action kind '{value}'.",
        )
    return normalized


def _normalize_url(value: str, *, label: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise BrowserValidationError(f"{label} is required.")
    parsed = urlsplit(normalized)
    if parsed.scheme not in {"http", "https", "ws", "wss"}:
        raise BrowserValidationError(
            f"{label} must use http, https, ws, or wss.",
        )
    if not parsed.hostname:
        raise BrowserValidationError(f"{label} must include a host.")
    if parsed.port is None:
        raise BrowserValidationError(f"{label} must include an explicit port.")
    return normalized.rstrip("/")


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _compose_cdp_url(system: BrowserSystemConfig, cdp_port: int) -> str:
    return f"http://{system.cdp_host}:{cdp_port}"


@dataclass(frozen=True, slots=True)
class DefaultBrowserProfileResolver(BrowserProfileResolver):
    def resolve(
        self,
        *,
        system: BrowserSystemConfig,
        profile_name: str,
    ) -> ResolvedBrowserProfile:
        normalized_name = profile_name.strip().lower()
        profiles = {profile.name: profile for profile in system.profiles}
        profile = profiles.get(normalized_name)
        if profile is None:
            raise BrowserValidationError(
                f"Browser profile '{profile_name}' is not configured.",
            )

        if profile.cdp_url is not None:
            normalized_url = _normalize_url(profile.cdp_url, label="cdp_url")
            parsed = urlsplit(normalized_url)
            return ResolvedBrowserProfile(
                name=profile.name,
                driver=profile.driver,
                cdp_url=normalized_url,
                cdp_port=parsed.port,
                user_data_dir=profile.user_data_dir,
                attach_only=profile.attach_only,
                is_loopback=(parsed.hostname or "").lower() in _LOOPBACK_HOSTS,
                enabled=profile.enabled,
                profile_directory=profile.profile_directory,
                autostart=profile.autostart,
                proxy_mode=profile.proxy_mode,
                proxy_server=profile.proxy_server,
                proxy_bypass_list=profile.proxy_bypass_list,
                proxy_binding_id=profile.proxy_binding_id,
                proxy_credential_kind=profile.proxy_credential_kind,
            )

        if profile.cdp_port is not None:
            return ResolvedBrowserProfile(
                name=profile.name,
                driver=profile.driver,
                cdp_url=_compose_cdp_url(system, profile.cdp_port),
                cdp_port=profile.cdp_port,
                user_data_dir=profile.user_data_dir,
                attach_only=profile.attach_only,
                is_loopback=system.cdp_host.lower() in _LOOPBACK_HOSTS,
                enabled=profile.enabled,
                profile_directory=profile.profile_directory,
                autostart=profile.autostart,
                proxy_mode=profile.proxy_mode,
                proxy_server=profile.proxy_server,
                proxy_bypass_list=profile.proxy_bypass_list,
                proxy_binding_id=profile.proxy_binding_id,
                proxy_credential_kind=profile.proxy_credential_kind,
            )

        if profile.driver == "existing-session":
            return ResolvedBrowserProfile(
                name=profile.name,
                driver=profile.driver,
                cdp_url=None,
                cdp_port=None,
                user_data_dir=profile.user_data_dir,
                attach_only=profile.attach_only,
                is_loopback=False,
                enabled=profile.enabled,
                profile_directory=profile.profile_directory,
                autostart=profile.autostart,
                proxy_mode=profile.proxy_mode,
                proxy_server=profile.proxy_server,
                proxy_bypass_list=profile.proxy_bypass_list,
                proxy_binding_id=profile.proxy_binding_id,
                proxy_credential_kind=profile.proxy_credential_kind,
            )

        ordered_names = [configured.name for configured in system.profiles]
        try:
            profile_index = ordered_names.index(profile.name)
        except ValueError as exc:
            raise BrowserValidationError(
                f"Browser profile '{profile.name}' is missing from system profile order.",
            ) from exc
        allocated_port = system.cdp_port_range_start + profile_index
        if allocated_port > system.cdp_port_range_end:
            raise BrowserValidationError(
                f"Browser profile '{profile.name}' exceeds configured CDP port range.",
            )
        return ResolvedBrowserProfile(
            name=profile.name,
            driver=profile.driver,
            cdp_url=_compose_cdp_url(system, allocated_port),
            cdp_port=allocated_port,
            user_data_dir=profile.user_data_dir,
            attach_only=profile.attach_only,
            is_loopback=system.cdp_host.lower() in _LOOPBACK_HOSTS,
            enabled=profile.enabled,
            profile_directory=profile.profile_directory,
            autostart=profile.autostart,
            proxy_mode=profile.proxy_mode,
            proxy_server=profile.proxy_server,
            proxy_bypass_list=profile.proxy_bypass_list,
            proxy_binding_id=profile.proxy_binding_id,
            proxy_credential_kind=profile.proxy_credential_kind,
        )


@dataclass(frozen=True, slots=True)
class DefaultBrowserCapabilitiesResolver(BrowserCapabilitiesResolver):
    def resolve(
        self,
        *,
        profile: ResolvedBrowserProfile,
    ) -> BrowserProfileCapabilities:
        if profile.driver == "existing-session":
            return BrowserProfileCapabilities(
                mode="local-existing-session",
                is_remote=False,
                control_family="cdp-control",
                action_family="cdp-backed-playwright",
                can_launch=False,
                supports_reset=False,
                supports_per_tab_ws=True,
                supports_json_tab_endpoints=True,
                supports_managed_tab_limit=False,
            )

        if not profile.is_loopback:
            return BrowserProfileCapabilities(
                mode="remote-cdp",
                is_remote=True,
                control_family="cdp-control",
                action_family="cdp-backed-playwright",
                can_launch=False,
                supports_reset=False,
                supports_per_tab_ws=False,
                supports_json_tab_endpoints=False,
                supports_managed_tab_limit=False,
            )

        return BrowserProfileCapabilities(
            mode="local-managed",
            is_remote=False,
            control_family="cdp-control",
            action_family="cdp-backed-playwright",
            can_launch=not profile.attach_only,
            supports_reset=not profile.attach_only,
            supports_per_tab_ws=True,
            supports_json_tab_endpoints=True,
            supports_managed_tab_limit=True,
        )


@dataclass(frozen=True, slots=True)
class DefaultBrowserControlCommandAssembler(BrowserControlCommandAssembler):
    def assemble(
        self,
        *,
        profile_name: str,
        kind: str,
        target_id: str | None = None,
        payload: Mapping[str, Any] | None = None,
        timeout_ms: int | None = None,
    ) -> BrowserControlCommand:
        return BrowserControlCommand(
            profile_name=profile_name,
            kind=_normalize_control_kind(kind),
            target_id=target_id,
            payload=dict(payload or {}),
            timeout_ms=timeout_ms,
        )


@dataclass(frozen=True, slots=True)
class DefaultBrowserPageActionAssembler(BrowserPageActionAssembler):
    def assemble(
        self,
        *,
        profile_name: str,
        kind: str,
        target_id: str | None = None,
        ref: str | None = None,
        selector: str | None = None,
        payload: Mapping[str, Any] | None = None,
        timeout_ms: int | None = None,
    ) -> BrowserPageActionCommand:
        return BrowserPageActionCommand(
            profile_name=profile_name,
            kind=_normalize_page_action_kind(kind),
            target=BrowserActionTarget(
                target_id=target_id,
                ref=ref,
                selector=selector,
            ),
            payload=dict(payload or {}),
            timeout_ms=timeout_ms,
        )


@dataclass(frozen=True, slots=True)
class DefaultBrowserExecutionPlanner(BrowserExecutionPlanner):
    def plan(
        self,
        *,
        system: BrowserSystemConfig,
        profile: ResolvedBrowserProfile,
        capabilities: BrowserProfileCapabilities,
        command: BrowserCommand,
    ) -> BrowserExecutionPlan:
        launch_policy = (
            "launch-if-missing"
            if capabilities.can_launch and not profile.attach_only
            else "attach-only"
        )
        tab_selection_policy = (
            "explicit-only"
            if isinstance(command, BrowserControlCommand)
            and command.kind in {"open-tab", "list-tabs"}
            else "sticky-last-target"
        )
        return BrowserExecutionPlan(
            command=command,
            system=system,
            profile=profile,
            capabilities=capabilities,
            control_family=capabilities.control_family,
            action_family=capabilities.action_family,
            launch_policy=launch_policy,
            tab_selection_policy=tab_selection_policy,
        )


@dataclass(frozen=True, slots=True)
class _DefaultBrowserProfileTabOps(BrowserProfileTabOps):
    plan: BrowserExecutionPlan
    runtime_state: BrowserProfileRuntimeState
    control_engine: Any

    def list_tabs(self) -> tuple[BrowserTab, ...]:
        return self.control_engine.list_tabs(
            plan=self.plan,
            runtime_state=self.runtime_state,
        )

    def open_tab(self, url: str) -> BrowserTab:
        return self.control_engine.open_tab(
            plan=self.plan,
            runtime_state=self.runtime_state,
            url=url,
        )

    def navigate_tab(self, target_id: str, url: str) -> BrowserTab:
        return self.control_engine.navigate_tab(
            plan=self.plan,
            runtime_state=self.runtime_state,
            target_id=target_id,
            url=url,
        )

    def focus_tab(self, target_id: str) -> BrowserTab:
        return self.control_engine.focus_tab(
            plan=self.plan,
            runtime_state=self.runtime_state,
            target_id=target_id,
        )

    def close_tab(self, target_id: str) -> None:
        self.control_engine.close_tab(
            plan=self.plan,
            runtime_state=self.runtime_state,
            target_id=target_id,
        )


@dataclass(frozen=True, slots=True)
class DefaultBrowserProfileTabOpsFactory(BrowserProfileTabOpsFactory):
    def create(
        self,
        *,
        plan: BrowserExecutionPlan,
        runtime_state: BrowserProfileRuntimeState,
        control_engine: Any,
    ) -> BrowserProfileTabOps:
        return _DefaultBrowserProfileTabOps(
            plan=plan,
            runtime_state=runtime_state,
            control_engine=control_engine,
        )


@dataclass(frozen=True, slots=True)
class _DefaultBrowserProfileSelectionOps(BrowserProfileSelectionOps):
    plan: BrowserExecutionPlan
    runtime_state: BrowserProfileRuntimeState
    tab_ops: BrowserProfileTabOps

    def _cached_tabs(self) -> tuple[BrowserTab, ...]:
        raw = self.runtime_state.metadata.get("tabs")
        if not isinstance(raw, list):
            return ()
        tabs: list[BrowserTab] = []
        for item in raw:
            if not isinstance(item, Mapping):
                continue
            target_id = str(item.get("target_id", "")).strip()
            if not target_id:
                continue
            tabs.append(
                BrowserTab(
                    target_id=target_id,
                    url=str(item.get("url", "")).strip(),
                    title=str(item.get("title", "")).strip(),
                    type=str(item.get("type", "page")).strip() or "page",
                    ws_url=(
                        str(item["ws_url"])
                        if item.get("ws_url") is not None
                        else None
                    ),
                    json_endpoints=(
                        dict(item["json_endpoints"])
                        if isinstance(item.get("json_endpoints"), dict)
                        else None
                    ),
                )
            )
        return tuple(tabs)

    def ensure_tab_available(
        self,
        *,
        requested_target: BrowserActionTarget,
    ) -> BrowserTab:
        tabs = self._cached_tabs()
        if not tabs:
            tabs = self.tab_ops.list_tabs()
        if not tabs and requested_target.target_id is None:
            tabs = (self.tab_ops.open_tab("about:blank"),)
        if not tabs:
            raise BrowserValidationError("No browser tabs are available.")

        if requested_target.target_id is not None:
            for tab in tabs:
                if tab.target_id == requested_target.target_id:
                    return tab
            fallback_tab = self._fallback_tab_for_missing_requested_target(tabs=tabs)
            if fallback_tab is not None:
                return fallback_tab
            raise BrowserValidationError(
                f"Browser tab '{requested_target.target_id}' was not found.",
            )

        if (
            self.plan.tab_selection_policy == "sticky-last-target"
            and self.runtime_state.last_target_id is not None
        ):
            for tab in tabs:
                if tab.target_id == self.runtime_state.last_target_id:
                    return tab

        for tab in tabs:
            if tab.type == "page":
                return tab
        return tabs[0]

    def _fallback_tab_for_missing_requested_target(
        self,
        *,
        tabs: tuple[BrowserTab, ...],
    ) -> BrowserTab | None:
        if self.plan.tab_selection_policy != "sticky-last-target":
            return None
        if not isinstance(self.plan.command, BrowserPageActionCommand):
            return None

        requested_target_id = self.plan.command.target.target_id
        if isinstance(requested_target_id, str):
            try:
                requested_ordinal = int(requested_target_id.strip())
            except ValueError:
                requested_ordinal = None
            if requested_ordinal is not None and requested_ordinal >= 1:
                page_tabs = tuple(tab for tab in tabs if tab.type == "page")
                ordinal_tabs = page_tabs or tabs
                if requested_ordinal <= len(ordinal_tabs):
                    return ordinal_tabs[requested_ordinal - 1]

        active_target = self.runtime_state.metadata.get("active_target_id")
        if isinstance(active_target, str) and active_target.strip():
            for tab in tabs:
                if tab.target_id == active_target.strip():
                    return tab

        if self.runtime_state.last_target_id is not None:
            for tab in tabs:
                if tab.target_id == self.runtime_state.last_target_id:
                    return tab
        return None


@dataclass(frozen=True, slots=True)
class DefaultBrowserProfileSelectionOpsFactory(BrowserProfileSelectionOpsFactory):
    def create(
        self,
        *,
        plan: BrowserExecutionPlan,
        runtime_state: BrowserProfileRuntimeState,
        tab_ops: BrowserProfileTabOps,
    ) -> BrowserProfileSelectionOps:
        return _DefaultBrowserProfileSelectionOps(
            plan=plan,
            runtime_state=runtime_state,
            tab_ops=tab_ops,
        )


@dataclass(frozen=True, slots=True)
class DefaultBrowserAllocationTargetRecycler(BrowserAllocationTargetRecycler):
    execution_coordinator: BrowserExecutionCoordinator

    def close_owned_target(
        self,
        *,
        profile_name: str,
        target_id: str,
    ) -> None:
        self.execution_coordinator.execute(
            BrowserControlCommand(
                profile_name=profile_name,
                kind="close-tab",
                target_id=target_id,
                payload={},
            ),
        )


@dataclass(frozen=True, slots=True)
class DefaultBrowserAllocationTargetInspector(BrowserAllocationTargetInspector):
    execution_coordinator: BrowserExecutionCoordinator

    def list_target_ids(
        self,
        *,
        profile_name: str,
    ) -> tuple[str, ...]:
        result = self.execution_coordinator.execute(
            BrowserControlCommand(
                profile_name=profile_name,
                kind="list-tabs",
                payload={},
            ),
        )
        if isinstance(result.value, tuple):
            tabs = result.value
        elif isinstance(result.value, list):
            tabs = tuple(result.value)
        else:
            tabs = ()
        target_ids: list[str] = []
        for tab in tabs:
            target_id = _optional_text(getattr(tab, "target_id", None))
            if target_id is None or target_id in target_ids:
                continue
            target_ids.append(target_id)
        return tuple(target_ids)
