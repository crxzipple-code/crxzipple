from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field, replace
from pathlib import Path

from sqlalchemy import Engine

from crxzipple.core.config import Settings, load_settings
from crxzipple.core.db import SessionFactory, build_engine, build_session_factory
from crxzipple.core.logger import get_logger
from crxzipple.modules.agent.application import AgentApplicationService
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
from crxzipple.modules.memory.application import (
    ListMemoryEntriesInput,
    MemoryApplicationService,
)
from crxzipple.modules.memory.infrastructure import register_builtin_memory_tools
from crxzipple.modules.memory.infrastructure import is_memory_tool_name
from crxzipple.modules.orchestration.application import (
    OrchestrationDispatchEventSubscriber,
    OrchestrationDispatchBridge,
    OrchestrationApplicationService,
    OrchestrationEngine,
    OrchestrationToolEventSubscriber,
    OrchestrationRouter,
    PromptAssembler,
    SessionResolver,
    ToolResolver,
)
from crxzipple.modules.orchestration.infrastructure.adapters import (
    AuthorizationServiceAdapter,
    LlmServiceAdapter,
    MemoryServiceAdapter,
    OrchestrationRunDispatchAdapter,
    ToolServiceAdapter,
)
from crxzipple.modules.session.application import SessionApplicationService
from crxzipple.modules.tool.application import ToolApplicationService
from crxzipple.modules.tool.application import ToolDispatchBridge
from crxzipple.modules.tool.application import ToolDispatchEventSubscriber
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
    register_mcp_remote_handlers,
    register_openapi_remote_handlers,
    register_builtin_remote_handlers,
    register_builtin_sandbox_handlers,
    register_builtin_local_tools,
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
    dispatch_service: DispatchApplicationService
    orchestration_service: OrchestrationApplicationService
    tool_service: ToolApplicationService
    session_service: SessionApplicationService
    llm_service: LlmApplicationService
    memory_service: MemoryApplicationService
    agent_service: AgentApplicationService
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


