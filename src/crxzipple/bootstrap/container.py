from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field, replace
import os
from pathlib import Path
import time
from types import SimpleNamespace
from typing import Any

from sqlalchemy import Engine

from crxzipple.core.config import (
    DEFAULT_BROWSER_DEFAULT_PROFILE_NAME,
    PROJECT_ROOT,
    Settings,
    load_settings,
)
from crxzipple.modules.channels import (
    ChannelControlService,
    ChannelInteractionRegistry,
    ChannelInteractionService,
    ChannelProfileApplicationService,
    ChannelRuntimePlanner,
    ChannelRuntimeManager,
    ChannelRuntimeRegistry,
    ChannelStateRoot,
    ChannelSystemConfig,
    LarkChannelRuntimeService,
    WebhookChannelRuntimeService,
    WebChannelRuntimeService,
    FileBackedChannelInteractionRegistryStore,
    FileBackedChannelRuntimeRegistryStore,
    FileBackedChannelSystemConfigStore,
    bootstrap_channel_state_root,
)
from crxzipple.modules.channels.application.event_contracts import (
    channel_event_definitions,
    channel_event_route_contracts,
    channel_event_surfaces,
    channel_event_topic_contracts,
)
from crxzipple.core.db import SessionFactory, build_engine, build_session_factory
from crxzipple.core.logger import get_logger
from crxzipple.modules.browser.application import (
    BrowserExecutionCoordinatorService,
    BrowserProfileAdminService,
    BrowserRuntimeStateStore,
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
    BrowserStateRoot,
    BrowserProfileProbeService,
    CdpBackedPlaywrightActionEngine,
    CdpControlEngine,
    ChromeMcpClientPool,
    FileBackedBrowserRefStore,
    FileBackedBrowserSystemConfigStore,
    FileBackedBrowserRuntimeStateStore,
    McpBackedActionEngine,
    McpControlEngine,
    PlaywrightCdpSessionPool,
    StaticBrowserEngineRegistry,
    bootstrap_browser_state_root,
)
from crxzipple.modules.browser.interfaces import (
    BrowserInterfaceFacade,
    BrowserResultSerializer,
)
from crxzipple.modules.artifacts import (
    ArtifactApplicationService,
    FilesystemArtifactStore,
)
from crxzipple.modules.agent.application import AgentApplicationService
from crxzipple.modules.agent.domain import AgentNotFoundError
from crxzipple.modules.agent.infrastructure.home_config import (
    apply_agent_home_config_payload,
    load_agent_home_config,
    profile_from_agent_home_config_payload,
    write_agent_home_config,
)
from crxzipple.modules.agent.infrastructure.home_files import (
    read_agent_home_files,
    write_agent_home_files,
)
from crxzipple.modules.agent.infrastructure.home_registry import (
    derive_agent_home_root,
    list_registered_agent_homes,
    register_agent_home,
    resolve_registered_agent_home,
)
from crxzipple.modules.agent.infrastructure.home_migration import (
    migrate_agent_home_contents,
)
from crxzipple.modules.agent.infrastructure.home_scaffold import (
    ensure_agent_home_scaffold,
)
from crxzipple.modules.access import AccessApplicationService
from crxzipple.modules.authorization.application import AuthorizationApplicationService
from crxzipple.modules.dispatch.application import (
    DispatchApplicationService,
    DispatchWakeupObserver,
    dispatch_event_observers,
)
from crxzipple.modules.dispatch.application.event_contracts import (
    dispatch_event_definitions,
    dispatch_event_surfaces,
    dispatch_event_topic_contracts,
)
from crxzipple.modules.events import (
    EventContractRegistry,
    EventsApplicationService,
    FileBackedEventsBackend,
    RedisEventsBackend,
    events_event_definitions,
    events_event_surfaces,
    events_event_topic_contracts,
)
from crxzipple.modules.event_relay import (
    EventRelayRuntimeService,
    WorkbenchEventRelayObserver,
)
from crxzipple.modules.operations.application.observation import (
    OperationsEventObserver,
    observed_event_from_record,
)
from crxzipple.modules.operations.application.event_contracts import (
    operations_event_definitions,
    operations_event_surfaces,
)
from crxzipple.modules.operations.application.runtime import (
    OperationsObserverRuntimeService,
    operations_observer_event_names,
)
from crxzipple.modules.operations.infrastructure.observation_store import (
    FileBackedOperationsObservationStore,
)
from crxzipple.modules.operations.infrastructure.persistence.repositories import (
    SqlAlchemyOperationsActionAuditStore,
    SqlAlchemyOperationsProjectionStore,
)
from crxzipple.modules.daemon import (
    DaemonApplicationService,
    DaemonManager,
    DaemonServiceSpec,
    DaemonStateRoot,
    FileBackedDaemonInstanceStore,
    FileBackedDaemonLeaseEventLog,
    FileBackedDaemonLeaseStore,
    FileBackedDaemonServiceSpecStore,
    bootstrap_daemon_state_root,
)
from crxzipple.modules.authorization.infrastructure import (
    AbacAuthorizationEvaluator,
    InMemoryAuthorizationPolicyRepository,
    SqlAlchemyTemporaryAuthorizationGrantRepository,
    YamlAuthorizationPolicyLoader,
)
from crxzipple.modules.llm.application import LlmApplicationService
from crxzipple.modules.llm.domain import LlmApiFamily
from crxzipple.modules.llm.infrastructure import LlmAdapterRegistry
from crxzipple.modules.llm.infrastructure import (
    AnthropicMessagesAdapter,
    GeminiGenerateContentAdapter,
    OpenAIChatCompatibleAdapter,
    OpenAICodexResponsesAdapter,
    OpenAIResponsesAdapter,
)
from crxzipple.modules.memory.application import FileBackedMemoryService
from crxzipple.modules.memory.application.event_contracts import (
    memory_event_definitions,
    memory_event_surfaces,
)
from crxzipple.modules.memory.application.events import memory_event_from_payload
from crxzipple.modules.memory.infrastructure.indexing import (
    FileMemoryIndexManager,
    LocalHashedMemoryEmbeddingProvider,
    OpenAICompatibleMemoryEmbeddingProvider,
)
from crxzipple.modules.memory.infrastructure.storage import FileMemoryStore
from crxzipple.modules.memory.infrastructure.watching import MemoryWatchRegistry
from crxzipple.modules.mobile.application import (
    DefaultMobileActionCommandAssembler,
    DefaultMobileCapabilitiesResolver,
    DefaultMobileControlCommandAssembler,
    DefaultMobileDeviceResolver,
    DefaultMobileExecutionPlanner,
    MobileExecutionCoordinatorService,
)
from crxzipple.modules.mobile.domain import MobileDeviceConfig, MobileSystemConfig
from crxzipple.modules.mobile.infrastructure import (
    AdbBackedMobileActionEngine,
    AdbControlEngine,
    AndroidAdbClient,
    FileBackedMobileRefStore,
    FileBackedMobileRuntimeStateStore,
    FileBackedMobileSystemConfigStore,
    MobileStateRoot,
    StaticMobileEngineRegistry,
    bootstrap_mobile_state_root,
)
from crxzipple.modules.mobile.interfaces import (
    MobileInterfaceFacade,
    MobileResultSerializer,
)
from crxzipple.modules.ocr.application import OcrApplicationService
from crxzipple.modules.ocr.infrastructure import OcrHostClient, PPStructureV3Client
from crxzipple.modules.ocr.interfaces import OcrResultSerializer
from crxzipple.modules.orchestration.application import (
    ApprovalControlService,
    OrchestrationDispatchRecoveryReaction,
    OrchestrationEngine,
    OrchestrationExecutorService,
    OrchestrationInspectionService,
    OrchestrationRunQueryService,
    OrchestrationRuntimeEventService,
    OrchestrationSchedulerService,
    OrchestrationServiceGraph,
    OrchestrationSessionRecorder,
    OrchestrationToolTerminalReaction,
    PromptAssembler,
    RUN_OBSERVATION_EVENT_NAMES,
    RunObservationObserver,
    SessionMessageObservationObserver,
    TOOL_OBSERVATION_SOURCE_EVENT_NAMES,
    ToolRunObservationObserver,
    ToolResolver,
    orchestration_event_definitions,
    orchestration_event_observers,
    orchestration_event_surfaces,
    turn_session_topic,
)
from crxzipple.modules.orchestration.application.cancellation import (
    RunCancellationService,
)
from crxzipple.modules.orchestration.application.event_contracts import (
    orchestration_event_topic_contracts,
)
from crxzipple.modules.orchestration.application.intake_service import (
    OrchestrationIntakeService,
)
from crxzipple.modules.orchestration.infrastructure.adapters import (
    AuthorizationServiceAdapter,
    FileBackedMemoryPortAdapter,
    FileMemoryContextResolver,
    LlmServiceAdapter,
    OrchestrationRunDispatchAdapter,
    ToolServiceAdapter,
)
from crxzipple.modules.orchestration.infrastructure import (
    MemoryBindingService,
)
from crxzipple.modules.process import (
    FilesystemProcessSessionRepository,
    ProcessApplicationService,
    ProcessSupervisor,
    derive_process_store_root,
)
from crxzipple.modules.session.application import (
    SessionApplicationService,
    SessionResolutionService,
)
from crxzipple.modules.skills.application import SkillManager
from crxzipple.modules.skills.application.event_contracts import (
    skill_event_definitions,
    skill_event_surfaces,
)
from crxzipple.modules.skills.application.events import skill_event_from_payload
from crxzipple.modules.skills.infrastructure import FilesystemSkillRepository
from crxzipple.modules.tool.application import (
    ToolApplicationService,
    ToolDispatchEventSubscriber,
    ToolSchedulerRuntimePort,
    ToolRuntimeEventService,
    ToolWorkerRuntimePort,
)
from crxzipple.modules.tool.application.service_support import ToolServiceDependencies
from crxzipple.modules.tool.application.service_graph import build_tool_service_graph
from crxzipple.modules.tool.infrastructure.adapters import ToolRunDispatchAdapter
from crxzipple.modules.tool.infrastructure import (
    build_sandbox_backend,
    FilesystemLocalToolDiscoveryProvider,
    LocalAsyncToolExecutor,
    LocalCatalogDiscoveryProvider,
    LocalToolCatalog,
    McpDiscoveryProvider,
    McpStdioClient,
    OpenApiDiscoveryProvider,
    RemoteAsyncToolExecutor,
    SandboxAsyncToolExecutor,
    ToolDiscoveryRegistry,
    ToolRuntimeRegistry,
    ToolRuntimeRouter,
    register_scanned_tool_packages,
    register_mcp_remote_handlers,
    register_openapi_remote_handlers,
)
from crxzipple.shared.infrastructure import (
    EventsBackedEventBus,
    SqlAlchemyUnitOfWork,
    close_async_http_clients_sync,
)
from crxzipple.shared.infrastructure.event_bus import EventBus
from crxzipple.shared.runtime_metrics import get_runtime_metrics_registry
from crxzipple.shared import (
    EventDefinitionRegistry,
    ORCHESTRATION_RUN_LLM_TEXT_DELTA_EVENT,
)

