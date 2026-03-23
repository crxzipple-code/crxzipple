from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field, replace

from sqlalchemy import Engine

from crxzipple.core.config import Settings, load_settings
from crxzipple.core.db import SessionFactory, build_engine, build_session_factory
from crxzipple.core.logger import get_logger
from crxzipple.modules.agent.application import AgentApplicationService
from crxzipple.modules.authorization.application import AuthorizationApplicationService
from crxzipple.modules.dispatch.application import DispatchApplicationService
from crxzipple.modules.authorization.infrastructure import (
    AbacAuthorizationEvaluator,
    InMemoryAuthorizationPolicyRepository,
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
    authorization_policies = YamlAuthorizationPolicyLoader().load_paths(
        resolved_settings.authorization_policy_paths,
    )
    authorization_service = AuthorizationApplicationService(
        policy_repository=InMemoryAuthorizationPolicyRepository(
            policies=list(authorization_policies),
        ),
        evaluator=AbacAuthorizationEvaluator(),
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
    agent_service = AgentApplicationService(uow_factory)
    dispatch_service = DispatchApplicationService(uow_factory)
    orchestration_router = OrchestrationRouter()
    session_resolver = SessionResolver(
        session_service=session_service,
        router=orchestration_router,
    )
    prompt_assembler = PromptAssembler(
        agent_service=agent_service,
        session_service=session_service,
    )
    tool_resolver = ToolResolver(
        tool_service=ToolApplicationService(
            uow_factory,
            tool_runtime_gateway,
            tool_discovery_registry,
            ToolDispatchBridge(),
            dispatch_service,
            default_max_attempts=resolved_settings.tool_run_max_attempts,
            worker_lease_seconds=resolved_settings.tool_run_lease_seconds,
            worker_heartbeat_seconds=resolved_settings.tool_run_heartbeat_seconds,
        ),
        authorization_service=authorization_service,
    )
    tool_service = tool_resolver.tool_service
    orchestration_engine = OrchestrationEngine(
        prompt_assembler=prompt_assembler,
        session_service=session_service,
        llm_service=llm_service,
        tool_resolver=tool_resolver,
        tool_service=tool_service,
    )
    orchestration_dispatch_bridge = OrchestrationDispatchBridge()
    orchestration_service = OrchestrationApplicationService(
        uow_factory,
        dispatch_bridge=orchestration_dispatch_bridge,
        dispatch_service=dispatch_service,
        router=orchestration_router,
        session_resolver=session_resolver,
        engine=orchestration_engine,
        worker_lease_seconds=resolved_settings.orchestration_run_lease_seconds,
        worker_heartbeat_seconds=resolved_settings.orchestration_run_heartbeat_seconds,
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
        agent_service=agent_service,
        cleanup_callbacks=tuple(cleanup_callbacks),
    )