def build_container(
    *,
    settings: Settings | None = None,
    database_url: str | None = None,
    event_bus: EventBus | None = None,
) -> AppContainer:
    resolved_settings = settings or load_settings()
    if database_url is not None:
        resolved_settings = replace(resolved_settings, database_url=database_url)

    engine = build_engine(resolved_settings)
    session_factory = build_session_factory(engine)
    resolved_event_bus = event_bus or InMemoryEventBus()
    local_tool_catalog = LocalToolCatalog()
    tool_discovery_registry = ToolDiscoveryRegistry()
    sandbox_tool_registry = ToolRuntimeRegistry()
    remote_tool_registry = ToolRuntimeRegistry()
    llm_adapter_registry = LlmAdapterRegistry()
    authorization_policy_paths = tuple(
        dict.fromkeys(
            (
                *resolved_settings.authorization_policy_paths,
                resolved_settings.authorization_runtime_policy_path,
            ),
        ),
    )
    authorization_policies = YamlAuthorizationPolicyLoader().load_paths(
        authorization_policy_paths,
    )
    authorization_service = AuthorizationApplicationService(
        policy_repository=InMemoryAuthorizationPolicyRepository(
            policies=list(authorization_policies),
            managed_path=Path(
                resolved_settings.authorization_runtime_policy_path,
            ).expanduser(),
        ),
        evaluator=AbacAuthorizationEvaluator(),
        temporary_grant_repository_factory=(
            lambda: SqlAlchemyTemporaryAuthorizationGrantRepository(session_factory)
        ),
        enabled=resolved_settings.authorization_enabled,
    )
    llm_adapter_registry.register(
        LlmApiFamily.OPENAI_RESPONSES,
        OpenAIResponsesAdapter(),
    )
    llm_adapter_registry.register(
        LlmApiFamily.OPENAI_CODEX_RESPONSES,
        OpenAICodexResponsesAdapter(),
    )
    llm_adapter_registry.register(
        LlmApiFamily.OPENAI_CHAT_COMPATIBLE,
        OpenAIChatCompatibleAdapter(),
    )
    llm_adapter_registry.register(
        LlmApiFamily.ANTHROPIC_MESSAGES,
        AnthropicMessagesAdapter(),
    )
    llm_adapter_registry.register(
        LlmApiFamily.GEMINI_GENERATE_CONTENT,
        GeminiGenerateContentAdapter(),
    )
    register_builtin_local_tools(local_tool_catalog)
    tool_discovery_registry.register(LocalCatalogDiscoveryProvider(local_tool_catalog))
    if resolved_settings.tool_local_paths:
        filesystem_provider = FilesystemLocalToolDiscoveryProvider(
            local_tool_catalog,
            resolved_settings.tool_local_paths,
        )
        tool_discovery_registry.register(filesystem_provider)
        filesystem_provider.discover_specs()
    register_builtin_sandbox_handlers(sandbox_tool_registry)
    register_builtin_remote_handlers(remote_tool_registry)
    cleanup_callbacks: list[Callable[[], None]] = []
    for provider_settings in resolved_settings.tool_mcp_providers:
        mcp_client = McpStdioClient(provider_settings)
        mcp_provider = McpDiscoveryProvider(provider_settings, client=mcp_client)
        tool_discovery_registry.register(mcp_provider)
        register_mcp_remote_handlers(
            remote_tool_registry,
            mcp_provider.definitions(),
            client=mcp_client,
        )
        cleanup_callbacks.append(mcp_client.close)
    for provider_settings in resolved_settings.tool_openapi_providers:
        openapi_provider = OpenApiDiscoveryProvider(provider_settings)
        tool_discovery_registry.register(openapi_provider)
        register_openapi_remote_handlers(
            remote_tool_registry,
            openapi_provider.operations(),
        )
    sandbox_backend = build_sandbox_backend(resolved_settings)
    tool_runtime_gateway = ToolRuntimeRouter(
        LocalAsyncToolExecutor(local_tool_catalog),
        SandboxAsyncToolExecutor(sandbox_tool_registry, sandbox_backend),
        RemoteAsyncToolExecutor(remote_tool_registry),
    )

    logger.info(
        "building app container",
        extra={
            "environment": resolved_settings.environment,
            "database_url": resolved_settings.database_url,
            "event_bus": type(resolved_event_bus).__name__,
            "local_tool_count": len(tool_runtime_gateway.list_local_tools()),
            "local_tool_path_count": len(resolved_settings.tool_local_paths),
            "tool_discovery_provider_count": len(
                tool_discovery_registry.list_providers(),
            ),
            "mcp_provider_count": len(resolved_settings.tool_mcp_providers),
            "openapi_provider_count": len(resolved_settings.tool_openapi_providers),
            "sandbox_backend": resolved_settings.sandbox_backend,
            "sandbox_runtime_count": sandbox_tool_registry.count(),
            "remote_runtime_count": remote_tool_registry.count(),
            "authorization_enabled": resolved_settings.authorization_enabled,
            "authorization_policy_count": len(authorization_policies),
        },
    )

    def uow_factory() -> SqlAlchemyUnitOfWork:
        return SqlAlchemyUnitOfWork(session_factory, resolved_event_bus)

    session_service = SessionApplicationService(uow_factory)
    llm_service = LlmApplicationService(uow_factory, llm_adapter_registry)
    agent_home_root = str(derive_agent_home_root(resolved_settings.database_url))
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
        home_file_reader=read_agent_home_files,
        home_file_writer=write_agent_home_files,
    )
    memory_service = MemoryApplicationService(
        uow_factory,
        workspace_resolver=lambda agent_id: (
            agent_service.get_profile(agent_id).runtime_preferences.resolved_home_dir
        ),
    )
    register_builtin_memory_tools(local_tool_catalog, memory_service)
    dispatch_service = DispatchApplicationService(uow_factory)
    orchestration_router = OrchestrationRouter()
    session_resolver = SessionResolver(
        session_service=session_service,
        router=orchestration_router,
    )
    memory_port = MemoryServiceAdapter(memory_service)
    authorization_port = AuthorizationServiceAdapter(authorization_service)
    llm_port = LlmServiceAdapter(llm_service)
    prompt_assembler = PromptAssembler(
        agent_service=agent_service,
        llm_port=llm_port,
        memory_port=memory_port,
        session_service=session_service,
        system_prompt_max_chars=resolved_settings.prompt_system_max_chars,
        system_prompt_max_tokens=resolved_settings.prompt_system_max_tokens,
        system_prompt_context_window_ratio=(
            resolved_settings.prompt_system_context_window_ratio
        ),
    )
    tool_port = ToolServiceAdapter(
        ToolApplicationService(
            uow_factory,
            tool_runtime_gateway,
            tool_discovery_registry,
            ToolDispatchBridge(),
            dispatch_service,
            default_max_attempts=resolved_settings.tool_run_max_attempts,
            worker_lease_seconds=resolved_settings.tool_run_lease_seconds,
            worker_heartbeat_seconds=resolved_settings.tool_run_heartbeat_seconds,
        ),
    )
    tool_resolver = ToolResolver(
        tool_catalog=tool_port,
        authorization_port=authorization_port,
        tool_availability_filter=lambda run, tool: (
            not is_memory_tool_name(tool.id)
            or (
                run.agent_id is not None
                and bool(
                    memory_service.list_entries(
                        ListMemoryEntriesInput(
                            agent_id=run.agent_id,
                            limit=1,
                        ),
                    ),
                )
            )
        ),
    )
    tool_service = tool_port.service
    orchestration_engine = OrchestrationEngine(
        prompt_assembler=prompt_assembler,
        session_service=session_service,
        llm_port=llm_port,
        tool_resolver=tool_resolver,
        tool_execution_port=tool_port,
        memory_port=memory_port,
    )
    orchestration_dispatch_port = OrchestrationRunDispatchAdapter(
        bridge=OrchestrationDispatchBridge(),
        dispatch_service=dispatch_service,
    )
    orchestration_service = OrchestrationApplicationService(
        uow_factory,
        dispatch_port=orchestration_dispatch_port,
        agent_service=agent_service,
        authorization_port=authorization_port,
        llm_port=llm_port,
        memory_port=memory_port,
        session_service=session_service,
        router=orchestration_router,
        session_resolver=session_resolver,
        engine=orchestration_engine,
        worker_lease_seconds=resolved_settings.orchestration_run_lease_seconds,
        worker_heartbeat_seconds=resolved_settings.orchestration_run_heartbeat_seconds,
        auto_compaction_enabled=resolved_settings.orchestration_auto_compaction_enabled,
        auto_compaction_transcript_chars=(
            resolved_settings.orchestration_auto_compaction_transcript_chars
        ),
        auto_compaction_transcript_tokens=(
            resolved_settings.orchestration_auto_compaction_transcript_tokens
        ),
        auto_compaction_reserve_tokens=(
            resolved_settings.orchestration_auto_compaction_reserve_tokens
        ),
        auto_compaction_soft_threshold_tokens=(
            resolved_settings.orchestration_auto_compaction_soft_threshold_tokens
        ),
    )
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
        resolved_event_bus.subscribe(
            event_name,
            tool_event_subscriber.handle_terminal_tool_run,
        )
    resolved_event_bus.subscribe(
        "dispatch.task.recovered",
        orchestration_dispatch_subscriber.handle_recovered_dispatch_task,
    )
    resolved_event_bus.subscribe(
        "dispatch.task.recovered",
        tool_dispatch_subscriber.handle_recovered_dispatch_task,
    )

    return AppContainer(
        settings=resolved_settings,
        engine=engine,
        session_factory=session_factory,
        event_bus=resolved_event_bus,
        local_tool_catalog=local_tool_catalog,
        tool_discovery_registry=tool_discovery_registry,
        sandbox_tool_registry=sandbox_tool_registry,
        remote_tool_registry=remote_tool_registry,
        llm_adapter_registry=llm_adapter_registry,
        authorization_service=authorization_service,
        uow_factory=uow_factory,
        dispatch_service=dispatch_service,
        orchestration_service=orchestration_service,
        tool_service=tool_service,
        session_service=session_service,
        llm_service=llm_service,
        memory_service=memory_service,
        agent_service=agent_service,
        cleanup_callbacks=tuple(cleanup_callbacks),
    )