logger = get_logger(__name__)


@dataclass(slots=True)
class AppContainer:
    settings: Settings
    engine: Engine
    session_factory: SessionFactory
    event_bus: EventBus
    events_service: EventsApplicationService | None
    event_contract_registry: EventContractRegistry
    event_definition_registry: EventDefinitionRegistry
    channel_system_config: ChannelSystemConfig
    channel_system_config_store: FileBackedChannelSystemConfigStore
    channel_interaction_registry_store: FileBackedChannelInteractionRegistryStore
    channel_runtime_registry_store: FileBackedChannelRuntimeRegistryStore
    channel_state_root: ChannelStateRoot
    channel_interaction_service: ChannelInteractionService
    channel_profile_service: ChannelProfileApplicationService
    channel_control_service: ChannelControlService
    channel_runtime_planner: ChannelRuntimePlanner
    channel_runtime_manager: ChannelRuntimeManager
    lark_channel_runtime_service: LarkChannelRuntimeService
    web_channel_runtime_service: WebChannelRuntimeService
    webhook_channel_runtime_service: WebhookChannelRuntimeService
    local_tool_catalog: LocalToolCatalog
    tool_discovery_registry: ToolDiscoveryRegistry
    sandbox_tool_registry: ToolRuntimeRegistry
    remote_tool_registry: ToolRuntimeRegistry
    llm_adapter_registry: LlmAdapterRegistry
    access_service: AccessApplicationService
    authorization_service: AuthorizationApplicationService
    uow_factory: Callable[[], SqlAlchemyUnitOfWork]
    browser_system_config: BrowserSystemConfig
    browser_system_config_store: FileBackedBrowserSystemConfigStore
    browser_state_root: BrowserStateRoot
    browser_facade: BrowserInterfaceFacade
    browser_result_serializer: BrowserResultSerializer
    browser_runtime_state_store: FileBackedBrowserRuntimeStateStore
    browser_cdp_control: CdpControlEngine
    browser_profile_admin_service: BrowserProfileAdminService
    browser_profile_probe_service: BrowserProfileProbeService
    browser_profile_resolver: DefaultBrowserProfileResolver
    browser_capabilities_resolver: DefaultBrowserCapabilitiesResolver
    mobile_system_config: MobileSystemConfig
    mobile_system_config_store: FileBackedMobileSystemConfigStore
    mobile_state_root: MobileStateRoot
    mobile_facade: MobileInterfaceFacade
    mobile_result_serializer: MobileResultSerializer
    mobile_runtime_state_store: FileBackedMobileRuntimeStateStore
    ocr_service: OcrApplicationService
    ocr_result_serializer: OcrResultSerializer
    daemon_state_root: DaemonStateRoot
    daemon_service: DaemonApplicationService
    daemon_manager: DaemonManager
    daemon_spec_syncers: tuple[Callable[[], object], ...]
    dispatch_service: DispatchApplicationService
    event_relay_runtime_event_service: EventRelayRuntimeService | None
    operations_observation_store: FileBackedOperationsObservationStore
    operations_action_audit_store: SqlAlchemyOperationsActionAuditStore
    operations_projection_store: SqlAlchemyOperationsProjectionStore
    operations_projection_materializer: Any | None
    operations_observer_runtime_event_service: OperationsObserverRuntimeService | None
    tool_runtime_event_service: ToolRuntimeEventService | None
    orchestration_run_query_service: OrchestrationRunQueryService
    orchestration_inspection_service: OrchestrationInspectionService
    orchestration_approval_control_service: ApprovalControlService
    orchestration_cancellation_service: RunCancellationService
    orchestration_intake_service: OrchestrationIntakeService
    orchestration_scheduler_service: OrchestrationSchedulerService
    orchestration_scheduler_runtime_event_service: OrchestrationRuntimeEventService | None
    orchestration_executor_service: OrchestrationExecutorService
    tool_service: ToolApplicationService
    tool_scheduler_service: ToolSchedulerRuntimePort
    tool_worker_service: ToolWorkerRuntimePort
    process_service: ProcessApplicationService
    session_service: SessionApplicationService
    session_resolution_service: SessionResolutionService
    llm_service: LlmApplicationService
    file_memory_service: FileBackedMemoryService
    memory_context_resolver: FileMemoryContextResolver
    memory_watch_registry: MemoryWatchRegistry | None
    agent_service: AgentApplicationService
    skill_manager: SkillManager
    artifact_service: ArtifactApplicationService
    cleanup_callbacks: tuple[Callable[[], None], ...] = field(default_factory=tuple)
    _closed: bool = field(default=False, init=False, repr=False)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        for callback in self.cleanup_callbacks:
            try:
                callback()
            except Exception:
                logger.exception("container cleanup callback failed")
        self.engine.dispose()

@dataclass(slots=True)
class _ToolInfrastructure:
    local_tool_catalog: LocalToolCatalog
    tool_discovery_registry: ToolDiscoveryRegistry
    sandbox_tool_registry: ToolRuntimeRegistry
    remote_tool_registry: ToolRuntimeRegistry
    tool_runtime_gateway: ToolRuntimeRouter
    cleanup_callbacks: tuple[Callable[[], None], ...] = field(default_factory=tuple)


@dataclass(slots=True)
class _RuntimeServices:
    tool_service: ToolApplicationService
    tool_scheduler_service: ToolSchedulerRuntimePort
    tool_worker_service: ToolWorkerRuntimePort
    access_service: AccessApplicationService
    orchestration_service_graph: OrchestrationServiceGraph
    orchestration_run_query_service: OrchestrationRunQueryService
    orchestration_inspection_service: OrchestrationInspectionService
    orchestration_approval_control_service: ApprovalControlService
    orchestration_cancellation_service: RunCancellationService
    orchestration_intake_service: OrchestrationIntakeService
    orchestration_scheduler_service: OrchestrationSchedulerService
    orchestration_executor_service: OrchestrationExecutorService
    skill_manager: SkillManager


@dataclass(slots=True)
class _ChannelsInfrastructure:
    system_config: ChannelSystemConfig
    system_config_store: FileBackedChannelSystemConfigStore
    interaction_registry_store: FileBackedChannelInteractionRegistryStore
    runtime_registry_store: FileBackedChannelRuntimeRegistryStore
    state_root: ChannelStateRoot
    interaction_service: ChannelInteractionService
    profile_service: ChannelProfileApplicationService
    runtime_planner: ChannelRuntimePlanner
    runtime_manager: ChannelRuntimeManager


@dataclass(slots=True)
class _BrowserInfrastructure:
    system_config: BrowserSystemConfig
    system_config_store: FileBackedBrowserSystemConfigStore
    state_root: BrowserStateRoot
    runtime_state_store: BrowserRuntimeStateStore
    ref_store: FileBackedBrowserRefStore
    cdp_control: CdpControlEngine
    cdp_backed_playwright: CdpBackedPlaywrightActionEngine
    mcp_pool: ChromeMcpClientPool
    profile_admin_service: BrowserProfileAdminService
    profile_probe_service: BrowserProfileProbeService
    profile_resolver: DefaultBrowserProfileResolver
    capabilities_resolver: DefaultBrowserCapabilitiesResolver
    facade: BrowserInterfaceFacade
    result_serializer: BrowserResultSerializer
    cleanup_callbacks: tuple[Callable[[], None], ...] = field(default_factory=tuple)


@dataclass(slots=True)
class _CoreServices:
    session_service: SessionApplicationService
    session_resolution_service: SessionResolutionService
    llm_service: LlmApplicationService
    agent_service: AgentApplicationService
    file_memory_service: FileBackedMemoryService
    memory_context_resolver: FileMemoryContextResolver
    memory_watch_registry: MemoryWatchRegistry | None
    memory_port: FileBackedMemoryPortAdapter
    dispatch_service: DispatchApplicationService


@dataclass(slots=True)
class _MobileInfrastructure:
    system_config: MobileSystemConfig
    system_config_store: FileBackedMobileSystemConfigStore
    state_root: MobileStateRoot
    runtime_state_store: FileBackedMobileRuntimeStateStore
    ref_store: FileBackedMobileRefStore
    control_engine: AdbControlEngine
    action_engine: AdbBackedMobileActionEngine
    facade: MobileInterfaceFacade
    result_serializer: MobileResultSerializer


@dataclass(slots=True)
class _DaemonInfrastructure:
    state_root: DaemonStateRoot
    service_spec_store: FileBackedDaemonServiceSpecStore
    instance_store: FileBackedDaemonInstanceStore
    lease_store: FileBackedDaemonLeaseStore
    lease_event_log: FileBackedDaemonLeaseEventLog
    service: DaemonApplicationService


