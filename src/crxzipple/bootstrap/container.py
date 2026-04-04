from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field, replace
import os
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import Engine

from crxzipple.core.config import (
    DEFAULT_BROWSER_DEFAULT_PROFILE_NAME,
    Settings,
    load_settings,
)
from crxzipple.core.db import SessionFactory, build_engine, build_session_factory
from crxzipple.core.logger import get_logger
from crxzipple.modules.browser.application import (
    BrowserExecutionCoordinatorService,
    BrowserProfileAdminService,
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
from crxzipple.modules.authorization.application import AuthorizationApplicationService
from crxzipple.modules.dispatch.application import DispatchApplicationService
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
from crxzipple.modules.memory.infrastructure.indexing import (
    FileMemoryIndexManager,
    LocalHashedMemoryEmbeddingProvider,
    OpenAICompatibleMemoryEmbeddingProvider,
)
from crxzipple.modules.memory.infrastructure.watching import MemoryWatchRegistry
from crxzipple.modules.orchestration.application import (
    OrchestrationDispatchEventSubscriber,
    OrchestrationApplicationService,
    OrchestrationEngine,
    OrchestrationSessionRecorder,
    OrchestrationToolEventSubscriber,
    OrchestrationRouter,
    PromptAssembler,
    SessionResolver,
    ToolResolver,
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
from crxzipple.modules.session.application import SessionApplicationService
from crxzipple.modules.skills.application import SkillManager
from crxzipple.modules.skills.infrastructure import FilesystemSkillRepository
from crxzipple.modules.tool.application import ToolApplicationService
from crxzipple.modules.tool.application import ToolDispatchEventSubscriber
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
from crxzipple.shared.infrastructure import InMemoryEventBus, SqlAlchemyUnitOfWork
from crxzipple.shared.infrastructure.event_bus import EventBus

logger = get_logger(__name__)


@dataclass(slots=True)
class AppContainer:
    settings: Settings
    engine: Engine
    session_factory: SessionFactory
    event_bus: EventBus
    local_tool_catalog: LocalToolCatalog
    tool_discovery_registry: ToolDiscoveryRegistry
    sandbox_tool_registry: ToolRuntimeRegistry
    remote_tool_registry: ToolRuntimeRegistry
    llm_adapter_registry: LlmAdapterRegistry
    authorization_service: AuthorizationApplicationService
    uow_factory: Callable[[], SqlAlchemyUnitOfWork]
    browser_system_config: BrowserSystemConfig
    browser_system_config_store: FileBackedBrowserSystemConfigStore
    browser_state_root: BrowserStateRoot
    browser_facade: BrowserInterfaceFacade
    browser_result_serializer: BrowserResultSerializer
    browser_runtime_state_store: FileBackedBrowserRuntimeStateStore
    browser_profile_admin_service: BrowserProfileAdminService
    browser_profile_probe_service: BrowserProfileProbeService
    browser_profile_resolver: DefaultBrowserProfileResolver
    browser_capabilities_resolver: DefaultBrowserCapabilitiesResolver
    dispatch_service: DispatchApplicationService
    orchestration_service: OrchestrationApplicationService
    tool_service: ToolApplicationService
    process_service: ProcessApplicationService
    session_service: SessionApplicationService
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
class _BrowserInfrastructure:
    system_config: BrowserSystemConfig
    system_config_store: FileBackedBrowserSystemConfigStore
    state_root: BrowserStateRoot
    runtime_state_store: BrowserRuntimeStateStore
    ref_store: FileBackedBrowserRefStore
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
    llm_service: LlmApplicationService
    agent_service: AgentApplicationService
    file_memory_service: FileBackedMemoryService
    memory_context_resolver: FileMemoryContextResolver
    memory_watch_registry: MemoryWatchRegistry | None
    memory_port: FileBackedMemoryPortAdapter
    dispatch_service: DispatchApplicationService


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


def _build_browser_infrastructure(settings: Settings) -> _BrowserInfrastructure:
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
    system_config = BrowserSystemConfig(
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
    mcp_pool = ChromeMcpClientPool()
    cdp_control = CdpControlEngine(
        profiles_root=state_root.profiles_dir,
    )
    profile_admin_service = BrowserProfileAdminService(
        system_config_store=system_config_store,
        runtime_state_store=runtime_state_store,
        ref_store=ref_store,
    )
    profile_probe_service = BrowserProfileProbeService(
        cdp_control=cdp_control,
        mcp_pool=mcp_pool,
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
            cdp_backed_playwright=CdpBackedPlaywrightActionEngine(
                session_pool=session_pool,
                ref_store=ref_store,
            ),
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


def _build_tool_infrastructure(
    settings: Settings,
    *,
    browser_infrastructure: _BrowserInfrastructure,
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
        )
        cleanup_callbacks.append(mcp_client.close)

    for provider_settings in settings.tool_openapi_providers:
        openapi_provider = OpenApiDiscoveryProvider(provider_settings)
        tool_discovery_registry.register(openapi_provider)
        register_openapi_remote_handlers(
            remote_tool_registry,
            openapi_provider.operations(),
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
    file_memory_service = FileBackedMemoryService(
        index_manager=FileMemoryIndexManager(
            embedding_provider=_build_memory_embedding_provider(settings),
        ),
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
    )
    memory_port = FileBackedMemoryPortAdapter(
        service=file_memory_service,
        context_resolver=file_memory_context_resolver,
    )
    return _CoreServices(
        session_service=session_service,
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


def _build_runtime_services(
    settings: Settings,
    uow_factory: Callable[[], SqlAlchemyUnitOfWork],
    authorization_service: AuthorizationApplicationService,
    tool_infrastructure: _ToolInfrastructure,
    core_services: _CoreServices,
    artifact_service: ArtifactApplicationService,
) -> tuple[
    ToolApplicationService,
    OrchestrationApplicationService,
    SkillManager,
    ProcessApplicationService,
]:
    memory_port = core_services.memory_port
    authorization_port = AuthorizationServiceAdapter(authorization_service)
    llm_port = LlmServiceAdapter(core_services.llm_service)
    skill_manager = SkillManager(repository=FilesystemSkillRepository())
    process_repository = FilesystemProcessSessionRepository(
        derive_process_store_root(settings.database_url),
    )
    process_service = ProcessApplicationService(
        repository=process_repository,
        supervisor=ProcessSupervisor(process_repository),
    )

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
            session_workspace_lookup=_session_workspace_lookup,
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
        system_prompt_max_chars=settings.prompt_system_max_chars,
        system_prompt_max_tokens=settings.prompt_system_max_tokens,
        system_prompt_context_window_ratio=(
            settings.prompt_system_context_window_ratio
        ),
        llm_image_max_bytes=settings.artifact_image_llm_max_bytes,
        llm_file_max_bytes=settings.artifact_file_llm_max_bytes,
        llm_text_file_max_chars=settings.artifact_text_file_llm_max_chars,
    )
    tool_service = ToolApplicationService(
        uow_factory,
        tool_infrastructure.tool_runtime_gateway,
        tool_infrastructure.tool_discovery_registry,
        dispatch_port=ToolRunDispatchAdapter(
            dispatch_service=core_services.dispatch_service,
        ),
        artifact_service=artifact_service,
        default_max_attempts=settings.tool_run_max_attempts,
        worker_lease_seconds=settings.tool_run_lease_seconds,
        worker_heartbeat_seconds=settings.tool_run_heartbeat_seconds,
        details_max_chars=settings.tool_details_max_chars,
    )
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
    )
    orchestration_router = OrchestrationRouter()
    session_resolver = SessionResolver(
        session_service=core_services.session_service,
        router=orchestration_router,
    )
    orchestration_service = OrchestrationApplicationService(
        uow_factory,
        dispatch_port=OrchestrationRunDispatchAdapter(
            dispatch_service=core_services.dispatch_service,
        ),
        agent_service=core_services.agent_service,
        authorization_port=authorization_port,
        llm_port=llm_port,
        memory_port=memory_port,
        session_service=core_services.session_service,
        router=orchestration_router,
        session_resolver=session_resolver,
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
    )
    return (
        tool_service,
        orchestration_service,
        skill_manager,
        process_service,
    )


def _subscribe_runtime_events(
    event_bus: EventBus,
    *,
    tool_service: ToolApplicationService,
    orchestration_service: OrchestrationApplicationService,
) -> None:
    tool_event_subscriber = OrchestrationToolEventSubscriber(
        service=orchestration_service,
    )
    orchestration_dispatch_subscriber = OrchestrationDispatchEventSubscriber(
        service=orchestration_service,
    )
    tool_dispatch_subscriber = ToolDispatchEventSubscriber(service=tool_service)
    for event_name in (
        "tool.run.succeeded",
        "tool.run.failed",
        "tool.run.cancelled",
        "tool.run.timed_out",
    ):
        event_bus.subscribe(
            event_name,
            tool_event_subscriber.handle_terminal_tool_run,
        )
    event_bus.subscribe(
        "dispatch.task.recovered",
        orchestration_dispatch_subscriber.handle_recovered_dispatch_task,
    )
    event_bus.subscribe(
        "dispatch.task.recovered",
        tool_dispatch_subscriber.handle_recovered_dispatch_task,
    )


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
    resolved_event_bus = event_bus or InMemoryEventBus()
    authorization_service, authorization_policy_count = _build_authorization_service(
        resolved_settings,
        session_factory,
    )
    llm_adapter_registry = _build_llm_adapter_registry()
    browser_infrastructure = _build_browser_infrastructure(resolved_settings)
    artifact_service = ArtifactApplicationService(
        FilesystemArtifactStore(resolved_settings.artifact_store_dir),
        preview_max_dimension=resolved_settings.artifact_image_preview_max_dimension,
        llm_max_dimension=resolved_settings.artifact_image_llm_max_dimension,
        llm_image_max_bytes=resolved_settings.artifact_image_llm_max_bytes,
    )
    tool_infrastructure = _build_tool_infrastructure(
        resolved_settings,
        browser_infrastructure=browser_infrastructure,
    )

    logger.info(
        "building app container",
        extra={
            "environment": resolved_settings.environment,
            "database_url": resolved_settings.database_url,
            "event_bus": type(resolved_event_bus).__name__,
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
        enable_memory_watchers=enable_memory_watchers,
    )
    (
        tool_service,
        orchestration_service,
        skill_manager,
        process_service,
    ) = _build_runtime_services(
        resolved_settings,
        uow_factory,
        authorization_service,
        tool_infrastructure,
        core_services,
        artifact_service,
    )
    _subscribe_runtime_events(
        resolved_event_bus,
        tool_service=tool_service,
        orchestration_service=orchestration_service,
    )

    return AppContainer(
        settings=resolved_settings,
        engine=engine,
        session_factory=session_factory,
        event_bus=resolved_event_bus,
        local_tool_catalog=tool_infrastructure.local_tool_catalog,
        tool_discovery_registry=tool_infrastructure.tool_discovery_registry,
        sandbox_tool_registry=tool_infrastructure.sandbox_tool_registry,
        remote_tool_registry=tool_infrastructure.remote_tool_registry,
        llm_adapter_registry=llm_adapter_registry,
        authorization_service=authorization_service,
        uow_factory=uow_factory,
        browser_system_config=browser_infrastructure.system_config,
        browser_system_config_store=browser_infrastructure.system_config_store,
        browser_state_root=browser_infrastructure.state_root,
        browser_facade=browser_infrastructure.facade,
        browser_result_serializer=browser_infrastructure.result_serializer,
        browser_runtime_state_store=browser_infrastructure.runtime_state_store,
        browser_profile_admin_service=browser_infrastructure.profile_admin_service,
        browser_profile_probe_service=browser_infrastructure.profile_probe_service,
        browser_profile_resolver=browser_infrastructure.profile_resolver,
        browser_capabilities_resolver=browser_infrastructure.capabilities_resolver,
        dispatch_service=core_services.dispatch_service,
        orchestration_service=orchestration_service,
        tool_service=tool_service,
        process_service=process_service,
        session_service=core_services.session_service,
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
        + ((core_services.memory_watch_registry.close,) if core_services.memory_watch_registry is not None else ()),
    )
