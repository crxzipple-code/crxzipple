from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, get_args
from urllib.parse import urlsplit
from uuid import uuid4

from crxzipple.modules.browser.domain import (
    BrowserActionResult,
    BrowserActionTarget,
    BrowserCommand,
    BrowserControlCommand,
    BrowserControlKind,
    BrowserExecutionPlan,
    BrowserPageActionCommand,
    BrowserPageActionKind,
    BrowserProfileAllocation,
    BrowserProfileCapabilities,
    BrowserProfileConfig,
    BrowserProfilePool,
    BrowserProfileRuntimeState,
    BrowserSystemConfig,
    BrowserTab,
    BrowserValidationError,
    ResolvedBrowserProfile,
)

from .events import (
    BROWSER_ALLOCATION_ACQUIRED_EVENT,
    BROWSER_ALLOCATION_EXPIRED_EVENT,
    BROWSER_ALLOCATION_FAILED_EVENT,
    BROWSER_ALLOCATION_HEARTBEATED_EVENT,
    BROWSER_ALLOCATION_LOST_EVENT,
    BROWSER_ALLOCATION_RELEASED_EVENT,
    BROWSER_POOL_CREATED_EVENT,
    BROWSER_POOL_DELETED_EVENT,
    BROWSER_POOL_DISABLED_EVENT,
    BROWSER_POOL_ENABLED_EVENT,
    BROWSER_POOL_UPDATED_EVENT,
    BROWSER_PROFILE_CREATED_EVENT,
    BROWSER_PROFILE_DELETED_EVENT,
    BROWSER_PROFILE_DISABLED_EVENT,
    BROWSER_PROFILE_ENABLED_EVENT,
    BROWSER_PROFILE_UPDATED_EVENT,
    BrowserEventEmitter,
    emit_browser_event,
)
from .runtime_payloads import browser_runtime_status_payload as _runtime_status_payload
from .ports import (
    BrowserAllocationTargetRecycler,
    BrowserAllocationTargetInspector,
    BrowserCapabilitiesResolver,
    BrowserControlCommandAssembler,
    BrowserEngineRegistry,
    BrowserExecutionCoordinator,
    BrowserExecutionPlanner,
    BrowserPageActionAssembler,
    BrowserProfileAllocationStore,
    BrowserProfileHostServiceSync,
    BrowserProfileResolver,
    BrowserProfilePoolStore,
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
_TAB_SCOPED_ACTIONS = _ALLOWED_PAGE_ACTION_KINDS


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


def _require_positive_int(value: object, *, label: str) -> int:
    try:
        numeric = int(value)
    except (TypeError, ValueError) as exc:
        raise BrowserValidationError(f"{label} must be an integer.") from exc
    if numeric < 1:
        raise BrowserValidationError(f"{label} must be greater than or equal to 1.")
    return numeric


def _compose_cdp_url(system: BrowserSystemConfig, cdp_port: int) -> str:
    return f"http://{system.cdp_host}:{cdp_port}"


def _disabled_profile_command_allowed(command: BrowserCommand) -> bool:
    return isinstance(command, BrowserControlCommand) and command.kind in {"status", "stop"}


def _changed_profile_fields(
    before: BrowserProfileConfig,
    after: BrowserProfileConfig,
) -> tuple[str, ...]:
    field_names = (
        "driver",
        "enabled",
        "cdp_url",
        "cdp_port",
        "user_data_dir",
        "profile_directory",
        "attach_only",
        "autostart",
        "proxy_mode",
        "proxy_server",
        "proxy_bypass_list",
        "proxy_binding_id",
        "proxy_credential_kind",
        "close_targets_on_release",
        "close_targets_on_expire",
    )
    return tuple(name for name in field_names if getattr(before, name) != getattr(after, name))


def _profile_event_payload(
    profile: BrowserProfileConfig,
    *,
    system: BrowserSystemConfig,
    changed_fields: tuple[str, ...] = (),
) -> dict[str, Any]:
    return {
        "profile_name": profile.name,
        "driver": profile.driver,
        "enabled": profile.enabled,
        "default_profile": system.default_profile,
        "is_default": system.default_profile == profile.name,
        "attach_only": profile.attach_only,
        "autostart": profile.autostart,
        "has_cdp_url": profile.cdp_url is not None,
        "cdp_port": profile.cdp_port,
        "profile_directory_configured": profile.profile_directory is not None,
        "user_data_dir_configured": profile.user_data_dir is not None,
        "proxy_mode": profile.proxy_mode,
        "proxy_binding_id": profile.proxy_binding_id,
        "proxy_credential_kind": profile.proxy_credential_kind,
        "close_targets_on_release": profile.close_targets_on_release,
        "close_targets_on_expire": profile.close_targets_on_expire,
        "proxy_configured": profile.proxy_server is not None or profile.proxy_binding_id is not None,
        "changed_fields": list(changed_fields),
    }


def _sanitize_profile_egress_result(result: Mapping[str, Any]) -> dict[str, Any]:
    sanitized: dict[str, Any] = {}
    for key in ("status", "ip", "url", "http_status"):
        value = result.get(key)
        if value is not None:
            sanitized[key] = value
    reason = result.get("reason")
    if reason is not None:
        sanitized["reason"] = str(reason)[:240]
    return sanitized


def _changed_pool_fields(
    before: BrowserProfilePool,
    after: BrowserProfilePool,
) -> tuple[str, ...]:
    field_names = (
        "display_name",
        "enabled",
        "profile_names",
        "target_hosts",
        "selection_strategy",
        "max_concurrency_per_profile",
        "max_concurrency_total",
        "allocation_ttl_seconds",
        "cooldown_seconds",
        "failure_cooldown_seconds",
        "allow_attach_only",
        "close_targets_on_release",
        "close_targets_on_expire",
        "health_policy",
        "metadata",
    )
    return tuple(name for name in field_names if getattr(before, name) != getattr(after, name))


def _pool_event_payload(
    pool: BrowserProfilePool,
    *,
    changed_fields: tuple[str, ...] = (),
) -> dict[str, Any]:
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
        "changed_fields": list(changed_fields),
    }