def _build_channels_infrastructure(settings: Settings) -> _ChannelsInfrastructure:
    bootstrap_config = ChannelSystemConfig(profiles=settings.channel_profiles)
    bootstrap_interactions = ChannelInteractionRegistry()
    bootstrap_registry = ChannelRuntimeRegistry()
    state_root = bootstrap_channel_state_root(
        settings.channels_state_dir,
        system_config=bootstrap_config,
        interaction_registry=bootstrap_interactions,
        runtime_registry=bootstrap_registry,
    )
    system_config_store = FileBackedChannelSystemConfigStore(
        state_root.root_dir,
        bootstrap_config=bootstrap_config,
    )
    interaction_registry_store = FileBackedChannelInteractionRegistryStore(
        state_root.root_dir,
        bootstrap_registry=bootstrap_interactions,
    )
    runtime_registry_store = FileBackedChannelRuntimeRegistryStore(
        state_root.root_dir,
        bootstrap_registry=bootstrap_registry,
    )
    interaction_service = ChannelInteractionService(
        registry_store=interaction_registry_store,
    )
    profile_service = ChannelProfileApplicationService(
        system_config_store=system_config_store,
    )
    for profile in settings.channel_profiles:
        profile_service.upsert_profile(profile)
    runtime_planner = ChannelRuntimePlanner()
    runtime_manager = ChannelRuntimeManager(
        registry_store=runtime_registry_store,
    )
    return _ChannelsInfrastructure(
        system_config=profile_service.get_system_config(),
        system_config_store=system_config_store,
        interaction_registry_store=interaction_registry_store,
        runtime_registry_store=runtime_registry_store,
        state_root=state_root,
        interaction_service=interaction_service,
        profile_service=profile_service,
        runtime_planner=runtime_planner,
        runtime_manager=runtime_manager,
    )


def _build_authorization_service(
    settings: Settings,
    session_factory: SessionFactory,
) -> tuple[AuthorizationApplicationService, int]:
    authorization_policy_paths = tuple(
        dict.fromkeys(
            (
                *settings.authorization_policy_paths,
                settings.authorization_runtime_policy_path,
            ),
        ),
    )
    authorization_policies = YamlAuthorizationPolicyLoader().load_paths(
        authorization_policy_paths,
    )
    service = AuthorizationApplicationService(
        policy_repository=InMemoryAuthorizationPolicyRepository(
            policies=list(authorization_policies),
            managed_path=Path(settings.authorization_runtime_policy_path).expanduser(),
        ),
        evaluator=AbacAuthorizationEvaluator(),
        temporary_grant_repository_factory=(
            lambda: SqlAlchemyTemporaryAuthorizationGrantRepository(session_factory)
        ),
        enabled=settings.authorization_enabled,
    )
    return service, len(authorization_policies)


def _build_llm_adapter_registry() -> LlmAdapterRegistry:
    registry = LlmAdapterRegistry()
    registry.register(
        LlmApiFamily.OPENAI_RESPONSES,
        OpenAIResponsesAdapter(),
    )
    registry.register(
        LlmApiFamily.OPENAI_CODEX_RESPONSES,
        OpenAICodexResponsesAdapter(),
    )
    registry.register(
        LlmApiFamily.OPENAI_CHAT_COMPATIBLE,
        OpenAIChatCompatibleAdapter(),
    )
    registry.register(
        LlmApiFamily.ANTHROPIC_MESSAGES,
        AnthropicMessagesAdapter(),
    )
    registry.register(
        LlmApiFamily.GEMINI_GENERATE_CONTENT,
        GeminiGenerateContentAdapter(),
    )
    return registry


def _build_browser_system_config(settings: Settings) -> BrowserSystemConfig:
    profiles = tuple(
        BrowserProfileConfig(
            name=profile.name,
            driver=profile.driver,
            cdp_url=(
                None
                if profile.driver == "existing-session"
                else profile.cdp_url
            ),
            cdp_port=(
                None
                if profile.driver == "existing-session"
                else profile.cdp_port
            ),
            user_data_dir=profile.user_data_dir,
            attach_only=profile.attach_only,
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
        cdp_port_range_end=settings.browser_cdp_port + max(len(resolved_profiles) + 16, 32),
    )


def _build_browser_infrastructure(
    settings: Settings,
    *,
    system_config: BrowserSystemConfig,
    daemon_service: DaemonApplicationService,
) -> _BrowserInfrastructure:
    state_root = bootstrap_browser_state_root(
        settings.browser_state_dir,
        system_config=system_config,
    )
    system_config_store = FileBackedBrowserSystemConfigStore(
        state_root.root_dir,
        bootstrap_config=system_config,
    )
    resolved_system_config = system_config_store.load()
    runtime_state_store = FileBackedBrowserRuntimeStateStore(state_root.runtime_dir)
    ref_store = FileBackedBrowserRefStore(state_root.refs_dir)
    profile_resolver = DefaultBrowserProfileResolver()
    capabilities_resolver = DefaultBrowserCapabilitiesResolver()
    session_pool = PlaywrightCdpSessionPool()
    mcp_pool = ChromeMcpClientPool(daemon_service=daemon_service)
    cdp_control = CdpControlEngine(
        daemon_service=daemon_service,
        profiles_root=state_root.profiles_dir,
    )
    cdp_backed_playwright = CdpBackedPlaywrightActionEngine(
        session_pool=session_pool,
        ref_store=ref_store,
        daemon_service=daemon_service,
    )
    profile_admin_service = BrowserProfileAdminService(
        system_config_store=system_config_store,
        runtime_state_store=runtime_state_store,
        ref_store=ref_store,
    )
    profile_probe_service = BrowserProfileProbeService(
        cdp_control=cdp_control,
        mcp_pool=mcp_pool,
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
            mcp_control=McpControlEngine(mcp_pool=mcp_pool),
            cdp_backed_playwright=cdp_backed_playwright,
            mcp_backed=McpBackedActionEngine(
                mcp_pool=mcp_pool,
                ref_store=ref_store,
            ),
        ),
        tab_ops_factory=DefaultBrowserProfileTabOpsFactory(),
        selection_ops_factory=DefaultBrowserProfileSelectionOpsFactory(),
    )
    return _BrowserInfrastructure(
        system_config=resolved_system_config,
        system_config_store=system_config_store,
        state_root=state_root,
        runtime_state_store=runtime_state_store,
        ref_store=ref_store,
        cdp_control=cdp_control,
        cdp_backed_playwright=cdp_backed_playwright,
        mcp_pool=mcp_pool,
        profile_admin_service=profile_admin_service,
        profile_probe_service=profile_probe_service,
        profile_resolver=profile_resolver,
        capabilities_resolver=capabilities_resolver,
        facade=BrowserInterfaceFacade(
            control_command_assembler=DefaultBrowserControlCommandAssembler(),
            page_action_assembler=DefaultBrowserPageActionAssembler(),
            execution_coordinator=coordinator,
        ),
        result_serializer=BrowserResultSerializer(),
        cleanup_callbacks=(session_pool.close, mcp_pool.close, cdp_control.close),
    )


def _build_mobile_system_config(settings: Settings) -> MobileSystemConfig:
    devices = tuple(
        MobileDeviceConfig(
            name=device.name,
            platform=device.platform,  # type: ignore[arg-type]
            udid=device.udid,
            app_package=device.app_package,
            app_activity=device.app_activity,
        )
        for device in settings.mobile_devices
    )
    default_device = devices[0].name if devices else None
    return MobileSystemConfig(
        default_device=default_device,
        devices=devices,
        adb_binary=settings.mobile_adb_binary,
    )


def _build_mobile_infrastructure(
    settings: Settings,
    *,
    artifact_service: ArtifactApplicationService,
    ocr_service: OcrApplicationService,
    system_config: MobileSystemConfig,
    daemon_service: DaemonApplicationService,
    daemon_manager: DaemonManager,
) -> _MobileInfrastructure:
    state_root = bootstrap_mobile_state_root(settings.mobile_state_dir)
    system_config_store = FileBackedMobileSystemConfigStore(
        state_root.config_dir,
        bootstrap_config=system_config,
    )
    resolved_system_config = system_config_store.load()
    runtime_state_store = FileBackedMobileRuntimeStateStore(state_root.runtime_dir)
    ref_store = FileBackedMobileRefStore(state_root.refs_dir)
    control_engine = AdbControlEngine()
    action_engine = AdbBackedMobileActionEngine(
        ref_store=ref_store,
        artifact_service=artifact_service,
        ocr_service=ocr_service,
    )
    coordinator = MobileExecutionCoordinatorService(
        system_config_store=system_config_store,
        device_resolver=DefaultMobileDeviceResolver(
            system_config_store=system_config_store,
            device_probe=AndroidAdbClient.probe_adb_devices,
        ),
        capabilities_resolver=DefaultMobileCapabilitiesResolver(),
        runtime_state_store=runtime_state_store,
        execution_planner=DefaultMobileExecutionPlanner(),
        engine_registry=StaticMobileEngineRegistry(
            adb_control=control_engine,
            adb_backed=action_engine,
        ),
    )
    return _MobileInfrastructure(
        system_config=resolved_system_config,
        system_config_store=system_config_store,
        state_root=state_root,
        runtime_state_store=runtime_state_store,
        ref_store=ref_store,
        control_engine=control_engine,
        action_engine=action_engine,
        facade=MobileInterfaceFacade(
            control_command_assembler=DefaultMobileControlCommandAssembler(),
            action_command_assembler=DefaultMobileActionCommandAssembler(),
            execution_coordinator=coordinator,
        ),
        result_serializer=MobileResultSerializer(),
    )


