"""Memory module app assembly."""

from __future__ import annotations

from typing import Any

from crxzipple.app.keys import AppKey
from crxzipple.app.plan import ApplicationFactory
from crxzipple.app.integration.memory_legacy_migration import (
    MemoryLegacyMigrationService,
)
from crxzipple.app.integration.memory_scope_resolution import AgentMemoryScopeResolver
from crxzipple.modules.events import EventsApplicationService
from crxzipple.modules.memory.application import (
    FileBackedMemoryService,
    MemorySettingsBootstrapConfig,
    MemoryPolicyService,
    MemoryQueryService,
    MemorySpaceService,
    MemoryRuntimeService,
    memory_bootstrap_config_from_settings,
)
from crxzipple.modules.memory.application.events import (
    MEMORY_ENGINE_READINESS_FAILED_EVENT,
    MEMORY_ENGINE_READINESS_OBSERVED_EVENT,
    emit_memory_event,
    memory_event_from_payload,
)
from crxzipple.modules.memory.infrastructure import (
    FileMemoryIndexManager,
    FileMarkdownMemoryEngine,
    FileMemoryStore,
    MemoryWatchRegistry,
    SqlAlchemyMemoryPolicyRepository,
    SqlAlchemyMemorySpaceRepository,
)
from crxzipple.modules.memory.infrastructure.indexing import (
    LocalHashedMemoryEmbeddingProvider,
    OpenAICompatibleMemoryEmbeddingProvider,
)


def memory_factories(
    *,
    enable_watchers: bool = False,
) -> tuple[ApplicationFactory, ...]:
    """Build Memory module-local service and optional watch registry."""

    return (
        ApplicationFactory(
            key="memory.bootstrap_config",
            provides=(AppKey.MEMORY_BOOTSTRAP_CONFIG,),
            requires=(AppKey.SETTINGS_MATERIALIZER,),
            build=_build_memory_bootstrap_config,
        ),
        ApplicationFactory(
            key="memory.space_service",
            provides=(AppKey.MEMORY_SPACE_SERVICE,),
            requires=(
                AppKey.DATABASE_SESSION_FACTORY,
                AppKey.MEMORY_BOOTSTRAP_CONFIG,
            ),
            build=lambda ctx: MemorySpaceService(
                SqlAlchemyMemorySpaceRepository(
                    ctx.require(AppKey.DATABASE_SESSION_FACTORY),
                ),
                default_storage_root=ctx.require(
                    AppKey.MEMORY_BOOTSTRAP_CONFIG,
                ).storage_root,
            ),
        ),
        ApplicationFactory(
            key="memory.policy_service",
            provides=(AppKey.MEMORY_POLICY_SERVICE,),
            requires=(AppKey.DATABASE_SESSION_FACTORY,),
            build=lambda ctx: MemoryPolicyService(
                SqlAlchemyMemoryPolicyRepository(
                    ctx.require(AppKey.DATABASE_SESSION_FACTORY),
                ),
            ),
        ),
        ApplicationFactory(
            key="memory.file_service",
            provides=(
                AppKey.FILE_MEMORY_SERVICE,
                AppKey.MEMORY_WATCH_REGISTRY,
            ),
            requires=(
                AppKey.MEMORY_BOOTSTRAP_CONFIG,
                AppKey.EVENTS_SERVICE,
                AppKey.ACCESS_SERVICE,
            ),
            build=lambda ctx: _build_memory_service(
                ctx,
                enable_watchers=enable_watchers,
            ),
        ),
    )


def memory_context_factories(
    *,
    create_missing_spaces: bool = True,
) -> tuple[ApplicationFactory, ...]:
    """Build Agent + Memory integration ports used by runtime composition."""

    return (
        ApplicationFactory(
            key="memory.context_resolver",
            provides=(
                AppKey.MEMORY_CONTEXT_RESOLVER,
                AppKey.MEMORY_LEGACY_MIGRATION_SERVICE,
                AppKey.MEMORY_QUERY_SERVICE,
                AppKey.MEMORY_RUNTIME_SERVICE,
            ),
            requires=(
                AppKey.AGENT_SERVICE,
                AppKey.MEMORY_SPACE_SERVICE,
                AppKey.MEMORY_POLICY_SERVICE,
                AppKey.FILE_MEMORY_SERVICE,
                AppKey.MEMORY_BOOTSTRAP_CONFIG,
            ),
            build=lambda ctx: _build_memory_context_ports(
                ctx,
                create_missing_spaces=create_missing_spaces,
            ),
        ),
    )


