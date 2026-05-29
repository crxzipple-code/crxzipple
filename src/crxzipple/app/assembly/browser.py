"""Browser module app assembly."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from crxzipple.app.keys import AppKey
from crxzipple.app.plan import ApplicationFactory
from crxzipple.app.assembly.daemon import browser_profile_daemon_service_spec
from crxzipple.core.config import DEFAULT_BROWSER_DEFAULT_PROFILE_NAME, Settings
from crxzipple.modules.browser.application.events import browser_event_from_payload
from crxzipple.modules.browser.application import (
    BrowserExecutionCoordinatorService,
    BrowserNetworkCaptureService,
    BrowserProfileAdminService,
    BrowserProfileAllocatorService,
    BrowserProfilePoolService,
    BrowserProfileQueryService,
    BrowserRuntimeStateStore,
    BrowserToolApplicationService,
    DefaultBrowserAllocationTargetInspector,
    DefaultBrowserAllocationTargetRecycler,
    DefaultBrowserCapabilitiesResolver,
    DefaultBrowserControlCommandAssembler,
    DefaultBrowserExecutionPlanner,
    DefaultBrowserPageActionAssembler,
    DefaultBrowserProfileResolver,
    DefaultBrowserProfileSelectionOpsFactory,
    DefaultBrowserProfileTabOpsFactory,
)
from crxzipple.modules.browser.domain import BrowserProfileConfig, BrowserSystemConfig
from crxzipple.modules.browser.infrastructure import (
    BrowserProfileProbeService,
    BrowserStateRoot,
    CdpBackedPlaywrightActionEngine,
    CdpControlEngine,
    BrowserEnvironmentControlService,
    BrowserDiagnosticsService,
    FileBackedBrowserProfileAllocationStore,
    FileBackedBrowserProfilePoolStore,
    FileBackedBrowserRefStore,
    FileBackedBrowserRuntimeStateStore,
    FileBackedBrowserSystemConfigStore,
    InMemoryBrowserNetworkCaptureStore,
    BrowserPageNetworkFetchService,
    PlaywrightCdpSessionPool,
    StaticBrowserEngineRegistry,
    bootstrap_browser_state_root,
)
from crxzipple.modules.browser.interfaces import (
    BrowserInterfaceFacade,
    BrowserResultSerializer,
)
from crxzipple.modules.daemon import DaemonApplicationService
from crxzipple.modules.events import EventsApplicationService


@dataclass(slots=True)
class DaemonBrowserProfileHostServiceSync:
    daemon_service: DaemonApplicationService

    def sync_profile(
        self,
        *,
        system: BrowserSystemConfig,
        profile: BrowserProfileConfig,
    ) -> None:
        profile_index = next(
            (
                index
                for index, candidate in enumerate(system.profiles)
                if candidate.name == profile.name
            ),
            len(system.profiles),
        )
        self.daemon_service.register_service_spec(
            browser_profile_daemon_service_spec(
                browser_system_config=system,
                profile=profile,
                index=profile_index,
            ),
        )

    def remove_profile(self, *, profile_name: str) -> None:
        normalized_name = profile_name.strip().lower()
        self.daemon_service.remove_service_specs(
            lambda spec: spec.key == f"host:browser:{normalized_name}",
        )


@dataclass(slots=True)
class BrowserInfrastructure:
    system_config: BrowserSystemConfig
    system_config_store: FileBackedBrowserSystemConfigStore
    state_root: BrowserStateRoot
    profile_pool_store: FileBackedBrowserProfilePoolStore
    profile_allocation_store: FileBackedBrowserProfileAllocationStore
    runtime_state_store: BrowserRuntimeStateStore
    ref_store: FileBackedBrowserRefStore
    network_capture_store: InMemoryBrowserNetworkCaptureStore
    network_capture_service: BrowserNetworkCaptureService
    network_page_fetch_service: BrowserPageNetworkFetchService
    cdp_control: CdpControlEngine
    cdp_backed_playwright: CdpBackedPlaywrightActionEngine
    profile_admin_service: BrowserProfileAdminService
    profile_pool_service: BrowserProfilePoolService
    profile_allocator_service: BrowserProfileAllocatorService
    profile_query_service: BrowserProfileQueryService
    profile_probe_service: BrowserProfileProbeService
    profile_resolver: DefaultBrowserProfileResolver
    capabilities_resolver: DefaultBrowserCapabilitiesResolver
    tool_application_service: BrowserToolApplicationService
    facade: BrowserInterfaceFacade
    result_serializer: BrowserResultSerializer
    cleanup_callbacks: tuple[Callable[[], None], ...] = field(default_factory=tuple)


def browser_factories() -> tuple[ApplicationFactory, ...]:
    """Build Browser profile/runtime applications."""

    return (
        ApplicationFactory(
            key="browser.infrastructure",
            provides=(
                AppKey.BROWSER_INFRASTRUCTURE,
                AppKey.BROWSER_SYSTEM_CONFIG_STORE,
                AppKey.BROWSER_PROFILE_POOL_STORE,
                AppKey.BROWSER_PROFILE_ALLOCATION_STORE,
                AppKey.BROWSER_PROFILE_ADMIN_SERVICE,
                AppKey.BROWSER_PROFILE_POOL_SERVICE,
                AppKey.BROWSER_PROFILE_ALLOCATOR_SERVICE,
                AppKey.BROWSER_QUERY_SERVICE,
                AppKey.BROWSER_TOOL_APPLICATION_SERVICE,
                AppKey.BROWSER_FACADE,
                AppKey.BROWSER_RESULT_SERIALIZER,
            ),
            requires=(
                AppKey.CORE_SETTINGS,
                AppKey.DAEMON_SERVICE,
                AppKey.EVENTS_SERVICE,
            ),
            build=_build_browser_infrastructure,
        ),
    )


def _build_browser_infrastructure(ctx) -> BrowserInfrastructure:
    settings = ctx.require(AppKey.CORE_SETTINGS)
    infrastructure = build_browser_infrastructure(
        settings,
        system_config=build_browser_system_config(settings),
        daemon_service=ctx.require(AppKey.DAEMON_SERVICE),
        daemon_manager=(
            ctx.require(AppKey.DAEMON_MANAGER)
            if ctx.has(AppKey.DAEMON_MANAGER)
            else None
        ),
        event_emitter=build_browser_event_emitter(ctx.require(AppKey.EVENTS_SERVICE)),
    )
    return {
        AppKey.BROWSER_INFRASTRUCTURE: infrastructure,
        AppKey.BROWSER_SYSTEM_CONFIG_STORE: infrastructure.system_config_store,
        AppKey.BROWSER_PROFILE_POOL_STORE: infrastructure.profile_pool_store,
        AppKey.BROWSER_PROFILE_ALLOCATION_STORE: infrastructure.profile_allocation_store,
        AppKey.BROWSER_PROFILE_ADMIN_SERVICE: infrastructure.profile_admin_service,
        AppKey.BROWSER_PROFILE_POOL_SERVICE: infrastructure.profile_pool_service,
        AppKey.BROWSER_PROFILE_ALLOCATOR_SERVICE: infrastructure.profile_allocator_service,
        AppKey.BROWSER_QUERY_SERVICE: infrastructure.profile_query_service,
        AppKey.BROWSER_TOOL_APPLICATION_SERVICE: infrastructure.tool_application_service,
        AppKey.BROWSER_FACADE: infrastructure.facade,
        AppKey.BROWSER_RESULT_SERIALIZER: infrastructure.result_serializer,
    }


def build_browser_system_config(settings: Settings) -> BrowserSystemConfig:
    profiles = tuple(
        BrowserProfileConfig(
            name=profile.name,
            driver=profile.driver,
            enabled=profile.enabled,
            cdp_url=profile.cdp_url,
            cdp_port=profile.cdp_port,
            user_data_dir=profile.user_data_dir,
            profile_directory=profile.profile_directory,
            attach_only=profile.attach_only,
            autostart=profile.autostart,
            proxy_mode=profile.proxy_mode,  # type: ignore[arg-type]
            proxy_server=profile.proxy_server,
            proxy_bypass_list=profile.proxy_bypass_list,
            proxy_binding_id=profile.proxy_binding_id,
            proxy_credential_kind=profile.proxy_credential_kind,
            close_targets_on_release=getattr(profile, "close_targets_on_release", True),
            close_targets_on_expire=getattr(profile, "close_targets_on_expire", True),
        )
        for profile in settings.browser_profiles
    )
    resolved_profiles = profiles or (
        BrowserProfileConfig(name=DEFAULT_BROWSER_DEFAULT_PROFILE_NAME),
    )
    default_profile = next(
        (
            profile.name
            for profile in resolved_profiles
            if profile.name == DEFAULT_BROWSER_DEFAULT_PROFILE_NAME
        ),
        resolved_profiles[0].name,
    )
    return BrowserSystemConfig(
        default_profile=default_profile,
        profiles=resolved_profiles,
        headless=settings.browser_headless,
        executable_path=settings.browser_executable_path,
        no_sandbox=False,
        managed_tab_limit=None,
        cdp_host=settings.browser_cdp_host,
        cdp_port_range_start=settings.browser_cdp_port,
        cdp_port_range_end=settings.browser_cdp_port
        + max(len(resolved_profiles) + 16, 32),
    )


def build_browser_infrastructure(
    settings: Settings,
    *,
    system_config: BrowserSystemConfig,
    daemon_service: DaemonApplicationService,
    daemon_manager=None,  # noqa: ANN001
    event_emitter=None,  # noqa: ANN001
) -> BrowserInfrastructure:
    state_root = bootstrap_browser_state_root(
        settings.browser_state_dir,
        system_config=system_config,
    )
    system_config_store = FileBackedBrowserSystemConfigStore(
        state_root.root_dir,
        bootstrap_config=system_config,
    )
    resolved_system_config = system_config_store.load()
    profile_pool_store = FileBackedBrowserProfilePoolStore(state_root.pools_dir)
    profile_allocation_store = FileBackedBrowserProfileAllocationStore(
        state_root.allocations_dir,
    )
    runtime_state_store = FileBackedBrowserRuntimeStateStore(state_root.runtime_dir)
    ref_store = FileBackedBrowserRefStore(state_root.refs_dir)
    network_capture_store = InMemoryBrowserNetworkCaptureStore()
    network_capture_service = BrowserNetworkCaptureService(
        capture_store=network_capture_store,
        event_emitter=event_emitter,
    )
    network_page_fetch_service = BrowserPageNetworkFetchService(
        event_emitter=event_emitter,
    )
    profile_resolver = DefaultBrowserProfileResolver()
    capabilities_resolver = DefaultBrowserCapabilitiesResolver()
    session_pool = PlaywrightCdpSessionPool()
    cdp_control = CdpControlEngine(
        daemon_service=daemon_service,
        daemon_manager=daemon_manager,
        profiles_root=state_root.profiles_dir,
    )
    cdp_backed_playwright = CdpBackedPlaywrightActionEngine(
        session_pool=session_pool,
        ref_store=ref_store,
        daemon_service=daemon_service,
        network_capture_service=network_capture_service,
        network_page_fetch_service=network_page_fetch_service,
        environment_control_service=BrowserEnvironmentControlService(
            event_emitter=event_emitter,
        ),
        diagnostics_service=BrowserDiagnosticsService(event_emitter=event_emitter),
    )
    profile_admin_service = BrowserProfileAdminService(
        system_config_store=system_config_store,
        runtime_state_store=runtime_state_store,
        ref_store=ref_store,
        allocation_store=profile_allocation_store,
        host_service_sync=DaemonBrowserProfileHostServiceSync(
            daemon_service=daemon_service,
        ),
        event_emitter=event_emitter,
    )
    profile_pool_service = BrowserProfilePoolService(
        pool_store=profile_pool_store,
        system_config_store=system_config_store,
        allocation_store=profile_allocation_store,
        event_emitter=event_emitter,
    )
    profile_query_service = BrowserProfileQueryService(
        system_config_store=system_config_store,
        runtime_state_store=runtime_state_store,
        profile_resolver=profile_resolver,
        capabilities_resolver=capabilities_resolver,
        profile_pool_store=profile_pool_store,
        profile_allocation_store=profile_allocation_store,
    )
    profile_probe_service = BrowserProfileProbeService(
        cdp_control=cdp_control,
        playwright_probe=session_pool.probe_connection,
    )
    coordinator = BrowserExecutionCoordinatorService(
        system_config_store=system_config_store,
        profile_resolver=profile_resolver,
        capabilities_resolver=capabilities_resolver,
        runtime_state_store=runtime_state_store,
        ref_store=ref_store,
        execution_planner=DefaultBrowserExecutionPlanner(),
        engine_registry=StaticBrowserEngineRegistry(
            cdp_control=cdp_control,
            cdp_backed_playwright=cdp_backed_playwright,
        ),
        tab_ops_factory=DefaultBrowserProfileTabOpsFactory(),
        selection_ops_factory=DefaultBrowserProfileSelectionOpsFactory(),
    )
    profile_allocator_service = BrowserProfileAllocatorService(
        allocation_store=profile_allocation_store,
        pool_store=profile_pool_store,
        system_config_store=system_config_store,
        runtime_state_store=runtime_state_store,
        target_recycler=DefaultBrowserAllocationTargetRecycler(
            execution_coordinator=coordinator,
        ),
        target_inspector=DefaultBrowserAllocationTargetInspector(
            execution_coordinator=coordinator,
        ),
        event_emitter=event_emitter,
    )
    control_command_assembler = DefaultBrowserControlCommandAssembler()
    page_action_assembler = DefaultBrowserPageActionAssembler()
    tool_application_service = BrowserToolApplicationService(
        control_command_assembler=control_command_assembler,
        page_action_assembler=page_action_assembler,
        execution_coordinator=coordinator,
        runtime_state_store=runtime_state_store,
    )
    return BrowserInfrastructure(
        system_config=resolved_system_config,
        system_config_store=system_config_store,
        state_root=state_root,
        profile_pool_store=profile_pool_store,
        profile_allocation_store=profile_allocation_store,
        runtime_state_store=runtime_state_store,
        ref_store=ref_store,
        network_capture_store=network_capture_store,
        network_capture_service=network_capture_service,
        network_page_fetch_service=network_page_fetch_service,
        cdp_control=cdp_control,
        cdp_backed_playwright=cdp_backed_playwright,
        profile_admin_service=profile_admin_service,
        profile_pool_service=profile_pool_service,
        profile_allocator_service=profile_allocator_service,
        profile_query_service=profile_query_service,
        profile_probe_service=profile_probe_service,
        profile_resolver=profile_resolver,
        capabilities_resolver=capabilities_resolver,
        tool_application_service=tool_application_service,
        facade=BrowserInterfaceFacade(
            control_command_assembler=control_command_assembler,
            page_action_assembler=page_action_assembler,
            execution_coordinator=coordinator,
            profile_probe_service=profile_probe_service,
        ),
        result_serializer=BrowserResultSerializer(),
        cleanup_callbacks=(session_pool.close, cdp_control.close),
    )


def build_browser_event_emitter(events_service: EventsApplicationService | None):
    if not isinstance(events_service, EventsApplicationService):
        return None

    def emit(event_name: str, payload: dict[str, object]) -> None:
        events_service.publish(browser_event_from_payload(event_name, payload))

    return emit


__all__ = [
    "BrowserInfrastructure",
    "build_browser_event_emitter",
    "browser_factories",
    "build_browser_infrastructure",
    "build_browser_system_config",
]