def _build_ocr_engine(settings: Settings) -> OcrHostClient | PPStructureV3Client:
    if settings.ocr_provider == "ppstructurev3":
        return PPStructureV3Client(
            base_url=settings.ocr_base_url,
            timeout_seconds=settings.ocr_request_timeout_seconds,
        )
    return OcrHostClient(
        base_url=settings.ocr_base_url,
        timeout_seconds=settings.ocr_request_timeout_seconds,
    )


def _bootstrap_daemon_specs(
    *,
    settings: Settings,
    browser_system_config: BrowserSystemConfig,
) -> tuple[DaemonServiceSpec, ...]:
    orchestration_executor_cli_args = [
        "orchestration-executor",
        "run-executor",
        "--max-concurrent-assignments",
        str(settings.orchestration_executor_max_concurrent_assignments),
    ]
    tool_worker_cli_args = [
        "tool-worker",
        "run",
        "--max-in-flight",
        str(settings.tool_worker_max_in_flight),
    ]
    specs: list[DaemonServiceSpec] = [
        DaemonServiceSpec(
            key="worker:orchestration-scheduler",
            display_name="Orchestration Scheduler",
            service_group="core",
            role="worker",
            managed_by="internal",
            transport="process",
            replica_mode="singleton",
            desired_replicas=1,
            start_policy="eager",
            restart_policy="on-failure",
            metadata={
                "module": "orchestration",
                "component": "scheduler",
                "application_service": "orchestration_scheduler_service",
                "run_method": "run_until_stopped",
                "cli_args": ["orchestration-scheduler", "run-scheduler"],
            },
        ),
        DaemonServiceSpec(
            key="worker:orchestration",
            display_name="Orchestration Executor",
            service_group="core",
            role="worker",
            managed_by="internal",
            transport="process",
            replica_mode="replicated",
            desired_replicas=1,
            start_policy="eager",
            restart_policy="on-failure",
            metadata={
                "module": "orchestration",
                "component": "executor",
                "application_service": "orchestration_executor_service",
                "run_method": "run_until_stopped",
                "cli_args": orchestration_executor_cli_args,
            },
        ),
        DaemonServiceSpec(
            key="worker:event-relay",
            display_name="Event Relay",
            service_group="core",
            role="worker",
            managed_by="internal",
            transport="process",
            replica_mode="singleton",
            desired_replicas=1,
            start_policy="eager",
            restart_policy="on-failure",
            metadata={
                "module": "event_relay",
                "component": "relay",
                "application_service": "event_relay_runtime_event_service",
                "run_method": "run_until_stopped",
                "cli_args": ["event-relay", "run"],
            },
        ),
        DaemonServiceSpec(
            key="worker:operations-observer",
            display_name="Operations Observer",
            service_group="core",
            role="worker",
            managed_by="internal",
            transport="process",
            replica_mode="singleton",
            desired_replicas=1,
            start_policy="eager",
            restart_policy="on-failure",
            metadata={
                "module": "operations",
                "component": "observer",
                "application_service": "operations_observer_runtime_event_service",
                "run_method": "run_until_stopped",
                "cli_args": ["operations-observer", "run"],
            },
        ),
        DaemonServiceSpec(
            key="worker:tool-scheduler",
            display_name="Tool Scheduler",
            service_group="core",
            role="worker",
            managed_by="internal",
            transport="process",
            replica_mode="singleton",
            desired_replicas=1,
            start_policy="eager",
            restart_policy="on-failure",
            metadata={
                "module": "tool",
                "component": "scheduler",
                "application_service": "tool_scheduler_service",
                "run_method": "run_until_stopped",
                "cli_args": ["tool-scheduler", "run-scheduler"],
            },
        ),
        DaemonServiceSpec(
            key="worker:tool",
            display_name="Tool Worker",
            service_group="core",
            role="worker",
            managed_by="internal",
            transport="process",
            replica_mode="replicated",
            desired_replicas=1,
            start_policy="eager",
            restart_policy="on-failure",
            metadata={
                "module": "tool",
                "component": "worker",
                "application_service": "tool_worker_service",
                "run_method": "run_until_stopped",
                "cli_args": tool_worker_cli_args,
            },
        ),
    ]
    for profile in browser_system_config.profiles:
        if profile.driver == "existing-session":
            specs.append(
                DaemonServiceSpec(
                    key=f"capability:chrome-mcp:{profile.name}",
                    display_name=f"Chrome MCP ({profile.name})",
                    service_group="browser",
                    role="capability",
                    managed_by="internal",
                    transport="process",
                    start_policy="lazy",
                    restart_policy="on-failure",
                    metadata={
                        "profile_name": profile.name,
                        "driver": profile.driver,
                        "cli_args": ["browser", "mcp", "run", "--profile", profile.name],
                    },
                ),
            )
            continue
        specs.append(
            DaemonServiceSpec(
                key=f"host:browser:{profile.name}",
                display_name=f"Managed Browser ({profile.name})",
                service_group="browser",
                role="host",
                managed_by="internal",
                transport="process",
                start_policy="ensure",
                restart_policy="on-failure",
                healthcheck_policy="cdp-version",
                match_policy="cdp-port",
                metadata={
                    "profile_name": profile.name,
                    "driver": profile.driver,
                    "attach_only": profile.attach_only,
                    "cdp_url": profile.cdp_url,
                    "cdp_port": profile.cdp_port,
                    "server_url": (
                        profile.cdp_url
                        or (
                            f"http://{browser_system_config.cdp_host}:{profile.cdp_port}"
                            if profile.cdp_port is not None
                            else None
                        )
                    ),
                    "cli_args": ["browser", "host", "run", "--profile", profile.name],
                },
            ),
        )
    if (
        settings.ocr_enabled
        and settings.ocr_backend == "local"
        and settings.ocr_provider == "host"
    ):
        specs.append(
            DaemonServiceSpec(
                key="capability:ocr:default",
                display_name="OCR Host",
                service_group="ocr",
                role="capability",
                managed_by="internal",
                transport="process",
                start_policy="lazy",
                restart_policy="on-failure",
                metadata={
                    "server_url": settings.ocr_base_url,
                    "cli_args": ["ocr", "host", "run"],
                },
            )
        )
    return tuple(specs)


def _build_daemon_infrastructure(
    settings: Settings,
    *,
    browser_system_config: BrowserSystemConfig,
) -> _DaemonInfrastructure:
    state_root = bootstrap_daemon_state_root(settings.daemon_state_dir)
    service_spec_store = FileBackedDaemonServiceSpecStore(
        state_root.config_dir,
        bootstrap_specs=_bootstrap_daemon_specs(
            settings=settings,
            browser_system_config=browser_system_config,
        ),
    )
    instance_store = FileBackedDaemonInstanceStore(state_root.instances_dir)
    lease_store = FileBackedDaemonLeaseStore(state_root.leases_dir)
    lease_event_log = FileBackedDaemonLeaseEventLog(state_root.leases_dir)
    service = DaemonApplicationService(
        service_spec_store=service_spec_store,
        instance_store=instance_store,
        lease_store=lease_store,
        lease_event_log=lease_event_log,
    )
    service.remove_service_specs(
        lambda spec: spec.key.startswith("capability:appium:"),
    )
    return _DaemonInfrastructure(
        state_root=state_root,
        service_spec_store=service_spec_store,
        instance_store=instance_store,
        lease_store=lease_store,
        lease_event_log=lease_event_log,
        service=service,
    )


def _build_tool_infrastructure(
    settings: Settings,
    *,
    browser_infrastructure: _BrowserInfrastructure,
    mobile_infrastructure: _MobileInfrastructure,
) -> _ToolInfrastructure:
    local_tool_catalog = LocalToolCatalog()
    tool_discovery_registry = ToolDiscoveryRegistry()
    sandbox_tool_registry = ToolRuntimeRegistry()
    remote_tool_registry = ToolRuntimeRegistry()

    register_scanned_tool_packages(
        SimpleNamespace(
            local_tool_catalog=local_tool_catalog,
            sandbox_tool_registry=sandbox_tool_registry,
            remote_tool_registry=remote_tool_registry,
            tool_discovery_registry=tool_discovery_registry,
            settings=settings,
            browser_system_config=browser_infrastructure.system_config,
            browser_system_config_store=browser_infrastructure.system_config_store,
            browser_facade=browser_infrastructure.facade,
            browser_result_serializer=browser_infrastructure.result_serializer,
            browser_profile_resolver=browser_infrastructure.profile_resolver,
            browser_capabilities_resolver=browser_infrastructure.capabilities_resolver,
            mobile_system_config=mobile_infrastructure.system_config,
            mobile_system_config_store=mobile_infrastructure.system_config_store,
            mobile_facade=mobile_infrastructure.facade,
            mobile_result_serializer=mobile_infrastructure.result_serializer,
        ),
        include_openapi=os.getenv("APP_TOOL_OPENAPI_PROVIDER_PATHS") is None,
    )
    tool_discovery_registry.register(
        LocalCatalogDiscoveryProvider(local_tool_catalog),
    )
    filesystem_provider = FilesystemLocalToolDiscoveryProvider(
        local_tool_catalog,
        settings.tool_local_paths,
    )
    tool_discovery_registry.register(filesystem_provider)
    filesystem_provider.discover_specs()

    cleanup_callbacks: list[Callable[[], None]] = []
    for provider_settings in settings.tool_mcp_providers:
        mcp_client = McpStdioClient(provider_settings)
        mcp_provider = McpDiscoveryProvider(provider_settings, client=mcp_client)
        tool_discovery_registry.register(mcp_provider)
        register_mcp_remote_handlers(
            remote_tool_registry,
            mcp_provider.definitions(),
            client=mcp_client,
            max_concurrency=(
                provider_settings.max_concurrency
                or settings.tool_remote_default_max_concurrency
            ),
        )
        cleanup_callbacks.append(mcp_client.close)

    for provider_settings in settings.tool_openapi_providers:
        openapi_provider = OpenApiDiscoveryProvider(provider_settings)
        tool_discovery_registry.register(openapi_provider)
        register_openapi_remote_handlers(
            remote_tool_registry,
            openapi_provider.operations(),
            max_concurrency=(
                provider_settings.max_concurrency
                or settings.tool_remote_default_max_concurrency
            ),
        )

    sandbox_backend = build_sandbox_backend(settings)
    tool_runtime_gateway = ToolRuntimeRouter(
        LocalAsyncToolExecutor(local_tool_catalog),
        SandboxAsyncToolExecutor(sandbox_tool_registry, sandbox_backend),
        RemoteAsyncToolExecutor(remote_tool_registry),
    )
    return _ToolInfrastructure(
        local_tool_catalog=local_tool_catalog,
        tool_discovery_registry=tool_discovery_registry,
        sandbox_tool_registry=sandbox_tool_registry,
        remote_tool_registry=remote_tool_registry,
        tool_runtime_gateway=tool_runtime_gateway,
        cleanup_callbacks=tuple(cleanup_callbacks),
    )


