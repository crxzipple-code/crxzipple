from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, get_args
from urllib.parse import urlsplit

from crxzipple.modules.browser.domain import (
    BrowserActionResult,
    BrowserActionTarget,
    BrowserCommand,
    BrowserControlCommand,
    BrowserControlKind,
    BrowserExecutionPlan,
    BrowserPageActionCommand,
    BrowserPageActionKind,
    BrowserProfileCapabilities,
    BrowserProfileConfig,
    BrowserProfileRuntimeState,
    BrowserSystemConfig,
    BrowserTab,
    BrowserValidationError,
    ResolvedBrowserProfile,
)

from .ports import (
    BrowserCapabilitiesResolver,
    BrowserControlCommandAssembler,
    BrowserEngineRegistry,
    BrowserExecutionCoordinator,
    BrowserExecutionPlanner,
    BrowserPageActionAssembler,
    BrowserProfileResolver,
    BrowserProfileSelectionOps,
    BrowserProfileSelectionOpsFactory,
    BrowserProfileTabOps,
    BrowserProfileTabOpsFactory,
    BrowserRefStore,
    BrowserRuntimeStateStore,
    BrowserSystemConfigStore,
)

_ALLOWED_CONTROL_KINDS = frozenset(get_args(BrowserControlKind))
_ALLOWED_PAGE_ACTION_KINDS = frozenset(get_args(BrowserPageActionKind))
_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}
_UNSET = object()
_TAB_SCOPED_ACTIONS = frozenset(
    {
        "click",
        "type",
        "press",
        "hover",
        "drag",
        "batch",
        "resize",
        "scroll-into-view",
        "select",
        "fill",
        "wait",
        "snapshot",
        "screenshot",
        "pdf",
        "evaluate",
    }
)


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

        if profile.driver == "existing-session":
            return ResolvedBrowserProfile(
                name=profile.name,
                driver=profile.driver,
                cdp_url=None,
                cdp_port=None,
                user_data_dir=profile.user_data_dir,
                attach_only=True,
                is_loopback=True,
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
                control_family="mcp-control",
                action_family="mcp-backed",
                can_launch=False,
                supports_reset=False,
                supports_per_tab_ws=False,
                supports_json_tab_endpoints=False,
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

    def ensure_tab_available(
        self,
        *,
        requested_target: BrowserActionTarget,
    ) -> BrowserTab:
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


@dataclass(slots=True)
class BrowserExecutionCoordinatorService(BrowserExecutionCoordinator):
    system_config_store: BrowserSystemConfigStore
    profile_resolver: BrowserProfileResolver
    capabilities_resolver: BrowserCapabilitiesResolver
    runtime_state_store: BrowserRuntimeStateStore
    ref_store: BrowserRefStore
    execution_planner: BrowserExecutionPlanner
    engine_registry: BrowserEngineRegistry
    tab_ops_factory: BrowserProfileTabOpsFactory
    selection_ops_factory: BrowserProfileSelectionOpsFactory

    def execute(self, command: BrowserCommand) -> BrowserActionResult:
        system = self.system_config_store.load()
        profile = self.profile_resolver.resolve(
            system=system,
            profile_name=command.profile_name,
        )
        capabilities = self.capabilities_resolver.resolve(profile=profile)
        plan = self.execution_planner.plan(
            system=system,
            profile=profile,
            capabilities=capabilities,
            command=command,
        )

        runtime_state = self.runtime_state_store.get(profile_name=profile.name)
        if runtime_state is None:
            runtime_state = BrowserProfileRuntimeState(profile_name=profile.name)

        engine_binding = self.engine_registry.resolve(
            plan=plan,
            command=command,
        )
        control_engine = engine_binding.control_engine
        action_engine = engine_binding.action_engine
        if isinstance(command, BrowserControlCommand) and command.kind == "reset":
            if not capabilities.supports_reset:
                raise BrowserValidationError(
                    f"Browser profile '{profile.name}' does not support reset.",
                )
            control_engine.reset_profile(
                plan=plan,
                runtime_state=runtime_state,
            )
            action_engine.clear_profile(profile_name=profile.name)
            self.ref_store.delete_profile_refs(profile_name=profile.name)
            self.runtime_state_store.delete(profile_name=profile.name)
            return BrowserActionResult(
                command=command,
                ok=True,
                value={"profile_name": profile.name},
                message="Reset browser profile.",
            )

        runtime_state.mark_attaching()
        self.runtime_state_store.save(runtime_state)
        try:
            runtime_state = control_engine.ensure_attached(
                plan=plan,
                runtime_state=runtime_state,
            )
        except BrowserValidationError as exc:
            runtime_state.mark_failed(str(exc))
            self.runtime_state_store.save(runtime_state)
            raise
        self.runtime_state_store.save(runtime_state)

        tab_ops = self.tab_ops_factory.create(
            plan=plan,
            runtime_state=runtime_state,
            control_engine=control_engine,
        )

        if isinstance(command, BrowserControlCommand) and command.kind == "list-tabs":
            tabs = tab_ops.list_tabs()
            return BrowserActionResult(
                command=command,
                ok=True,
                value=tabs,
                message=f"Listed {len(tabs)} tabs.",
            )

        if isinstance(command, BrowserControlCommand) and command.kind == "open-tab":
            if (
                capabilities.supports_managed_tab_limit
                and system.managed_tab_limit is not None
            ):
                current_tabs = tab_ops.list_tabs()
                if len(current_tabs) >= system.managed_tab_limit:
                    raise BrowserValidationError(
                        "Browser managed tab limit was reached.",
                    )
            url = self._require_payload_text(command, key="url")
            tab = tab_ops.open_tab(url)
            runtime_state.remember_target(tab.target_id)
            self.runtime_state_store.save(runtime_state)
            return BrowserActionResult(
                command=command,
                ok=True,
                target_id=tab.target_id,
                value=tab,
                message="Opened browser tab.",
            )

        selection_ops = self.selection_ops_factory.create(
            plan=plan,
            runtime_state=runtime_state,
            tab_ops=tab_ops,
        )
        requested_target = (
            BrowserActionTarget(target_id=command.target_id)
            if isinstance(command, BrowserControlCommand)
            else command.target
        )
        resolved_tab = selection_ops.ensure_tab_available(
            requested_target=requested_target,
        )

        if isinstance(command, BrowserControlCommand) and command.kind == "navigate":
            url = self._require_payload_text(command, key="url")
            tab = tab_ops.navigate_tab(resolved_tab.target_id, url)
            self.ref_store.delete_tab_refs(
                profile_name=profile.name,
                target_id=resolved_tab.target_id,
            )
            runtime_state.forget_page(target_id=resolved_tab.target_id)
            runtime_state.remember_target(tab.target_id)
            self.runtime_state_store.save(runtime_state)
            return BrowserActionResult(
                command=command,
                ok=True,
                target_id=tab.target_id,
                value=tab,
                message="Navigated browser tab.",
            )

        if isinstance(command, BrowserControlCommand) and command.kind == "focus-tab":
            tab = tab_ops.focus_tab(resolved_tab.target_id)
            runtime_state.remember_target(tab.target_id)
            self.runtime_state_store.save(runtime_state)
            return BrowserActionResult(
                command=command,
                ok=True,
                target_id=tab.target_id,
                value=tab,
                message="Focused browser tab.",
            )

        if isinstance(command, BrowserControlCommand) and command.kind == "close-tab":
            tab_ops.close_tab(resolved_tab.target_id)
            self.ref_store.delete_tab_refs(
                profile_name=profile.name,
                target_id=resolved_tab.target_id,
            )
            runtime_state.forget_page(target_id=resolved_tab.target_id)
            if runtime_state.last_target_id == resolved_tab.target_id:
                runtime_state.remember_target(None)
            self.runtime_state_store.save(runtime_state)
            return BrowserActionResult(
                command=command,
                ok=True,
                target_id=resolved_tab.target_id,
                message="Closed browser tab.",
            )

        if not isinstance(command, BrowserPageActionCommand):
            raise BrowserValidationError(
                f"Unsupported browser control kind '{command.kind}'.",
            )

        if command.kind not in _TAB_SCOPED_ACTIONS:
            raise BrowserValidationError(
                f"Unsupported browser execution kind '{command.kind}'.",
            )

        if command.target.ref is not None:
            stored_refs = self.ref_store.get_tab_refs(
                profile_name=profile.name,
                target_id=resolved_tab.target_id,
            )
            if runtime_state.restore_page_ref_session(
                target_id=resolved_tab.target_id,
                refs=stored_refs,
            ):
                self.runtime_state_store.save(runtime_state)

        result = action_engine.execute(
            plan=plan,
            runtime_state=runtime_state,
            tab=resolved_tab,
            command=command,
        )
        runtime_state.remember_target(result.target_id or resolved_tab.target_id)
        self.runtime_state_store.save(runtime_state)
        return result

    @staticmethod
    def _require_payload_text(command: BrowserCommand, *, key: str) -> str:
        value = command.payload.get(key)
        if not isinstance(value, str) or not value.strip():
            raise BrowserValidationError(f"payload.{key} is required.")
        return value.strip()


@dataclass(slots=True)
class BrowserProfileAdminService:
    system_config_store: BrowserSystemConfigStore
    runtime_state_store: BrowserRuntimeStateStore
    ref_store: BrowserRefStore

    def list_profiles(self) -> BrowserSystemConfig:
        return self.system_config_store.load()

    def create_profile(
        self,
        *,
        name: str,
        driver: str = "managed",
        cdp_url: str | None = None,
        cdp_port: int | None = None,
        user_data_dir: str | None = None,
        attach_only: bool = False,
        set_as_default: bool = False,
    ) -> BrowserSystemConfig:
        system = self.system_config_store.load()
        normalized_name = name.strip().lower()
        if any(profile.name == normalized_name for profile in system.profiles):
            raise BrowserValidationError(
                f"Browser profile '{name}' already exists.",
            )

        profile = BrowserProfileConfig(
            name=name,
            driver=driver,  # type: ignore[arg-type]
            cdp_url=cdp_url,
            cdp_port=cdp_port,
            user_data_dir=user_data_dir,
            attach_only=attach_only,
        )
        updated = self._rebuild_system(
            system,
            profiles=system.profiles + (profile,),
            default_profile=profile.name if set_as_default else system.default_profile,
        )
        return self.system_config_store.save(updated)

    def update_profile(
        self,
        *,
        profile_name: str,
        driver: str | object = _UNSET,
        cdp_url: str | None | object = _UNSET,
        cdp_port: int | None | object = _UNSET,
        user_data_dir: str | None | object = _UNSET,
        attach_only: bool | object = _UNSET,
        set_as_default: bool | None = None,
    ) -> BrowserSystemConfig:
        system = self.system_config_store.load()
        current = self._get_profile(system, profile_name)

        updated_profile = BrowserProfileConfig(
            name=current.name,
            driver=current.driver if driver is _UNSET else str(driver),
            cdp_url=current.cdp_url if cdp_url is _UNSET else cdp_url,
            cdp_port=current.cdp_port if cdp_port is _UNSET else cdp_port,
            user_data_dir=(
                current.user_data_dir if user_data_dir is _UNSET else user_data_dir
            ),
            attach_only=(
                current.attach_only if attach_only is _UNSET else bool(attach_only)
            ),
        )

        profiles = tuple(
            updated_profile if profile.name == current.name else profile
            for profile in system.profiles
        )
        default_profile = (
            updated_profile.name
            if set_as_default is True
            else system.default_profile
        )
        updated = self._rebuild_system(
            system,
            profiles=profiles,
            default_profile=default_profile,
        )
        return self.system_config_store.save(updated)

    def delete_profile(self, *, profile_name: str) -> BrowserSystemConfig:
        system = self.system_config_store.load()
        profile = self._get_profile(system, profile_name)
        remaining = tuple(
            candidate for candidate in system.profiles if candidate.name != profile.name
        )
        if not remaining:
            raise BrowserValidationError("Cannot delete the last browser profile.")

        default_profile = (
            system.default_profile
            if system.default_profile != profile.name
            else remaining[0].name
        )
        updated = self._rebuild_system(
            system,
            profiles=remaining,
            default_profile=default_profile,
        )
        saved = self.system_config_store.save(updated)
        self.runtime_state_store.delete(profile_name=profile.name)
        self.ref_store.delete_profile_refs(profile_name=profile.name)
        return saved

    def set_default_profile(self, *, profile_name: str) -> BrowserSystemConfig:
        system = self.system_config_store.load()
        profile = self._get_profile(system, profile_name)
        updated = self._rebuild_system(
            system,
            default_profile=profile.name,
        )
        return self.system_config_store.save(updated)

    @staticmethod
    def _get_profile(
        system: BrowserSystemConfig,
        profile_name: str,
    ) -> BrowserProfileConfig:
        normalized_name = profile_name.strip().lower()
        for profile in system.profiles:
            if profile.name == normalized_name:
                return profile
        raise BrowserValidationError(
            f"Browser profile '{profile_name}' is not configured.",
        )

    @staticmethod
    def _rebuild_system(
        system: BrowserSystemConfig,
        *,
        profiles: tuple[BrowserProfileConfig, ...] | None = None,
        default_profile: str | None = None,
    ) -> BrowserSystemConfig:
        return BrowserSystemConfig(
            default_profile=default_profile or system.default_profile,
            profiles=profiles or system.profiles,
            headless=system.headless,
            executable_path=system.executable_path,
            no_sandbox=system.no_sandbox,
            managed_tab_limit=system.managed_tab_limit,
            cdp_host=system.cdp_host,
            cdp_port_range_start=system.cdp_port_range_start,
            cdp_port_range_end=system.cdp_port_range_end,
        )