def _build_memory_bootstrap_config(ctx) -> MemorySettingsBootstrapConfig:
    materializer = ctx.require(AppKey.SETTINGS_MATERIALIZER)
    memory_resource_config = materializer.memory_config()
    if memory_resource_config is None:
        return MemorySettingsBootstrapConfig()
    return memory_bootstrap_config_from_settings(memory_resource_config)


def _build_memory_service(
    ctx,
    *,
    enable_watchers: bool,
) -> dict[str, Any]:
    config = ctx.require(AppKey.MEMORY_BOOTSTRAP_CONFIG)
    events_service = ctx.require(AppKey.EVENTS_SERVICE)
    access_service = ctx.require(AppKey.ACCESS_SERVICE)
    event_emitter = build_memory_event_emitter(events_service)
    try:
        embedding_provider = build_memory_embedding_provider(
            config,
            credential_provider=access_service,
        )
    except Exception as exc:
        emit_memory_event(
            event_emitter,
            MEMORY_ENGINE_READINESS_FAILED_EVENT,
            status="failed",
            level="error",
            payload=_memory_engine_readiness_payload(
                config,
                status="failed",
                error_message=str(exc),
            ),
        )
        raise
    emit_memory_event(
        event_emitter,
        MEMORY_ENGINE_READINESS_OBSERVED_EVENT,
        status="ready",
        payload=_memory_engine_readiness_payload(
            config,
            status="ready",
            embedding_provider=embedding_provider,
        ),
    )
    service = FileBackedMemoryService(
        store=FileMemoryStore(),
        index_manager=FileMemoryIndexManager(
            embedding_provider=embedding_provider,
        ),
        event_emitter=event_emitter,
    )
    watch_registry = (
        MemoryWatchRegistry(
            memory_service=service,
            enabled=True,
            interval_seconds=config.watch_interval_seconds,
        )
        if enable_watchers
        else None
    )
    return {
        AppKey.FILE_MEMORY_SERVICE: service,
        AppKey.MEMORY_WATCH_REGISTRY: watch_registry,
    }


def _memory_engine_readiness_payload(
    config: MemorySettingsBootstrapConfig,
    *,
    status: str,
    embedding_provider: Any | None = None,
    error_message: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "engine_id": "file_markdown",
        "readiness_status": status,
        "retrieval_backend": config.retrieval_backend,
        "vector_provider": config.vector_provider,
        "vector_model": config.vector_model
        or getattr(embedding_provider, "model_name", None)
        or ("text-embedding-3-small" if config.vector_provider == "openai_compatible" else "local-hashed-v1"),
        "credential_binding_id": config.vector_credential_binding_id,
        "requires_credentials": config.vector_provider == "openai_compatible",
    }
    if error_message:
        payload["error_message"] = error_message
    return payload