def _build_core_services(
    settings: Settings,
    uow_factory: Callable[[], SqlAlchemyUnitOfWork],
    llm_adapter_registry: LlmAdapterRegistry,
    local_tool_catalog: LocalToolCatalog,
    *,
    events_service: EventsApplicationService | None,
    enable_memory_watchers: bool,
) -> _CoreServices:
    llm_service = LlmApplicationService(uow_factory, llm_adapter_registry)
    agent_home_root = str(derive_agent_home_root(settings.database_url))
    memory_binding_service = MemoryBindingService()
    agent_service = AgentApplicationService(
        uow_factory,
        agent_home_root=agent_home_root,
        home_scaffolder=ensure_agent_home_scaffold,
        home_migrator=migrate_agent_home_contents,
        home_config_loader=load_agent_home_config,
        home_config_writer=lambda profile, home_dir: write_agent_home_config(
            profile,
            home_dir=home_dir,
        ),
        home_config_applier=lambda profile, payload, home_dir: (
            apply_agent_home_config_payload(
                profile,
                payload,
                home_dir=home_dir,
            )
        ),
        home_profile_factory=lambda payload, home_dir: (
            profile_from_agent_home_config_payload(payload, home_dir=home_dir)
        ),
        home_registry_lister=lambda root_dir: list_registered_agent_homes(root_dir),
        home_registry_resolver=lambda root_dir, agent_id: resolve_registered_agent_home(
            root_dir,
            agent_id,
        ),
        home_registry_writer=lambda root_dir, agent_id, home_dir: register_agent_home(
            root_dir,
            agent_id=agent_id,
            home_dir=home_dir,
        ),
        home_sidecar_factory=lambda payload, _home_dir: (
            memory_binding_service.sidecar_files_from_agent_home_payload(payload)
        ),
        home_file_reader=read_agent_home_files,
        home_file_writer=write_agent_home_files,
    )

    def _default_workspace_for_agent(agent_id: str) -> str | None:
        try:
            profile = agent_service.get_profile(agent_id)
        except AgentNotFoundError:
            return None
        return profile.runtime_preferences.resolved_home_dir

    session_service = SessionApplicationService(
        uow_factory,
        workspace_defaults_resolver=_default_workspace_for_agent,
    )
    session_resolution_service = SessionResolutionService(session_service)
    file_memory_service = FileBackedMemoryService(
        store=FileMemoryStore(),
        index_manager=FileMemoryIndexManager(
            embedding_provider=_build_memory_embedding_provider(settings),
        ),
        event_emitter=_build_memory_event_emitter(events_service),
    )
    memory_watch_registry = (
        MemoryWatchRegistry(
            memory_service=file_memory_service,
            enabled=True,
            interval_seconds=settings.memory_watch_interval_seconds,
        )
        if enable_memory_watchers
        else None
    )
    file_memory_context_resolver = FileMemoryContextResolver(
        agent_service=agent_service,
        default_retrieval_backend=settings.memory_retrieval_backend,
        binding_loader=lambda home_dir: memory_binding_service.load(home_dir),
        context_observer=(
            memory_watch_registry.ensure_watching
            if memory_watch_registry is not None
            else None
        ),
        event_emitter=_build_memory_event_emitter(events_service),
    )
    memory_port = FileBackedMemoryPortAdapter(
        service=file_memory_service,
        context_resolver=file_memory_context_resolver,
    )
    return _CoreServices(
        session_service=session_service,
        session_resolution_service=session_resolution_service,
        llm_service=llm_service,
        agent_service=agent_service,
        file_memory_service=file_memory_service,
        memory_context_resolver=file_memory_context_resolver,
        memory_watch_registry=memory_watch_registry,
        memory_port=memory_port,
        dispatch_service=DispatchApplicationService(uow_factory),
    )


def _build_memory_embedding_provider(settings: Settings):
    if settings.memory_vector_provider == "openai_compatible":
        return OpenAICompatibleMemoryEmbeddingProvider(
            base_url=settings.memory_vector_base_url or "https://api.openai.com/v1",
            model_name=settings.memory_vector_model or "text-embedding-3-small",
            credential_binding=(
                settings.memory_vector_credential_binding or "env:OPENAI_API_KEY"
            ),
            timeout_seconds=settings.memory_vector_timeout_seconds,
        )
    return LocalHashedMemoryEmbeddingProvider(
        model_name=settings.memory_vector_model or "local-hashed-v1",
    )


def _build_memory_event_emitter(
    events_service: EventsApplicationService | None,
):
    if not isinstance(events_service, EventsApplicationService):
        return None

    def emit(event_name: str, payload: dict[str, object]) -> None:
        events_service.publish(memory_event_from_payload(event_name, payload))

    return emit


def _build_skill_event_emitter(
    events_service: EventsApplicationService | None,
):
    if not isinstance(events_service, EventsApplicationService):
        return None

    def emit(event_name: str, payload: dict[str, object]) -> None:
        events_service.publish(skill_event_from_payload(event_name, payload))

    return emit