def _allocation_event_payload(
    allocation: BrowserProfileAllocation,
) -> dict[str, Any]:
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
            if allocation.last_heartbeat_at is not None
            else None
        ),
        "released_at": (
            allocation.released_at.isoformat()
            if allocation.released_at is not None
            else None
        ),
        "release_reason": allocation.release_reason,
        "owned_target_ids": list(allocation.owned_target_ids),
        "metadata": dict(allocation.metadata),
    }


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


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
        if not profile.enabled and not _disabled_profile_command_allowed(command):
            raise BrowserValidationError(f"Browser profile '{profile.name}' is disabled.")

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

        if isinstance(command, BrowserControlCommand) and command.kind == "stop":
            control_engine.stop_profile(
                plan=plan,
                runtime_state=runtime_state,
            )
            action_engine.clear_profile(profile_name=profile.name)
            self.ref_store.delete_profile_refs(profile_name=profile.name)
            self.runtime_state_store.save(runtime_state)
            return BrowserActionResult(
                command=command,
                ok=True,
                value={
                    "profile_name": profile.name,
                    "runtime": _runtime_status_payload(runtime_state),
                },
                message="Stopped browser profile.",
            )

        if isinstance(command, BrowserControlCommand) and command.kind == "status":
            tabs: tuple[BrowserTab, ...] = ()
            tabs_error: str | None = None
            if runtime_state.attachment_status == "attached":
                try:
                    tabs = control_engine.list_tabs(
                        plan=plan,
                        runtime_state=runtime_state,
                    )
                except BrowserValidationError as exc:
                    tabs_error = str(exc)
            return BrowserActionResult(
                command=command,
                ok=True,
                target_id=runtime_state.last_target_id,
                value={
                    "profile_name": profile.name,
                    "driver": profile.driver,
                    "mode": capabilities.mode,
                    "enabled": profile.enabled,
                    "control_family": capabilities.control_family,
                    "action_family": capabilities.action_family,
                    "can_launch": capabilities.can_launch,
                    "supports_reset": capabilities.supports_reset,
                    "supports_per_tab_ws": capabilities.supports_per_tab_ws,
                    "supports_json_tab_endpoints": capabilities.supports_json_tab_endpoints,
                    "runtime": _runtime_status_payload(runtime_state),
                    "tabs": tabs,
                    "tab_count": len(tabs),
                    "tabs_error": tabs_error,
                },
                message="Loaded browser profile status.",
            )

        previous_host_generation = runtime_state.host_generation()
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
        current_host_generation = runtime_state.host_generation()
        if (
            previous_host_generation is not None
            and current_host_generation is not None
            and previous_host_generation != current_host_generation
        ):
            self.ref_store.delete_profile_refs(profile_name=profile.name)
            runtime_state.forget_all_pages()
            runtime_state.metadata["host_generation_changed"] = True
        self.runtime_state_store.save(runtime_state)

        tab_ops = self.tab_ops_factory.create(
            plan=plan,
            runtime_state=runtime_state,
            control_engine=control_engine,
        )

        if isinstance(command, BrowserControlCommand) and command.kind == "start":
            tabs = tab_ops.list_tabs()
            return BrowserActionResult(
                command=command,
                ok=True,
                target_id=runtime_state.last_target_id,
                value={
                    "profile_name": profile.name,
                    "runtime": _runtime_status_payload(runtime_state),
                    "tabs": tabs,
                    "tab_count": len(tabs),
                },
                message="Started browser profile.",
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
            runtime_state.remember_page_opened(target_id=tab.target_id)
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
            runtime_state.reset_page_state(
                target_id=resolved_tab.target_id,
                reason="navigate",
            )
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
    allocation_store: BrowserProfileAllocationStore | None = None
    host_service_sync: BrowserProfileHostServiceSync | None = None
    event_emitter: BrowserEventEmitter | None = None

    def list_profiles(self) -> BrowserSystemConfig:
        return self.system_config_store.load()

    def create_profile(
        self,
        *,
        name: str,
        driver: str = "managed",
        enabled: bool = True,
        cdp_url: str | None = None,
        cdp_port: int | None = None,
        user_data_dir: str | None = None,
        profile_directory: str | None = None,
        attach_only: bool = False,
        autostart: bool = True,
        proxy_mode: str = "none",
        proxy_server: str | None = None,
        proxy_bypass_list: tuple[str, ...] = (),
        proxy_binding_id: str | None = None,
        proxy_credential_kind: str = "basic",
        close_targets_on_release: bool = True,
        close_targets_on_expire: bool = True,
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
            enabled=enabled,
            cdp_url=cdp_url,
            cdp_port=cdp_port,
            user_data_dir=user_data_dir,
            profile_directory=profile_directory,
            attach_only=attach_only,
            autostart=autostart,
            proxy_mode=proxy_mode,  # type: ignore[arg-type]
            proxy_server=proxy_server,
            proxy_bypass_list=proxy_bypass_list,
            proxy_binding_id=proxy_binding_id,
            proxy_credential_kind=proxy_credential_kind,  # type: ignore[arg-type]
            close_targets_on_release=close_targets_on_release,
            close_targets_on_expire=close_targets_on_expire,
        )
        updated = self._rebuild_system(
            system,
            profiles=system.profiles + (profile,),
            default_profile=profile.name if set_as_default else system.default_profile,
        )
        saved = self.system_config_store.save(updated)
        self._sync_profile_host_service(system=saved, profile=profile)
        self._emit_profile_event(
            BROWSER_PROFILE_CREATED_EVENT,
            profile=profile,
            system=saved,
            status="created",
        )
        return saved

    def update_profile(
        self,
        *,
        profile_name: str,
        driver: str | object = _UNSET,
        enabled: bool | object = _UNSET,
        cdp_url: str | None | object = _UNSET,
        cdp_port: int | None | object = _UNSET,
        user_data_dir: str | None | object = _UNSET,
        profile_directory: str | None | object = _UNSET,
        attach_only: bool | object = _UNSET,
        autostart: bool | object = _UNSET,
        proxy_mode: str | object = _UNSET,
        proxy_server: str | None | object = _UNSET,
        proxy_bypass_list: tuple[str, ...] | object = _UNSET,
        proxy_binding_id: str | None | object = _UNSET,
        proxy_credential_kind: str | object = _UNSET,
        close_targets_on_release: bool | object = _UNSET,
        close_targets_on_expire: bool | object = _UNSET,
        set_as_default: bool | None = None,
    ) -> BrowserSystemConfig:
        system = self.system_config_store.load()
        current = self._get_profile(system, profile_name)
        requested_enabled = current.enabled if enabled is _UNSET else bool(enabled)
        if not requested_enabled:
            self._raise_if_profile_runtime_active(current.name, action="disable")
            self._raise_if_profile_allocation_active(current.name, action="disable")

        updated_profile = BrowserProfileConfig(
            name=current.name,
            driver=current.driver if driver is _UNSET else str(driver),
            enabled=requested_enabled,
            cdp_url=current.cdp_url if cdp_url is _UNSET else cdp_url,
            cdp_port=current.cdp_port if cdp_port is _UNSET else cdp_port,
            user_data_dir=(
                current.user_data_dir if user_data_dir is _UNSET else user_data_dir
            ),
            profile_directory=(
                current.profile_directory
                if profile_directory is _UNSET
                else profile_directory
            ),
            attach_only=(
                current.attach_only if attach_only is _UNSET else bool(attach_only)
            ),
            autostart=(
                current.autostart if autostart is _UNSET else bool(autostart)
            ),
            proxy_mode=(
                current.proxy_mode if proxy_mode is _UNSET else str(proxy_mode)
            ),  # type: ignore[arg-type]
            proxy_server=(
                current.proxy_server if proxy_server is _UNSET else proxy_server
            ),
            proxy_bypass_list=(
                current.proxy_bypass_list
                if proxy_bypass_list is _UNSET
                else proxy_bypass_list
            ),
            proxy_binding_id=(
                current.proxy_binding_id
                if proxy_binding_id is _UNSET
                else proxy_binding_id
            ),
            proxy_credential_kind=(
                current.proxy_credential_kind
                if proxy_credential_kind is _UNSET
                else str(proxy_credential_kind)
            ),  # type: ignore[arg-type]
            close_targets_on_release=(
                current.close_targets_on_release
                if close_targets_on_release is _UNSET
                else bool(close_targets_on_release)
            ),
            close_targets_on_expire=(
                current.close_targets_on_expire
                if close_targets_on_expire is _UNSET
                else bool(close_targets_on_expire)
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
        saved = self.system_config_store.save(updated)
        self._sync_profile_host_service(system=saved, profile=updated_profile)
        changed_fields = _changed_profile_fields(current, updated_profile)
        if system.default_profile != default_profile:
            changed_fields = tuple((*changed_fields, "default_profile"))
        if changed_fields:
            self._emit_profile_event(
                BROWSER_PROFILE_UPDATED_EVENT,
                profile=updated_profile,
                system=saved,
                status="updated",
                changed_fields=changed_fields,
            )
        if current.enabled != updated_profile.enabled:
            self._emit_profile_event(
                BROWSER_PROFILE_ENABLED_EVENT
                if updated_profile.enabled
                else BROWSER_PROFILE_DISABLED_EVENT,
                profile=updated_profile,
                system=saved,
                status="enabled" if updated_profile.enabled else "disabled",
                changed_fields=("enabled",),
            )
        return saved

    def delete_profile(self, *, profile_name: str) -> BrowserSystemConfig:
        system = self.system_config_store.load()
        profile = self._get_profile(system, profile_name)
        if system.default_profile == profile.name:
            raise BrowserValidationError(
                "Cannot delete the default browser profile. Set another default first.",
            )
        self._raise_if_profile_runtime_active(profile.name, action="delete")
        self._raise_if_profile_allocation_active(profile.name, action="delete")
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
        self._remove_profile_host_service(profile.name)
        self._emit_profile_event(
            BROWSER_PROFILE_DELETED_EVENT,
            profile=profile,
            system=saved,
            status="deleted",
        )
        return saved

    def enable_profile(self, *, profile_name: str) -> BrowserSystemConfig:
        return self.update_profile(profile_name=profile_name, enabled=True)

    def disable_profile(self, *, profile_name: str) -> BrowserSystemConfig:
        return self.update_profile(profile_name=profile_name, enabled=False)

    def record_profile_egress(
        self,
        *,
        profile_name: str,
        result: Mapping[str, Any],
    ) -> BrowserProfileRuntimeState:
        system = self.system_config_store.load()
        profile = self._get_profile(system, profile_name)
        sanitized = _sanitize_profile_egress_result(result)
        checked_at = _utc_now().isoformat()

        runtime_state = self.runtime_state_store.get(profile_name=profile.name)
        if runtime_state is None:
            runtime_state = BrowserProfileRuntimeState(profile_name=profile.name)
        runtime_state.metadata["proxy_egress"] = sanitized
        runtime_state.metadata["proxy_egress_status"] = sanitized.get("status")
        runtime_state.metadata["proxy_egress_checked_at"] = checked_at
        if sanitized.get("ip"):
            runtime_state.metadata["proxy_egress_ip"] = sanitized["ip"]
        else:
            runtime_state.metadata.pop("proxy_egress_ip", None)
        self.runtime_state_store.save(runtime_state)

        self._emit_profile_event(
            BROWSER_PROFILE_UPDATED_EVENT,
            profile=profile,
            system=system,
            status="egress_checked",
            changed_fields=("proxy_egress",),
            extra_payload={
                "proxy_egress_status": sanitized.get("status"),
                "proxy_egress_ip": sanitized.get("ip"),
                "proxy_egress_checked_at": checked_at,
            },
        )
        return runtime_state

    def _sync_profile_host_service(
        self,
        *,
        system: BrowserSystemConfig,
        profile: BrowserProfileConfig,
    ) -> None:
        if self.host_service_sync is None:
            return
        self.host_service_sync.sync_profile(system=system, profile=profile)

    def _remove_profile_host_service(self, profile_name: str) -> None:
        if self.host_service_sync is None:
            return
        self.host_service_sync.remove_profile(profile_name=profile_name)

    def set_default_profile(self, *, profile_name: str) -> BrowserSystemConfig:
        system = self.system_config_store.load()
        profile = self._get_profile(system, profile_name)
        updated = self._rebuild_system(
            system,
            default_profile=profile.name,
        )
        saved = self.system_config_store.save(updated)
        if system.default_profile != saved.default_profile:
            self._emit_profile_event(
                BROWSER_PROFILE_UPDATED_EVENT,
                profile=profile,
                system=saved,
                status="updated",
                changed_fields=("default_profile",),
            )
        return saved

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

    def _raise_if_profile_runtime_active(self, profile_name: str, *, action: str) -> None:
        runtime_state = self.runtime_state_store.get(profile_name=profile_name)
        if runtime_state is None:
            return
        if runtime_state.attachment_status in {"attached", "attaching", "recovering", "degraded"}:
            raise BrowserValidationError(
                f"Cannot {action} browser profile '{profile_name}' while it is running. Stop it first.",
            )
        if runtime_state.browser_ref is not None or runtime_state.running_pid is not None:
            raise BrowserValidationError(
                f"Cannot {action} browser profile '{profile_name}' while it has active runtime state. Stop it first.",
            )

    def _raise_if_profile_allocation_active(self, profile_name: str, *, action: str) -> None:
        if self.allocation_store is None:
            return
        normalized_profile = profile_name.strip().lower()
        for allocation in self.allocation_store.list_allocations():
            if allocation.profile_name == normalized_profile and allocation.status == "active":
                raise BrowserValidationError(
                    f"Cannot {action} browser profile '{profile_name}' while allocation '{allocation.allocation_id}' is active. Release it first.",
                )

    def _emit_profile_event(
        self,
        event_name: str,
        *,
        profile: BrowserProfileConfig,
        system: BrowserSystemConfig,
        status: str,
        changed_fields: tuple[str, ...] = (),
        extra_payload: Mapping[str, Any] | None = None,
    ) -> None:
        payload = _profile_event_payload(
            profile,
            system=system,
            changed_fields=changed_fields,
        )
        if extra_payload:
            payload.update(extra_payload)
        emit_browser_event(
            self.event_emitter,
            event_name,
            status=status,
            payload=payload,
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


@dataclass(slots=True)
class BrowserProfilePoolService:
    pool_store: BrowserProfilePoolStore
    system_config_store: BrowserSystemConfigStore
    allocation_store: BrowserProfileAllocationStore | None = None
    event_emitter: BrowserEventEmitter | None = None

    def list_pools(self) -> tuple[BrowserProfilePool, ...]:
        return self.pool_store.list_pools()

    def get_pool(self, *, pool_id: str) -> BrowserProfilePool:
        return self._get_pool(pool_id)

    def create_pool(
        self,
        *,
        pool_id: str,
        display_name: str | None = None,
        enabled: bool = True,
        profile_names: tuple[str, ...] = (),
        target_hosts: tuple[str, ...] = (),
        selection_strategy: str = "least_busy",
        max_concurrency_per_profile: int = 1,
        max_concurrency_total: int | None = None,
        allocation_ttl_seconds: int = 900,
        cooldown_seconds: int = 0,
        failure_cooldown_seconds: int = 300,
        allow_attach_only: bool = False,
        close_targets_on_release: bool = True,
        close_targets_on_expire: bool = True,
        health_policy: Mapping[str, Any] | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> BrowserProfilePool:
        pool = BrowserProfilePool(
            pool_id=pool_id,
            display_name=display_name,
            enabled=enabled,
            profile_names=profile_names,
            target_hosts=target_hosts,
            selection_strategy=selection_strategy,  # type: ignore[arg-type]
            max_concurrency_per_profile=max_concurrency_per_profile,
            max_concurrency_total=max_concurrency_total,
            allocation_ttl_seconds=allocation_ttl_seconds,
            cooldown_seconds=cooldown_seconds,
            failure_cooldown_seconds=failure_cooldown_seconds,
            allow_attach_only=allow_attach_only,
            close_targets_on_release=close_targets_on_release,
            close_targets_on_expire=close_targets_on_expire,
            health_policy=health_policy or {},
            metadata=metadata or {},
        )
        if self.pool_store.get_pool(pool_id=pool.pool_id) is not None:
            raise BrowserValidationError(
                f"Browser profile pool '{pool.pool_id}' already exists.",
            )
        self._validate_pool(pool)
        saved = self.pool_store.save_pool(pool)
        self._emit_pool_event(
            BROWSER_POOL_CREATED_EVENT,
            pool=saved,
            status="created",
        )
        return saved

    def update_pool(
        self,
        *,
        pool_id: str,
        display_name: str | None | object = _UNSET,
        enabled: bool | object = _UNSET,
        profile_names: tuple[str, ...] | object = _UNSET,
        target_hosts: tuple[str, ...] | object = _UNSET,
        selection_strategy: str | object = _UNSET,
        max_concurrency_per_profile: int | object = _UNSET,
        max_concurrency_total: int | None | object = _UNSET,
        allocation_ttl_seconds: int | object = _UNSET,
        cooldown_seconds: int | object = _UNSET,
        failure_cooldown_seconds: int | object = _UNSET,
        allow_attach_only: bool | object = _UNSET,
        close_targets_on_release: bool | object = _UNSET,
        close_targets_on_expire: bool | object = _UNSET,
        health_policy: Mapping[str, Any] | object = _UNSET,
        metadata: Mapping[str, Any] | object = _UNSET,
    ) -> BrowserProfilePool:
        current = self._get_pool(pool_id)
        requested_enabled = current.enabled if enabled is _UNSET else bool(enabled)
        if not requested_enabled:
            self._raise_if_pool_allocation_active(current.pool_id, action="disable")
        updated = BrowserProfilePool(
            pool_id=current.pool_id,
            display_name=(
                current.display_name
                if display_name is _UNSET
                else display_name
            ),
            enabled=requested_enabled,
            profile_names=(
                current.profile_names
                if profile_names is _UNSET
                else profile_names
            ),
            target_hosts=(
                current.target_hosts
                if target_hosts is _UNSET
                else target_hosts
            ),
            selection_strategy=(
                current.selection_strategy
                if selection_strategy is _UNSET
                else str(selection_strategy)
            ),  # type: ignore[arg-type]
            max_concurrency_per_profile=(
                current.max_concurrency_per_profile
                if max_concurrency_per_profile is _UNSET
                else int(max_concurrency_per_profile)
            ),
            max_concurrency_total=(
                current.max_concurrency_total
                if max_concurrency_total is _UNSET
                else max_concurrency_total
            ),
            allocation_ttl_seconds=(
                current.allocation_ttl_seconds
                if allocation_ttl_seconds is _UNSET
                else int(allocation_ttl_seconds)
            ),
            cooldown_seconds=(
                current.cooldown_seconds
                if cooldown_seconds is _UNSET
                else int(cooldown_seconds)
            ),
            failure_cooldown_seconds=(
                current.failure_cooldown_seconds
                if failure_cooldown_seconds is _UNSET
                else int(failure_cooldown_seconds)
            ),
            allow_attach_only=(
                current.allow_attach_only
                if allow_attach_only is _UNSET
                else bool(allow_attach_only)
            ),
            close_targets_on_release=(
                current.close_targets_on_release
                if close_targets_on_release is _UNSET
                else bool(close_targets_on_release)
            ),
            close_targets_on_expire=(
                current.close_targets_on_expire
                if close_targets_on_expire is _UNSET
                else bool(close_targets_on_expire)
            ),
            health_policy=(
                current.health_policy
                if health_policy is _UNSET
                else health_policy
            ),
            metadata=current.metadata if metadata is _UNSET else metadata,
        )
        self._validate_pool(updated)
        saved = self.pool_store.save_pool(updated)
        changed_fields = _changed_pool_fields(current, saved)
        if changed_fields:
            self._emit_pool_event(
                BROWSER_POOL_UPDATED_EVENT,
                pool=saved,
                status="updated",
                changed_fields=changed_fields,
            )
        if current.enabled != saved.enabled:
            self._emit_pool_event(
                BROWSER_POOL_ENABLED_EVENT
                if saved.enabled
                else BROWSER_POOL_DISABLED_EVENT,
                pool=saved,
                status="enabled" if saved.enabled else "disabled",
                changed_fields=("enabled",),
            )
        return saved

    def delete_pool(self, *, pool_id: str) -> None:
        pool = self._get_pool(pool_id)
        self._raise_if_pool_allocation_active(pool.pool_id, action="delete")
        self.pool_store.delete_pool(pool_id=pool.pool_id)
        self._emit_pool_event(
            BROWSER_POOL_DELETED_EVENT,
            pool=pool,
            status="deleted",
        )

    def enable_pool(self, *, pool_id: str) -> BrowserProfilePool:
        return self.update_pool(pool_id=pool_id, enabled=True)

    def disable_pool(self, *, pool_id: str) -> BrowserProfilePool:
        return self.update_pool(pool_id=pool_id, enabled=False)

    def _get_pool(self, pool_id: str) -> BrowserProfilePool:
        normalized = pool_id.strip().lower()
        if not normalized:
            raise BrowserValidationError("browser profile pool id is required.")
        pool = self.pool_store.get_pool(pool_id=normalized)
        if pool is None:
            raise BrowserValidationError(
                f"Browser profile pool '{pool_id}' is not configured.",
            )
        return pool

    def _validate_pool(self, pool: BrowserProfilePool) -> None:
        if not pool.profile_names:
            raise BrowserValidationError(
                "browser profile pool must include at least one profile.",
            )
        system = self.system_config_store.load()
        profiles = {profile.name: profile for profile in system.profiles}
        missing = tuple(
            profile_name
            for profile_name in pool.profile_names
            if profile_name not in profiles
        )
        if missing:
            raise BrowserValidationError(
                "browser profile pool references unknown profiles: "
                + ", ".join(missing),
            )
        if pool.allow_attach_only:
            return
        attach_only_profiles = tuple(
            profile.name
            for profile in profiles.values()
            if profile.name in pool.profile_names
            and (profile.attach_only or profile.driver == "existing-session")
        )
        if attach_only_profiles:
            raise BrowserValidationError(
                "browser profile pool contains attach-only profiles; "
                "set allow_attach_only to true or remove: "
                + ", ".join(attach_only_profiles),
            )

    def _raise_if_pool_allocation_active(self, pool_id: str, *, action: str) -> None:
        if self.allocation_store is None:
            return
        normalized_pool = pool_id.strip().lower()
        for allocation in self.allocation_store.list_allocations():
            if allocation.pool_id == normalized_pool and allocation.status == "active":
                raise BrowserValidationError(
                    f"Cannot {action} browser profile pool '{pool_id}' while allocation '{allocation.allocation_id}' is active. Release it first.",
                )

    def _emit_pool_event(
        self,
        event_name: str,
        *,
        pool: BrowserProfilePool,
        status: str,
        changed_fields: tuple[str, ...] = (),
    ) -> None:
        emit_browser_event(
            self.event_emitter,
            event_name,
            status=status,
            payload=_pool_event_payload(pool, changed_fields=changed_fields),
        )


@dataclass(slots=True)
class BrowserProfileAllocatorService:
    allocation_store: BrowserProfileAllocationStore
    pool_store: BrowserProfilePoolStore
    system_config_store: BrowserSystemConfigStore
    runtime_state_store: BrowserRuntimeStateStore
    target_recycler: BrowserAllocationTargetRecycler | None = None
    target_inspector: BrowserAllocationTargetInspector | None = None
    event_emitter: BrowserEventEmitter | None = None

    def list_allocations(
        self,
        *,
        status: str | None = None,
        pool_id: str | None = None,
        profile_name: str | None = None,
        active_only: bool = False,
    ) -> tuple[BrowserProfileAllocation, ...]:
        self.expire_allocations()
        allocations = self.allocation_store.list_allocations()
        normalized_status = status.strip().lower() if status else None
        normalized_pool = pool_id.strip().lower() if pool_id else None
        normalized_profile = profile_name.strip().lower() if profile_name else None
        if active_only:
            normalized_status = "active"
        return tuple(
            allocation
            for allocation in allocations
            if (normalized_status is None or allocation.status == normalized_status)
            and (normalized_pool is None or allocation.pool_id == normalized_pool)
            and (normalized_profile is None or allocation.profile_name == normalized_profile)
        )

    def get_allocation(self, *, allocation_id: str) -> BrowserProfileAllocation:
        allocation = self.allocation_store.get_allocation(allocation_id=allocation_id)
        if allocation is None:
            raise BrowserValidationError(
                f"Browser profile allocation '{allocation_id}' is not configured.",
            )
        if allocation.status == "active" and allocation.expires_at <= _utc_now():
            self.expire_allocations()
            allocation = self.allocation_store.get_allocation(allocation_id=allocation_id)
            if allocation is None:
                raise BrowserValidationError(
                    f"Browser profile allocation '{allocation_id}' is not configured.",
                )
        return allocation

    def allocate(
        self,
        *,
        consumer_kind: str,
        consumer_id: str,
        pool_id: str | None = None,
        profile_name: str | None = None,
        target_host: str | None = None,
        now: datetime | None = None,
    ) -> BrowserProfileAllocation:
        current_time = now or _utc_now()
        self.expire_allocations(now=current_time)
        system = self.system_config_store.load()
        profiles = {profile.name: profile for profile in system.profiles}
        pool = self._resolve_pool(pool_id)
        synthetic_pool_id = (
            pool.pool_id
            if pool is not None
            else f"profile:{(profile_name or system.default_profile).strip().lower()}"
        )
        normalized_consumer_kind = consumer_kind.strip().lower()
        normalized_consumer_id = consumer_id.strip()
        normalized_target_host = target_host.strip().lower() if target_host else None
        reusable = self._find_reusable_allocation(
            pool_id=synthetic_pool_id,
            consumer_kind=normalized_consumer_kind,
            consumer_id=normalized_consumer_id,
            target_host=normalized_target_host,
            now=current_time,
        )
        if reusable is not None:
            return reusable

        selected_profile, selection_reason = self._select_profile(
            profiles=profiles,
            pool=pool,
            profile_name=profile_name,
            default_profile=system.default_profile,
            now=current_time,
        )
        ttl_seconds = pool.allocation_ttl_seconds if pool is not None else 900
        allocation = BrowserProfileAllocation(
            allocation_id=f"browser_alloc_{uuid4().hex}",
            pool_id=synthetic_pool_id,
            profile_name=selected_profile.name,
            consumer_kind=normalized_consumer_kind,  # type: ignore[arg-type]
            consumer_id=normalized_consumer_id,
            target_host=normalized_target_host,
            status="active",
            acquired_at=current_time,
            expires_at=current_time + timedelta(seconds=ttl_seconds),
            metadata={
                "selection_reason": selection_reason,
                "profile_source": (
                    "pool_allocation" if pool is not None else "explicit_profile"
                ),
                "host_service_key": f"host:browser:{selected_profile.name}",
            },
        )
        saved = self.allocation_store.save_allocation(allocation)
        self._emit_allocation_event(
            BROWSER_ALLOCATION_ACQUIRED_EVENT,
            allocation=saved,
            status="acquired",
        )
        return saved

    def release_allocation(
        self,
        *,
        allocation_id: str,
        reason: str = "released",
        failed: bool = False,
        recycle_targets: bool | None = None,
        now: datetime | None = None,
    ) -> BrowserProfileAllocation:
        allocation = self.allocation_store.get_allocation(allocation_id=allocation_id)
        if allocation is None:
            raise BrowserValidationError(
                f"Browser profile allocation '{allocation_id}' is not configured.",
            )
        if allocation.status != "active":
            return allocation
        current_time = now or _utc_now()
        should_recycle = self._should_recycle_targets(
            allocation,
            reason_kind="release",
            explicit=recycle_targets,
        )
        metadata = self._recycle_target_metadata(
            allocation,
            reason=reason,
        ) if should_recycle else dict(allocation.metadata)
        updated = replace(
            allocation,
            status="failed" if failed else "released",
            released_at=current_time,
            release_reason=reason,
            metadata=metadata,
        )
        saved = self.allocation_store.save_allocation(updated)
        self._emit_allocation_event(
            BROWSER_ALLOCATION_FAILED_EVENT
            if failed
            else BROWSER_ALLOCATION_RELEASED_EVENT,
            allocation=saved,
            status=saved.status,
        )
        return saved

    def fail_allocation(
        self,
        *,
        allocation_id: str,
        reason: str = "failed",
        now: datetime | None = None,
    ) -> BrowserProfileAllocation:
        return self.release_allocation(
            allocation_id=allocation_id,
            reason=reason,
            failed=True,
            now=now,
        )

    def heartbeat_allocation(
        self,
        *,
        allocation_id: str,
        ttl_seconds: int | None = None,
        now: datetime | None = None,
    ) -> BrowserProfileAllocation:
        current_time = now or _utc_now()
        allocation = self.get_allocation(allocation_id=allocation_id)
        if not allocation.is_active_at(current_time):
            expired = self.expire_allocations(now=current_time)
            refreshed = self.allocation_store.get_allocation(
                allocation_id=allocation.allocation_id,
            )
            allocation = refreshed or allocation
            if allocation.status != "active":
                raise BrowserValidationError(
                    f"Browser profile allocation '{allocation_id}' is not active.",
                )
            if any(item.allocation_id == allocation.allocation_id for item in expired):
                raise BrowserValidationError(
                    f"Browser profile allocation '{allocation_id}' expired before heartbeat.",
                )
        extension_seconds = (
            _require_positive_int(ttl_seconds, label="ttl_seconds")
            if ttl_seconds is not None
            else self._allocation_ttl_seconds(allocation)
        )
        updated = replace(
            allocation,
            expires_at=current_time + timedelta(seconds=extension_seconds),
            last_heartbeat_at=current_time,
            metadata={
                **dict(allocation.metadata),
                "last_heartbeat_at": current_time.isoformat(),
            },
        )
        saved = self.allocation_store.save_allocation(updated)
        self._emit_allocation_event(
            BROWSER_ALLOCATION_HEARTBEATED_EVENT,
            allocation=saved,
            status="heartbeated",
        )
        return saved

    def reconcile_allocation(
        self,
        *,
        allocation_id: str,
        now: datetime | None = None,
    ) -> BrowserProfileAllocation:
        current_time = now or _utc_now()
        allocation = self.get_allocation(allocation_id=allocation_id)
        if allocation.status != "active":
            return allocation
        if allocation.expires_at <= current_time:
            expired = self.expire_allocations(now=current_time)
            for item in expired:
                if item.allocation_id == allocation.allocation_id:
                    return item
            refreshed = self.allocation_store.get_allocation(
                allocation_id=allocation.allocation_id,
            )
            return refreshed or allocation
        if self.target_inspector is None or not allocation.owned_target_ids:
            updated = replace(
                allocation,
                metadata={
                    **dict(allocation.metadata),
                    "target_reconcile": {
                        "status": "not_required",
                        "checked_at": current_time.isoformat(),
                    },
                },
            )
            return self.allocation_store.save_allocation(updated)
        try:
            live_target_ids = self.target_inspector.list_target_ids(
                profile_name=allocation.profile_name,
            )
        except BrowserValidationError as exc:
            return self._mark_allocation_lost(
                allocation,
                reason="target_reconcile_failed",
                now=current_time,
                metadata={
                    "target_reconcile": {
                        "status": "failed",
                        "checked_at": current_time.isoformat(),
                        "error": str(exc)[:500],
                    },
                },
            )
        live_set = set(live_target_ids)
        kept_targets = tuple(
            target_id for target_id in allocation.owned_target_ids if target_id in live_set
        )
        missing_targets = tuple(
            target_id
            for target_id in allocation.owned_target_ids
            if target_id not in live_set
        )
        reconcile_metadata = {
            "status": "ok" if not missing_targets else "missing_targets",
            "checked_at": current_time.isoformat(),
            "live_target_ids": list(live_target_ids),
            "missing_target_ids": list(missing_targets),
        }
        if missing_targets and not kept_targets:
            return self._mark_allocation_lost(
                allocation,
                reason="target_lost",
                now=current_time,
                metadata={"target_reconcile": reconcile_metadata},
            )
        updated = replace(
            allocation,
            owned_target_ids=kept_targets,
            metadata={
                **dict(allocation.metadata),
                "target_reconcile": reconcile_metadata,
            },
        )
        return self.allocation_store.save_allocation(updated)

    def reconcile_allocations(
        self,
        *,
        now: datetime | None = None,
    ) -> tuple[BrowserProfileAllocation, ...]:
        current_time = now or _utc_now()
        reconciled: list[BrowserProfileAllocation] = []
        for allocation in self.list_allocations(active_only=True):
            reconciled.append(
                self.reconcile_allocation(
                    allocation_id=allocation.allocation_id,
                    now=current_time,
                ),
            )
        return tuple(reconciled)

    def expire_allocations(
        self,
        *,
        recycle_targets: bool | None = None,
        now: datetime | None = None,
    ) -> tuple[BrowserProfileAllocation, ...]:
        current_time = now or _utc_now()
        expired: list[BrowserProfileAllocation] = []
        for allocation in self.allocation_store.list_allocations():
            if allocation.status != "active" or allocation.expires_at > current_time:
                continue
            should_recycle = self._should_recycle_targets(
                allocation,
                reason_kind="expire",
                explicit=recycle_targets,
            )
            metadata = self._recycle_target_metadata(
                allocation,
                reason="ttl_expired",
            ) if should_recycle else dict(allocation.metadata)
            updated = replace(
                allocation,
                status="expired",
                released_at=current_time,
                release_reason="ttl_expired",
                metadata=metadata,
            )
            saved = self.allocation_store.save_allocation(updated)
            self._emit_allocation_event(
                BROWSER_ALLOCATION_EXPIRED_EVENT,
                allocation=saved,
                status="expired",
            )
            expired.append(saved)
        return tuple(expired)

    def drain_pool(
        self,
        *,
        pool_id: str,
        reason: str = "pool_drained",
        recycle_targets: bool | None = None,
        now: datetime | None = None,
    ) -> tuple[BrowserProfileAllocation, ...]:
        pool = self._get_pool(pool_id, require_enabled=False)
        current_time = now or _utc_now()
        drained: list[BrowserProfileAllocation] = []
        for allocation in self.list_allocations(
            pool_id=pool.pool_id,
            active_only=True,
        ):
            drained.append(
                self.release_allocation(
                    allocation_id=allocation.allocation_id,
                    reason=reason,
                    recycle_targets=recycle_targets,
                    now=current_time,
                )
            )
        return tuple(drained)

    def remember_allocation_target(
        self,
        *,
        allocation_id: str,
        target_id: str,
    ) -> BrowserProfileAllocation:
        allocation = self.get_allocation(allocation_id=allocation_id)
        normalized_target = target_id.strip()
        if allocation.status != "active" or not normalized_target:
            return allocation
        if normalized_target in allocation.owned_target_ids:
            return allocation
        updated = replace(
            allocation,
            owned_target_ids=(*allocation.owned_target_ids, normalized_target),
            metadata={
                **dict(allocation.metadata),
                "last_owned_target_id": normalized_target,
            },
        )
        return self.allocation_store.save_allocation(updated)

    def forget_allocation_target(
        self,
        *,
        allocation_id: str,
        target_id: str,
    ) -> BrowserProfileAllocation:
        allocation = self.get_allocation(allocation_id=allocation_id)
        normalized_target = target_id.strip()
        if allocation.status != "active" or not normalized_target:
            return allocation
        remaining = tuple(
            owned_target_id
            for owned_target_id in allocation.owned_target_ids
            if owned_target_id != normalized_target
        )
        if remaining == allocation.owned_target_ids:
            return allocation
        updated = replace(
            allocation,
            owned_target_ids=remaining,
            metadata={
                **dict(allocation.metadata),
                "last_released_target_id": normalized_target,
            },
        )
        return self.allocation_store.save_allocation(updated)

    def _recycle_target_metadata(
        self,
        allocation: BrowserProfileAllocation,
        *,
        reason: str,
    ) -> dict[str, Any]:
        metadata = dict(allocation.metadata)
        if self.target_recycler is None or not allocation.owned_target_ids:
            return metadata
        closed_target_ids: list[str] = []
        failed_targets: list[dict[str, str]] = []
        for target_id in allocation.owned_target_ids:
            try:
                self.target_recycler.close_owned_target(
                    profile_name=allocation.profile_name,
                    target_id=target_id,
                )
            except BrowserValidationError as exc:
                message = str(exc)
                if "not found" in message.lower():
                    closed_target_ids.append(target_id)
                    continue
                failed_targets.append(
                    {
                        "target_id": target_id,
                        "reason": message[:500],
                    },
                )
            else:
                closed_target_ids.append(target_id)
        metadata["target_recycle"] = {
            "reason": reason,
            "closed_target_ids": closed_target_ids,
            "failed_targets": failed_targets,
        }
        return metadata

    def _should_recycle_targets(
        self,
        allocation: BrowserProfileAllocation,
        *,
        reason_kind: str,
        explicit: bool | None,
    ) -> bool:
        if explicit is not None:
            return explicit
        pool = self.pool_store.get_pool(pool_id=allocation.pool_id)
        if pool is not None:
            return (
                pool.close_targets_on_expire
                if reason_kind == "expire"
                else pool.close_targets_on_release
            )
        system = self.system_config_store.load()
        profile = self._profile_or_raise(
            {profile.name: profile for profile in system.profiles},
            allocation.profile_name,
        )
        return (
            profile.close_targets_on_expire
            if reason_kind == "expire"
            else profile.close_targets_on_release
        )

    def _allocation_ttl_seconds(self, allocation: BrowserProfileAllocation) -> int:
        pool = self.pool_store.get_pool(pool_id=allocation.pool_id)
        if pool is not None:
            return pool.allocation_ttl_seconds
        duration = int(
            (allocation.expires_at - allocation.acquired_at).total_seconds(),
        )
        return max(duration, 1)

    def _mark_allocation_lost(
        self,
        allocation: BrowserProfileAllocation,
        *,
        reason: str,
        now: datetime,
        metadata: Mapping[str, Any] | None = None,
    ) -> BrowserProfileAllocation:
        updated = replace(
            allocation,
            status="lost",
            released_at=now,
            release_reason=reason,
            metadata={
                **dict(allocation.metadata),
                **dict(metadata or {}),
            },
        )
        saved = self.allocation_store.save_allocation(updated)
        self._emit_allocation_event(
            BROWSER_ALLOCATION_LOST_EVENT,
            allocation=saved,
            status="lost",
        )
        return saved

    def _resolve_pool(self, pool_id: str | None) -> BrowserProfilePool | None:
        if pool_id is None or not pool_id.strip():
            return None
        return self._get_pool(pool_id)

    def _get_pool(self, pool_id: str, *, require_enabled: bool = True) -> BrowserProfilePool:
        pool = self.pool_store.get_pool(pool_id=pool_id.strip().lower())
        if pool is None:
            raise BrowserValidationError(
                f"Browser profile pool '{pool_id}' is not configured.",
            )
        if require_enabled and not pool.enabled:
            raise BrowserValidationError(
                f"Browser profile pool '{pool.pool_id}' is disabled.",
            )
        return pool

    def _find_reusable_allocation(
        self,
        *,
        pool_id: str,
        consumer_kind: str,
        consumer_id: str,
        target_host: str | None,
        now: datetime,
    ) -> BrowserProfileAllocation | None:
        for allocation in self.allocation_store.list_allocations():
            if not allocation.is_active_at(now):
                continue
            if allocation.matches_consumer(
                pool_id=pool_id,
                consumer_kind=consumer_kind,
                consumer_id=consumer_id,
                target_host=target_host,
            ):
                return allocation
        return None

    def _select_profile(
        self,
        *,
        profiles: dict[str, BrowserProfileConfig],
        pool: BrowserProfilePool | None,
        profile_name: str | None,
        default_profile: str,
        now: datetime,
    ) -> tuple[BrowserProfileConfig, str]:
        requested_profile = profile_name.strip().lower() if profile_name else None
        if pool is None:
            profile = self._profile_or_raise(
                profiles,
                requested_profile or default_profile,
            )
            if not profile.enabled:
                raise BrowserValidationError(
                    f"Browser profile '{profile.name}' is disabled.",
                )
            return profile, "explicit_profile"

        if requested_profile is not None:
            if requested_profile not in pool.profile_names:
                raise BrowserValidationError(
                    f"Browser profile '{requested_profile}' is not a member of pool '{pool.pool_id}'.",
                )
            if pool.selection_strategy != "manual_only":
                raise BrowserValidationError(
                    "profile and profile_pool can be combined only when pool selection_strategy is manual_only.",
                )
            profile = self._profile_or_raise(profiles, requested_profile)
            self._validate_pool_profile_candidate(pool=pool, profile=profile)
            return profile, "manual_pool_profile"

        if pool.selection_strategy == "manual_only":
            raise BrowserValidationError(
                f"Browser profile pool '{pool.pool_id}' requires an explicit profile.",
            )

        active_allocations = tuple(
            allocation
            for allocation in self.allocation_store.list_allocations()
            if allocation.pool_id == pool.pool_id and allocation.is_active_at(now)
        )
        if (
            pool.max_concurrency_total is not None
            and len(active_allocations) >= pool.max_concurrency_total
        ):
            raise BrowserValidationError(
                f"Browser profile pool '{pool.pool_id}' reached max concurrency.",
            )
        candidates = tuple(
            profile
            for profile_name in pool.profile_names
            for profile in (profiles.get(profile_name),)
            if profile is not None
            and self._candidate_available(
                pool=pool,
                profile=profile,
                active_allocations=active_allocations,
                now=now,
            )
        )
        if not candidates:
            raise BrowserValidationError(
                f"Browser profile pool '{pool.pool_id}' has no eligible profile.",
            )
        if pool.selection_strategy == "round_robin":
            return self._select_round_robin(pool=pool, candidates=candidates)
        return self._select_least_busy(
            pool=pool,
            candidates=candidates,
            active_allocations=active_allocations,
        )

    def _profile_or_raise(
        self,
        profiles: dict[str, BrowserProfileConfig],
        profile_name: str,
    ) -> BrowserProfileConfig:
        profile = profiles.get(profile_name.strip().lower())
        if profile is None:
            raise BrowserValidationError(
                f"Browser profile '{profile_name}' is not configured.",
            )
        return profile

    def _validate_pool_profile_candidate(
        self,
        *,
        pool: BrowserProfilePool,
        profile: BrowserProfileConfig,
    ) -> None:
        if not profile.enabled:
            raise BrowserValidationError(
                f"Browser profile '{profile.name}' is disabled.",
            )
        if (
            not pool.allow_attach_only
            and (profile.attach_only or profile.driver == "existing-session")
        ):
            raise BrowserValidationError(
                f"Browser profile '{profile.name}' is attach-only and cannot be allocated by pool '{pool.pool_id}'.",
            )

    def _candidate_available(
        self,
        *,
        pool: BrowserProfilePool,
        profile: BrowserProfileConfig,
        active_allocations: tuple[BrowserProfileAllocation, ...],
        now: datetime,
    ) -> bool:
        try:
            self._validate_pool_profile_candidate(pool=pool, profile=profile)
        except BrowserValidationError:
            return False
        if self._runtime_blocked(profile.name):
            return False
        profile_active_count = sum(
            1
            for allocation in active_allocations
            if allocation.profile_name == profile.name
        )
        if profile_active_count >= pool.max_concurrency_per_profile:
            return False
        return not self._profile_in_cooldown(pool=pool, profile_name=profile.name, now=now)

    def _runtime_blocked(self, profile_name: str) -> bool:
        runtime_state = self.runtime_state_store.get(profile_name=profile_name)
        if runtime_state is None:
            return False
        return runtime_state.attachment_status in {"failed", "degraded"}

    def _profile_in_cooldown(
        self,
        *,
        pool: BrowserProfilePool,
        profile_name: str,
        now: datetime,
    ) -> bool:
        for allocation in self.allocation_store.list_allocations():
            if allocation.pool_id != pool.pool_id or allocation.profile_name != profile_name:
                continue
            if allocation.released_at is None:
                continue
            if (
                allocation.status == "failed"
                and allocation.released_at + timedelta(seconds=pool.failure_cooldown_seconds) > now
            ):
                return True
            if (
                allocation.status == "released"
                and allocation.released_at + timedelta(seconds=pool.cooldown_seconds) > now
            ):
                return True
        return False

    def _select_round_robin(
        self,
        *,
        pool: BrowserProfilePool,
        candidates: tuple[BrowserProfileConfig, ...],
    ) -> tuple[BrowserProfileConfig, str]:
        candidate_names = [profile.name for profile in candidates]
        last = next(
            (
                allocation.profile_name
                for allocation in sorted(
                    self.allocation_store.list_allocations(),
                    key=lambda item: item.acquired_at,
                    reverse=True,
                )
                if allocation.pool_id == pool.pool_id
                and allocation.profile_name in candidate_names
            ),
            None,
        )
        if last is None:
            return candidates[0], "round_robin"
        index = candidate_names.index(last)
        return candidates[(index + 1) % len(candidates)], "round_robin"

    def _select_least_busy(
        self,
        *,
        pool: BrowserProfilePool,
        candidates: tuple[BrowserProfileConfig, ...],
        active_allocations: tuple[BrowserProfileAllocation, ...],
    ) -> tuple[BrowserProfileConfig, str]:
        active_counts = {
            profile.name: sum(
                1
                for allocation in active_allocations
                if allocation.profile_name == profile.name
            )
            for profile in candidates
        }
        order = {profile_name: index for index, profile_name in enumerate(pool.profile_names)}
        return min(
            candidates,
            key=lambda profile: (active_counts[profile.name], order.get(profile.name, 9999)),
        ), "least_busy"

    def _emit_allocation_event(
        self,
        event_name: str,
        *,
        allocation: BrowserProfileAllocation,
        status: str,
    ) -> None:
        emit_browser_event(
            self.event_emitter,
            event_name,
            status=status,
            payload=_allocation_event_payload(allocation),
        )