def _build_memory_context_ports(
    ctx,
    *,
    create_missing_spaces: bool,
) -> dict[str, Any]:
    bootstrap_config = ctx.require(AppKey.MEMORY_BOOTSTRAP_CONFIG)
    file_memory_service = ctx.require(AppKey.FILE_MEMORY_SERVICE)
    memory_watch_registry = (
        ctx.require(AppKey.MEMORY_WATCH_REGISTRY)
        if ctx.has(AppKey.MEMORY_WATCH_REGISTRY)
        else None
    )
    events_service = (
        ctx.require(AppKey.EVENTS_SERVICE) if ctx.has(AppKey.EVENTS_SERVICE) else None
    )
    context_resolver = AgentMemoryScopeResolver(
        agent_service=ctx.require(AppKey.AGENT_SERVICE),
        memory_spaces=ctx.require(AppKey.MEMORY_SPACE_SERVICE),
        default_retrieval_backend=bootstrap_config.retrieval_backend,
        context_observer=(
            memory_watch_registry.ensure_watching
            if memory_watch_registry is not None
            else None
        ),
        event_emitter=build_memory_event_emitter(events_service),
        create_missing_spaces=create_missing_spaces,
    )
    runtime_service = MemoryRuntimeService(
        scope_resolver=context_resolver,
        engine=FileMarkdownMemoryEngine(file_memory_service),
        policy_provider=ctx.require(AppKey.MEMORY_POLICY_SERVICE),
        space_inventory=ctx.require(AppKey.MEMORY_SPACE_SERVICE),
    )
    query_service = MemoryQueryService(
        file_memory_service=file_memory_service,
        scope_resolver=context_resolver,
    )
    legacy_migration_service = MemoryLegacyMigrationService(
        agent_service=ctx.require(AppKey.AGENT_SERVICE),
        memory_spaces=ctx.require(AppKey.MEMORY_SPACE_SERVICE),
        default_retrieval_backend=bootstrap_config.retrieval_backend,
    )
    return {
        AppKey.MEMORY_CONTEXT_RESOLVER: context_resolver,
        AppKey.MEMORY_LEGACY_MIGRATION_SERVICE: legacy_migration_service,
        AppKey.MEMORY_QUERY_SERVICE: query_service,
        AppKey.MEMORY_RUNTIME_SERVICE: runtime_service,
    }


def build_memory_embedding_provider(
    config: MemorySettingsBootstrapConfig,
    *,
    credential_provider: Any | None = None,
):
    if config.vector_provider == "openai_compatible":
        if not config.vector_credential_binding_id:
            raise ValueError(
                "OpenAI-compatible memory embeddings require vector_credential_binding_id.",
            )
        if credential_provider is None:
            raise ValueError(
                "OpenAI-compatible memory embeddings require an Access credential provider.",
            )
        _validate_memory_embedding_credential_binding(
            config.vector_credential_binding_id,
            credential_provider=credential_provider,
        )
        return OpenAICompatibleMemoryEmbeddingProvider(
            base_url=config.vector_base_url or "https://api.openai.com/v1",
            model_name=config.vector_model or "text-embedding-3-small",
            credential_binding_id=config.vector_credential_binding_id,
            credential_provider=credential_provider,
            timeout_seconds=config.vector_timeout_seconds,
        )
    return LocalHashedMemoryEmbeddingProvider(
        model_name=config.vector_model or "local-hashed-v1",
    )


def _validate_memory_embedding_credential_binding(
    binding_id: str,
    *,
    credential_provider: Any,
) -> None:
    describe = getattr(credential_provider, "describe_credential_binding", None)
    if not callable(describe):
        return
    metadata = describe(binding_id)
    if metadata is None:
        raise ValueError(
            "OpenAI-compatible memory embeddings reference unknown Access "
            f"credential binding '{binding_id}'.",
        )
    binding_kind = str(metadata.get("binding_kind") or "").strip().lower()
    if binding_kind != "api_key":
        actual = binding_kind or "unknown"
        raise ValueError(
            "OpenAI-compatible memory embeddings require an Access api_key "
            f"credential binding, but '{binding_id}' is {actual}.",
        )
    status = str(metadata.get("status") or "active").strip().lower()
    if status != "active":
        raise ValueError(
            "OpenAI-compatible memory embeddings require an active Access "
            f"credential binding, but '{binding_id}' is {status}.",
        )


def build_memory_event_emitter(
    events_service: EventsApplicationService | None,
):
    if not isinstance(events_service, EventsApplicationService):
        return None

    def emit(event_name: str, payload: dict[str, object]) -> None:
        events_service.publish(memory_event_from_payload(event_name, payload))

    return emit


__all__ = [
    "build_memory_embedding_provider",
    "build_memory_event_emitter",
    "memory_context_factories",
    "memory_factories",
]