def _build_runtime_services(
    settings: Settings,
    uow_factory: Callable[[], SqlAlchemyUnitOfWork],
    authorization_service: AuthorizationApplicationService,
    tool_infrastructure: _ToolInfrastructure,
    core_services: _CoreServices,
    daemon_service: DaemonApplicationService,
    process_service: ProcessApplicationService,
    daemon_manager: DaemonManager,
    artifact_service: ArtifactApplicationService,
    events_service: EventsApplicationService | None = None,
) -> _RuntimeServices:
    memory_port = core_services.memory_port
    authorization_port = AuthorizationServiceAdapter(authorization_service)
    llm_port = LlmServiceAdapter(core_services.llm_service)
    skill_manager = SkillManager(
        repository=FilesystemSkillRepository(),
        event_emitter=_build_skill_event_emitter(events_service),
    )
    access_service = AccessApplicationService()
    orchestration_scheduler_service_ref: dict[
        str,
        OrchestrationSchedulerService | None,
    ] = {
        "value": None,
    }
    orchestration_cancellation_service_ref: dict[
        str,
        RunCancellationService | None,
    ] = {
        "value": None,
    }
    orchestration_run_query_service = OrchestrationRunQueryService(uow_factory)

    def _session_workspace_lookup(session_key: str) -> str | None:
        normalized_session_key = session_key.strip()
        if not normalized_session_key:
            return None
        try:
            session = core_services.session_service.get_session(normalized_session_key)
        except Exception:
            return None
        workspace = session.runtime_binding().workspace
        if workspace is None:
            return None
        normalized_workspace = workspace.strip()
        return normalized_workspace or None

    register_scanned_tool_packages(
        SimpleNamespace(
            local_tool_catalog=tool_infrastructure.local_tool_catalog,
            file_memory_service=core_services.file_memory_service,
            memory_context_resolver=core_services.memory_context_resolver,
            process_service=process_service,
            session_service=core_services.session_service,
            session_workspace_lookup=_session_workspace_lookup,
            orchestration_run_query_service_lookup=(
                lambda: orchestration_run_query_service
            ),
            orchestration_cancellation_service_lookup=(
                lambda: orchestration_cancellation_service_ref["value"]
            ),
            orchestration_scheduler_service_lookup=(
                lambda: orchestration_scheduler_service_ref["value"]
            ),
            skill_manager=skill_manager,
        ),
        include_openapi=False,
    )

    prompt_assembler = PromptAssembler(
        agent_service=core_services.agent_service,
        llm_port=llm_port,
        memory_port=memory_port,
        skill_catalog_port=skill_manager,
        session_service=core_services.session_service,
        artifact_service=artifact_service,
        access_port=access_service,
        events_service=events_service,
        system_prompt_max_chars=settings.prompt_system_max_chars,
        system_prompt_max_tokens=settings.prompt_system_max_tokens,
        system_prompt_context_window_ratio=(
            settings.prompt_system_context_window_ratio
        ),
        llm_image_max_bytes=settings.artifact_image_llm_max_bytes,
        llm_file_max_bytes=settings.artifact_file_llm_max_bytes,
        llm_text_file_max_chars=settings.artifact_text_file_llm_max_chars,
    )
    tool_service_graph = build_tool_service_graph(
        ToolServiceDependencies(
            uow_factory=uow_factory,
            runtime_gateway=tool_infrastructure.tool_runtime_gateway,
            runtime_registry=tool_infrastructure.remote_tool_registry,
            discovery_gateway=tool_infrastructure.tool_discovery_registry,
            dispatch_port=ToolRunDispatchAdapter(
                dispatch_service=core_services.dispatch_service,
            ),
            artifact_service=artifact_service,
            default_max_attempts=settings.tool_run_max_attempts,
            worker_lease_seconds=settings.tool_run_lease_seconds,
            worker_heartbeat_seconds=settings.tool_run_heartbeat_seconds,
            details_max_chars=settings.tool_details_max_chars,
            worker_default_run_concurrency=settings.tool_worker_default_run_concurrency,
            worker_image_run_concurrency=settings.tool_worker_image_run_concurrency,
            worker_shared_state_run_concurrency=(
                settings.tool_worker_shared_state_run_concurrency
            ),
            metrics=get_runtime_metrics_registry(),
        ),
    )
    tool_service = tool_service_graph.application_service
    tool_port = ToolServiceAdapter(tool_service)

    def _run_context_provider(run):
        workspace_dir: str | None = None
        session_key = str(run.metadata.get("session_key", "")).strip()
        if session_key:
            try:
                session = core_services.session_service.get_session(session_key)
            except Exception:
                session = None
            if session is not None:
                workspace_dir = session.runtime_binding().workspace
        available_scopes: list[str] = []
        if session_key:
            available_scopes.append("session_context")
        if (
            run.agent_id is not None
            and core_services.memory_port.resolve_context(space_id=run.agent_id)
            is not None
        ):
            available_scopes.append("memory_context")
        if workspace_dir is not None and workspace_dir.strip():
            available_scopes.append("workspace_bound")
        attrs = {
            "available_scopes": available_scopes,
        }
        if workspace_dir is not None and workspace_dir.strip():
            attrs["workspace_dir"] = workspace_dir.strip()
        return attrs

    tool_resolver = ToolResolver(
        tool_catalog=tool_port,
        authorization_port=authorization_port,
        access_port=access_service,
        run_context_provider=_run_context_provider,
    )
    orchestration_engine = OrchestrationEngine(
        prompt_assembler=prompt_assembler,
        session_recorder=OrchestrationSessionRecorder(
            session_service=core_services.session_service,
        ),
        llm_port=llm_port,
        tool_resolver=tool_resolver,
        tool_execution_port=tool_port,
        memory_port=memory_port,
        detailed_phase_metrics_enabled=(
            settings.orchestration_detailed_engine_metrics_enabled
        ),
    )
    orchestration_service_graph = OrchestrationServiceGraph(
        uow_factory,
        dispatch_port=OrchestrationRunDispatchAdapter(
            dispatch_service=core_services.dispatch_service,
        ),
        agent_service=core_services.agent_service,
        authorization_port=authorization_port,
        llm_port=llm_port,
        memory_port=memory_port,
        session_service=core_services.session_service,
        session_resolution_service=core_services.session_resolution_service,
        engine=orchestration_engine,
        worker_lease_seconds=settings.orchestration_run_lease_seconds,
        worker_heartbeat_seconds=settings.orchestration_run_heartbeat_seconds,
        auto_compaction_enabled=settings.orchestration_auto_compaction_enabled,
        auto_compaction_reserve_tokens=(
            settings.orchestration_auto_compaction_reserve_tokens
        ),
        auto_compaction_soft_threshold_tokens=(
            settings.orchestration_auto_compaction_soft_threshold_tokens
        ),
        events_service=events_service,
        run_query_service=orchestration_run_query_service,
    )
    orchestration_inspection_service = orchestration_service_graph.inspection_service
    orchestration_approval_control_service = (
        orchestration_service_graph.approval_control_service
    )
    orchestration_cancellation_service = orchestration_service_graph.cancellation_service
    orchestration_cancellation_service_ref["value"] = orchestration_cancellation_service
    orchestration_intake_service = orchestration_service_graph.intake_service
    orchestration_scheduler_service = orchestration_service_graph.scheduler_service
    orchestration_executor_service = orchestration_service_graph.executor_service
    orchestration_scheduler_service_ref["value"] = orchestration_scheduler_service
    return _RuntimeServices(
        tool_service=tool_service,
        tool_scheduler_service=tool_service_graph.scheduler_service,
        tool_worker_service=tool_service_graph.worker_service,
        access_service=access_service,
        orchestration_service_graph=orchestration_service_graph,
        orchestration_run_query_service=orchestration_run_query_service,
        orchestration_inspection_service=orchestration_inspection_service,
        orchestration_approval_control_service=orchestration_approval_control_service,
        orchestration_cancellation_service=orchestration_cancellation_service,
        orchestration_intake_service=orchestration_intake_service,
        orchestration_scheduler_service=orchestration_scheduler_service,
        orchestration_executor_service=orchestration_executor_service,
        skill_manager=skill_manager,
    )


def _build_process_runtime_services(
    settings: Settings,
    *,
    daemon_service: DaemonApplicationService,
) -> tuple[ProcessApplicationService, DaemonManager]:
    process_repository = FilesystemProcessSessionRepository(
        derive_process_store_root(settings.database_url),
    )
    process_service = ProcessApplicationService(
        repository=process_repository,
        supervisor=ProcessSupervisor(process_repository),
    )
    daemon_manager = DaemonManager(
        daemon_service=daemon_service,
        process_service=process_service,
        working_directory=str(PROJECT_ROOT),
        shell_resolver=lambda: "/bin/sh",
    )
    return process_service, daemon_manager


def _build_orchestration_scheduler_runtime_event_service(
    *,
    events_service: EventsApplicationService | None,
    tool_service: ToolApplicationService,
    orchestration_scheduler_service: OrchestrationSchedulerService,
) -> OrchestrationRuntimeEventService | None:
    if not isinstance(events_service, EventsApplicationService):
        return None
    runtime = OrchestrationRuntimeEventService(
        events_service=events_service,
        runtime_name="orchestration.scheduler-runtime",
    )
    wake_observer = DispatchWakeupObserver(events_service=events_service)
    tool_terminal_reaction = OrchestrationToolTerminalReaction(
        scheduler_service=orchestration_scheduler_service,
        tool_run_lookup=tool_service.get_tool_run,
    )
    orchestration_dispatch_recovery_reaction = OrchestrationDispatchRecoveryReaction(
        scheduler_service=orchestration_scheduler_service,
    )
    for event_name in (
        "tool.run.succeeded",
        "tool.run.failed",
        "tool.run.cancelled",
        "tool.run.timed_out",
    ):
        runtime.subscribe_event_name(
            event_name,
            subscription_id=f"orchestration.runtime.tool-terminal.{event_name}",
            handler=tool_terminal_reaction.react_to_terminal_tool_run,
        )
    for event_name, handler in (
        ("dispatch.task.queued", wake_observer.observe_task_queued),
        ("dispatch.task.requeued", wake_observer.observe_task_requeued),
        ("dispatch.task.recovered", wake_observer.observe_task_recovered),
    ):
        runtime.subscribe_event_name(
            event_name,
            subscription_id=f"orchestration.scheduler.dispatch-wakeup.{event_name}",
            handler=handler,
        )
    runtime.subscribe_event_name(
        "dispatch.task.recovered",
        subscription_id="orchestration.runtime.dispatch-recovery",
        handler=orchestration_dispatch_recovery_reaction.react_to_recovered_dispatch_task,
    )
    return runtime


def _build_event_relay_runtime_event_service(
    *,
    events_service: EventsApplicationService | None,
    tool_service: ToolApplicationService,
    orchestration_run_query_service: OrchestrationRunQueryService,
) -> EventRelayRuntimeService | None:
    if not isinstance(events_service, EventsApplicationService):
        return None
    runtime = EventRelayRuntimeService(
        events_service=events_service,
        runtime_name="event_relay.runtime",
    )
    workbench_observer = WorkbenchEventRelayObserver(
        events_service=events_service,
        run_lookup=orchestration_run_query_service,
        tool_execution_port=tool_service,
    )
    turn_session_run_observer = RunObservationObserver(
        events_service=events_service,
        run_lookup=orchestration_run_query_service,
    )
    turn_session_message_observer = SessionMessageObservationObserver(
        events_service=events_service,
    )
    turn_session_tool_observer = ToolRunObservationObserver(
        events_service=events_service,
        run_lookup=orchestration_run_query_service,
        tool_execution_port=tool_service,
    )
    for event_name in RUN_OBSERVATION_EVENT_NAMES:
        runtime.subscribe_event_name(
            event_name,
            subscription_id=f"event_relay.workbench.run.{event_name}",
            handler=workbench_observer.observe_run_event,
        )
        runtime.subscribe_event_name(
            event_name,
            subscription_id=f"event_relay.turn-session.run.{event_name}",
            handler=turn_session_run_observer.observe_run_event,
            replay_existing_on_first_run=True,
        )
    runtime.subscribe_event_name(
        "session.message.appended",
        subscription_id="event_relay.workbench.session-message",
        handler=workbench_observer.observe_session_message_event,
    )
    runtime.subscribe_event_name(
        "session.message.appended",
        subscription_id="event_relay.turn-session.session-message",
        handler=turn_session_message_observer.observe_message_appended,
        replay_existing_on_first_run=True,
    )
    runtime.subscribe_event_name(
        ORCHESTRATION_RUN_LLM_TEXT_DELTA_EVENT,
        subscription_id="event_relay.workbench.llm-text-delta",
        handler=workbench_observer.observe_live_llm_event,
    )
    for event_name in TOOL_OBSERVATION_SOURCE_EVENT_NAMES:
        runtime.subscribe_event_name(
            event_name,
            subscription_id=f"event_relay.workbench.tool.{event_name}",
            handler=workbench_observer.observe_tool_event,
        )
        runtime.subscribe_event_name(
            event_name,
            subscription_id=f"event_relay.turn-session.tool.{event_name}",
            handler=turn_session_tool_observer.observe_tool_event,
            replay_existing_on_first_run=True,
        )
    return runtime


def _build_operations_observer_runtime_event_service(
    *,
    events_service: EventsApplicationService | None,
    observation_store: FileBackedOperationsObservationStore,
    event_definition_registry: EventDefinitionRegistry,
    projection_materializer: Any | None = None,
) -> OperationsObserverRuntimeService | None:
    if not isinstance(events_service, EventsApplicationService):
        return None
    runtime = OperationsObserverRuntimeService(
        events_service=events_service,
        runtime_name="operations.observer",
        heartbeat_handler=observation_store.record_observer_heartbeat,
    )
    observer = OperationsEventObserver(
        observation_store=observation_store,
        definition_registry=event_definition_registry,
    )
    pending_projection_modules: set[str] = set()
    last_projection_at = time.monotonic()
    projection_interval_seconds = 30.0

    def _observe_event_records(records) -> None:  # noqa: ANN001
        nonlocal last_projection_at
        observer.observe_event_records(records)
        if projection_materializer is None:
            return
        pending_projection_modules.update(
            observed_event_from_record(
                record,
                definition_registry=event_definition_registry,
            ).module
            for record in records
        )
        now = time.monotonic()
        if now - last_projection_at < projection_interval_seconds:
            return
        modules = tuple(sorted(pending_projection_modules))
        pending_projection_modules.clear()
        last_projection_at = now
        projection_materializer.materialize_observed_modules(modules)

    for event_name in operations_observer_event_names(event_definition_registry):
        runtime.subscribe_event_name(
            event_name,
            subscription_id=f"operations.observer.{event_name}",
            handler=observer.observe_event_record,
            batch_handler=_observe_event_records,
        )
    return runtime


def _build_tool_runtime_event_service(
    *,
    events_service: EventsApplicationService | None,
    tool_recovery_handler,
) -> ToolRuntimeEventService | None:
    if not isinstance(events_service, EventsApplicationService):
        return None
    return ToolRuntimeEventService(
        events_service=events_service,
        dispatch_subscriber=ToolDispatchEventSubscriber(service=tool_recovery_handler),
    )


def _build_events_backend(settings: Settings):
    if settings.events_backend == "redis":
        return RedisEventsBackend(
            settings.events_redis_url,
            key_prefix=settings.events_redis_key_prefix,
            block_ms=settings.events_redis_block_ms,
            dedupe_ttl_seconds=settings.events_redis_dedupe_ttl_seconds,
        )
    return FileBackedEventsBackend(
        settings.events_state_dir,
        sync_writes=settings.events_file_sync_writes,
    )


def _build_event_contract_registry() -> EventContractRegistry:
    registry = EventContractRegistry()
    registry.register_topics(events_event_topic_contracts())
    registry.register_topics(orchestration_event_topic_contracts())
    registry.register_topics(dispatch_event_topic_contracts())
    registry.register_topics(channel_event_topic_contracts())
    registry.register_routes(channel_event_route_contracts())
    return registry


def _build_event_definition_registry() -> EventDefinitionRegistry:
    registry = EventDefinitionRegistry()
    registry.register_many(events_event_definitions())
    registry.register_surfaces(events_event_surfaces())
    registry.register_many(dispatch_event_definitions())
    registry.register_surfaces(dispatch_event_surfaces())
    registry.register_observers(dispatch_event_observers())
    registry.register_many(channel_event_definitions())
    registry.register_surfaces(channel_event_surfaces())
    registry.register_many(operations_event_definitions())
    registry.register_surfaces(operations_event_surfaces())
    registry.register_many(orchestration_event_definitions())
    registry.register_surfaces(orchestration_event_surfaces())
    registry.register_observers(orchestration_event_observers())
    registry.register_many(memory_event_definitions())
    registry.register_surfaces(memory_event_surfaces())
    registry.register_many(skill_event_definitions())
    registry.register_surfaces(skill_event_surfaces())
    return registry


def build_container(
    *,
    settings: Settings | None = None,
    database_url: str | None = None,
    event_bus: EventBus | None = None,
    enable_memory_watchers: bool = False,
) -> AppContainer:
    resolved_settings = settings or load_settings()
    if database_url is not None:
        resolved_settings = replace(resolved_settings, database_url=database_url)

    engine = build_engine(resolved_settings)
    session_factory = build_session_factory(engine)
    event_contract_registry = _build_event_contract_registry()
    event_definition_registry = _build_event_definition_registry()
    resolved_event_bus = event_bus or EventsBackedEventBus(
        EventsApplicationService(
            _build_events_backend(resolved_settings),
        ),
    )
    resolved_events_service = getattr(resolved_event_bus, "events_service", None)
    container_events_service = (
        resolved_events_service
        if isinstance(resolved_events_service, EventsApplicationService)
        else None
    )
    authorization_service, authorization_policy_count = _build_authorization_service(
        resolved_settings,
        session_factory,
    )
    llm_adapter_registry = _build_llm_adapter_registry()
    browser_system_config = _build_browser_system_config(resolved_settings)
    mobile_system_config = _build_mobile_system_config(resolved_settings)
    artifact_service = ArtifactApplicationService(
        FilesystemArtifactStore(resolved_settings.artifact_store_dir),
        preview_max_dimension=resolved_settings.artifact_image_preview_max_dimension,
        llm_max_dimension=resolved_settings.artifact_image_llm_max_dimension,
        llm_image_max_bytes=resolved_settings.artifact_image_llm_max_bytes,
    )
    ocr_service = OcrApplicationService(
        engine=_build_ocr_engine(resolved_settings),
        artifact_service=artifact_service,
        default_language=resolved_settings.ocr_language,
    )
    daemon_infrastructure = _build_daemon_infrastructure(
        resolved_settings,
        browser_system_config=browser_system_config,
    )
    channels_infrastructure = _build_channels_infrastructure(resolved_settings)
    channel_control_service = ChannelControlService(
        profile_service=channels_infrastructure.profile_service,
        planner=channels_infrastructure.runtime_planner,
        daemon_service=daemon_infrastructure.service,
    )
    process_service, daemon_manager = _build_process_runtime_services(
        resolved_settings,
        daemon_service=daemon_infrastructure.service,
    )
    browser_infrastructure = _build_browser_infrastructure(
        resolved_settings,
        system_config=browser_system_config,
        daemon_service=daemon_infrastructure.service,
    )
    mobile_infrastructure = _build_mobile_infrastructure(
        resolved_settings,
        artifact_service=artifact_service,
        ocr_service=ocr_service,
        system_config=mobile_system_config,
        daemon_service=daemon_infrastructure.service,
        daemon_manager=daemon_manager,
    )
    tool_infrastructure = _build_tool_infrastructure(
        resolved_settings,
        browser_infrastructure=browser_infrastructure,
        mobile_infrastructure=mobile_infrastructure,
    )
    operations_observation_store = FileBackedOperationsObservationStore(
        resolved_settings.operations_state_dir,
    )
    operations_action_audit_store = SqlAlchemyOperationsActionAuditStore(session_factory)
    operations_projection_store = SqlAlchemyOperationsProjectionStore(session_factory)

    logger.info(
        "building app container",
        extra={
            "environment": resolved_settings.environment,
            "database_url": resolved_settings.database_url,
            "event_bus": type(resolved_event_bus).__name__,
            "events_backend": (
                type(resolved_events_service.backend).__name__
                if isinstance(resolved_events_service, EventsApplicationService)
                else None
            ),
            "event_topic_contract_count": len(
                event_contract_registry.list_topic_contracts(),
            ),
            "event_route_contract_count": len(
                event_contract_registry.list_route_contracts(),
            ),
            "channel_profile_count": len(
                channels_infrastructure.system_config.profiles,
            ),
            "local_tool_count": len(
                tool_infrastructure.tool_runtime_gateway.list_local_tools(),
            ),
            "local_tool_path_count": len(resolved_settings.tool_local_paths),
            "tool_discovery_provider_count": len(
                tool_infrastructure.tool_discovery_registry.list_providers(),
            ),
            "mcp_provider_count": len(resolved_settings.tool_mcp_providers),
            "openapi_provider_count": len(resolved_settings.tool_openapi_providers),
            "sandbox_backend": resolved_settings.sandbox_backend,
            "sandbox_runtime_count": tool_infrastructure.sandbox_tool_registry.count(),
            "remote_runtime_count": tool_infrastructure.remote_tool_registry.count(),
            "authorization_enabled": resolved_settings.authorization_enabled,
            "authorization_policy_count": authorization_policy_count,
            "memory_retrieval_backend": resolved_settings.memory_retrieval_backend,
            "memory_vector_provider": resolved_settings.memory_vector_provider,
        },
    )

    def uow_factory() -> SqlAlchemyUnitOfWork:
        return SqlAlchemyUnitOfWork(session_factory, resolved_event_bus)

    core_services = _build_core_services(
        resolved_settings,
        uow_factory,
        llm_adapter_registry,
        tool_infrastructure.local_tool_catalog,
        events_service=container_events_service,
        enable_memory_watchers=enable_memory_watchers,
    )
    runtime_services = _build_runtime_services(
        resolved_settings,
        uow_factory,
        authorization_service,
        tool_infrastructure,
        core_services,
        daemon_infrastructure.service,
        process_service,
        daemon_manager,
        artifact_service,
        container_events_service,
    )
    tool_service = runtime_services.tool_service
    tool_scheduler_service = runtime_services.tool_scheduler_service
    tool_worker_service = runtime_services.tool_worker_service
    access_service = runtime_services.access_service
    orchestration_run_query_service = runtime_services.orchestration_run_query_service
    orchestration_inspection_service = runtime_services.orchestration_inspection_service
    orchestration_approval_control_service = (
        runtime_services.orchestration_approval_control_service
    )
    orchestration_cancellation_service = (
        runtime_services.orchestration_cancellation_service
    )
    orchestration_intake_service = runtime_services.orchestration_intake_service
    orchestration_scheduler_service = runtime_services.orchestration_scheduler_service
    orchestration_executor_service = runtime_services.orchestration_executor_service
    skill_manager = runtime_services.skill_manager
    web_channel_runtime_service = WebChannelRuntimeService(
        profile_service=channels_infrastructure.profile_service,
        runtime_manager=channels_infrastructure.runtime_manager,
        events_service=container_events_service
        or EventsApplicationService(_build_events_backend(resolved_settings)),
        access_service=access_service,
    )
    webhook_channel_runtime_service = WebhookChannelRuntimeService(
        agent_service=core_services.agent_service,
        orchestration_scheduler_service=orchestration_scheduler_service,
        orchestration_run_lookup=orchestration_run_query_service,
        interaction_service=channels_infrastructure.interaction_service,
        profile_service=channels_infrastructure.profile_service,
        runtime_manager=channels_infrastructure.runtime_manager,
        events_service=container_events_service
        or EventsApplicationService(_build_events_backend(resolved_settings)),
        access_service=access_service,
    )
    lark_channel_runtime_service = LarkChannelRuntimeService(
        agent_service=core_services.agent_service,
        orchestration_scheduler_service=orchestration_scheduler_service,
        orchestration_run_lookup=orchestration_run_query_service,
        artifact_service=artifact_service,
        interaction_service=channels_infrastructure.interaction_service,
        profile_service=channels_infrastructure.profile_service,
        runtime_manager=channels_infrastructure.runtime_manager,
        events_service=container_events_service
        or EventsApplicationService(_build_events_backend(resolved_settings)),
        access_service=access_service,
    )

    def _bind_channel_interactions_to_run(run) -> None:
        session_key = (
            run.session_key.strip()
            if isinstance(run.session_key, str) and run.session_key.strip()
            else None
        )
        metadata: dict[str, object] = {
            "active_session_id": run.active_session_id,
        }
        if (
            session_key is not None
            and container_events_service is not None
        ):
            metadata["observe_cursor"] = container_events_service.snapshot_event_topic(
                turn_session_topic(session_key),
            )
        channels_infrastructure.interaction_service.bind_run_by_run_id(
            run.id,
            session_key=session_key,
            agent_id=run.agent_id,
            status=run.status.value,
            metadata=metadata,
        )

    orchestration_scheduler_service.on_run_enqueued = (
        _bind_channel_interactions_to_run
    )
    orchestration_scheduler_runtime_event_service = (
        _build_orchestration_scheduler_runtime_event_service(
            events_service=container_events_service,
            tool_service=tool_service,
            orchestration_scheduler_service=orchestration_scheduler_service,
        )
    )
    event_relay_runtime_event_service = _build_event_relay_runtime_event_service(
        events_service=container_events_service,
        tool_service=tool_service,
        orchestration_run_query_service=orchestration_run_query_service,
    )
    operations_projection_context = SimpleNamespace(
        settings=resolved_settings,
        events_service=container_events_service,
        event_contract_registry=event_contract_registry,
        event_definition_registry=event_definition_registry,
        operations_observation_store=operations_observation_store,
        operations_action_audit_store=operations_action_audit_store,
        operations_projection_store=operations_projection_store,
        operations_observer_runtime_event_service=None,
        orchestration_run_query_service=orchestration_run_query_service,
        orchestration_executor_service=orchestration_executor_service,
        tool_service=tool_service,
        access_service=access_service,
        artifact_service=artifact_service,
        remote_tool_registry=tool_infrastructure.remote_tool_registry,
        llm_service=core_services.llm_service,
        agent_service=core_services.agent_service,
        file_memory_service=core_services.file_memory_service,
        memory_context_resolver=core_services.memory_context_resolver,
        memory_watch_registry=core_services.memory_watch_registry,
        skill_manager=skill_manager,
        channel_profile_service=channels_infrastructure.profile_service,
        channel_runtime_manager=channels_infrastructure.runtime_manager,
        channel_interaction_service=channels_infrastructure.interaction_service,
        lark_channel_runtime_service=lark_channel_runtime_service,
        web_channel_runtime_service=web_channel_runtime_service,
        webhook_channel_runtime_service=webhook_channel_runtime_service,
        daemon_service=daemon_infrastructure.service,
        daemon_manager=daemon_manager,
        process_service=process_service,
    )
    from crxzipple.modules.operations.application.projections import (
        OperationsProjectionMaterializer,
    )
    from crxzipple.modules.operations.application.read_models.factory import (
        build_operations_source_read_model_provider,
    )

    operations_projection_materializer = OperationsProjectionMaterializer(
        source_provider=build_operations_source_read_model_provider(
            operations_projection_context,
        ),
        projection_store=operations_projection_store,
        events_service=container_events_service,
    )
    operations_observer_runtime_event_service = (
        _build_operations_observer_runtime_event_service(
            events_service=container_events_service,
            observation_store=operations_observation_store,
            event_definition_registry=event_definition_registry,
            projection_materializer=operations_projection_materializer,
        )
    )
    operations_projection_context.operations_observer_runtime_event_service = (
        operations_observer_runtime_event_service
    )
    tool_runtime_event_service = _build_tool_runtime_event_service(
        events_service=container_events_service,
        tool_recovery_handler=tool_worker_service,
    )
    orchestration_scheduler_service.runtime_event_service = (
        orchestration_scheduler_runtime_event_service
    )

    return AppContainer(
        settings=resolved_settings,
        engine=engine,
        session_factory=session_factory,
        event_bus=resolved_event_bus,
        events_service=container_events_service,
        event_contract_registry=event_contract_registry,
        event_definition_registry=event_definition_registry,
        channel_system_config=channels_infrastructure.system_config,
        channel_system_config_store=channels_infrastructure.system_config_store,
        channel_interaction_registry_store=channels_infrastructure.interaction_registry_store,
        channel_runtime_registry_store=channels_infrastructure.runtime_registry_store,
        channel_state_root=channels_infrastructure.state_root,
        channel_interaction_service=channels_infrastructure.interaction_service,
        channel_profile_service=channels_infrastructure.profile_service,
        channel_control_service=channel_control_service,
        channel_runtime_planner=channels_infrastructure.runtime_planner,
        channel_runtime_manager=channels_infrastructure.runtime_manager,
        lark_channel_runtime_service=lark_channel_runtime_service,
        web_channel_runtime_service=web_channel_runtime_service,
        webhook_channel_runtime_service=webhook_channel_runtime_service,
        local_tool_catalog=tool_infrastructure.local_tool_catalog,
        tool_discovery_registry=tool_infrastructure.tool_discovery_registry,
        sandbox_tool_registry=tool_infrastructure.sandbox_tool_registry,
        remote_tool_registry=tool_infrastructure.remote_tool_registry,
        llm_adapter_registry=llm_adapter_registry,
        access_service=access_service,
        authorization_service=authorization_service,
        uow_factory=uow_factory,
        browser_system_config=browser_infrastructure.system_config,
        browser_system_config_store=browser_infrastructure.system_config_store,
        browser_state_root=browser_infrastructure.state_root,
        browser_facade=browser_infrastructure.facade,
        browser_result_serializer=browser_infrastructure.result_serializer,
        browser_runtime_state_store=browser_infrastructure.runtime_state_store,
        browser_cdp_control=browser_infrastructure.cdp_control,
        browser_profile_admin_service=browser_infrastructure.profile_admin_service,
        browser_profile_probe_service=browser_infrastructure.profile_probe_service,
        browser_profile_resolver=browser_infrastructure.profile_resolver,
        browser_capabilities_resolver=browser_infrastructure.capabilities_resolver,
        mobile_system_config=mobile_infrastructure.system_config,
        mobile_system_config_store=mobile_infrastructure.system_config_store,
        mobile_state_root=mobile_infrastructure.state_root,
        mobile_facade=mobile_infrastructure.facade,
        mobile_result_serializer=mobile_infrastructure.result_serializer,
        mobile_runtime_state_store=mobile_infrastructure.runtime_state_store,
        ocr_service=ocr_service,
        ocr_result_serializer=OcrResultSerializer(),
        daemon_state_root=daemon_infrastructure.state_root,
        daemon_service=daemon_infrastructure.service,
        daemon_manager=daemon_manager,
        daemon_spec_syncers=(channel_control_service.sync_daemon_specs,),
        dispatch_service=core_services.dispatch_service,
        event_relay_runtime_event_service=event_relay_runtime_event_service,
        operations_observation_store=operations_observation_store,
        operations_action_audit_store=operations_action_audit_store,
        operations_projection_store=operations_projection_store,
        operations_projection_materializer=operations_projection_materializer,
        operations_observer_runtime_event_service=(
            operations_observer_runtime_event_service
        ),
        tool_runtime_event_service=tool_runtime_event_service,
        orchestration_run_query_service=orchestration_run_query_service,
        orchestration_inspection_service=orchestration_inspection_service,
        orchestration_approval_control_service=orchestration_approval_control_service,
        orchestration_cancellation_service=orchestration_cancellation_service,
        orchestration_intake_service=orchestration_intake_service,
        orchestration_scheduler_service=orchestration_scheduler_service,
        orchestration_scheduler_runtime_event_service=(
            orchestration_scheduler_runtime_event_service
        ),
        orchestration_executor_service=orchestration_executor_service,
        tool_service=tool_service,
        tool_scheduler_service=tool_scheduler_service,
        tool_worker_service=tool_worker_service,
        process_service=process_service,
        session_service=core_services.session_service,
        session_resolution_service=core_services.session_resolution_service,
        llm_service=core_services.llm_service,
        file_memory_service=core_services.file_memory_service,
        memory_context_resolver=core_services.memory_context_resolver,
        memory_watch_registry=core_services.memory_watch_registry,
        agent_service=core_services.agent_service,
        skill_manager=skill_manager,
        artifact_service=artifact_service,
        cleanup_callbacks=browser_infrastructure.cleanup_callbacks
        + tool_infrastructure.cleanup_callbacks
        + (process_service.close,)
        + (close_async_http_clients_sync,)
        + ((core_services.memory_watch_registry.close,) if core_services.memory_watch_registry is not None else ()),
    )
