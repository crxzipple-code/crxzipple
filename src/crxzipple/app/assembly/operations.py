"""Operations read-model and observer app assembly."""

from __future__ import annotations

from typing import Any

from crxzipple.app.keys import AppKey
from crxzipple.app.plan import ApplicationFactory, AssemblyTarget
from crxzipple.modules.operations.application.projections import (
    OperationsProjectionMaterializer,
)
from crxzipple.modules.operations.application.read_models.factory import (
    OperationsSourceReadModelContext,
    build_operations_source_read_model_provider,
)
from crxzipple.modules.operations.infrastructure.persistence.repositories import (
    SqlAlchemyOperationsActionAuditStore,
    SqlAlchemyOperationsObservationStore,
    SqlAlchemyOperationsProjectionStore,
)


def operations_factories() -> tuple[ApplicationFactory, ...]:
    """Build Operations stores and app-level projection materializer."""

    projection_targets = (
        AssemblyTarget.API,
        AssemblyTarget.OPERATIONS_OBSERVER,
        AssemblyTarget.TEST,
    )
    return (
        ApplicationFactory(
            key="operations.stores",
            provides=(
                AppKey.OPERATIONS_OBSERVATION_STORE,
                AppKey.OPERATIONS_ACTION_AUDIT_STORE,
                AppKey.OPERATIONS_PROJECTION_STORE,
            ),
            requires=(AppKey.DATABASE_SESSION_FACTORY,),
            build=_build_operations_stores,
            targets=projection_targets,
        ),
        ApplicationFactory(
            key="operations.projection_materializer",
            provides=(
                AppKey.OPERATIONS_SOURCE_READ_MODEL_CONTEXT,
                AppKey.OPERATIONS_READ_MODEL_PROVIDER,
                AppKey.OPERATIONS_PROJECTION_MATERIALIZER,
            ),
            requires=(
                AppKey.RUNTIME_BOOTSTRAP_CONFIG,
                AppKey.EVENTS_SERVICE,
                AppKey.EVENT_CONTRACT_REGISTRY,
                AppKey.EVENT_DEFINITION_REGISTRY,
                AppKey.OPERATIONS_OBSERVATION_STORE,
                AppKey.OPERATIONS_PROJECTION_STORE,
                AppKey.ACCESS_GOVERNANCE_REPOSITORY,
                AppKey.SETTINGS_QUERY_SERVICE,
                AppKey.CORE_SETTINGS,
                AppKey.ORCHESTRATION_RUN_QUERY_SERVICE,
                AppKey.TOOL_QUERY_SERVICE,
                AppKey.ACCESS_SERVICE,
                AppKey.ARTIFACT_SERVICE,
                AppKey.TOOL_REMOTE_RUNTIME_REGISTRY,
                AppKey.LLM_SERVICE,
                AppKey.AGENT_SERVICE,
                AppKey.FILE_MEMORY_SERVICE,
                AppKey.MEMORY_CONTEXT_RESOLVER,
                AppKey.CONTEXT_WORKSPACE_SERVICE,
                AppKey.CONTEXT_TREE_SERVICE,
                AppKey.CONTEXT_RENDER_SERVICE,
                AppKey.SKILL_MANAGER,
                AppKey.BROWSER_QUERY_SERVICE,
                AppKey.CHANNEL_INFRASTRUCTURE,
                AppKey.DAEMON_SERVICE,
                AppKey.DAEMON_MANAGER,
                AppKey.PROCESS_SERVICE,
            ),
            build=_build_operations_projection_materializer,
            targets=projection_targets,
        ),
    )


def _build_operations_stores(ctx) -> dict[str, Any]:
    session_factory = ctx.require(AppKey.DATABASE_SESSION_FACTORY)
    return {
        AppKey.OPERATIONS_OBSERVATION_STORE: SqlAlchemyOperationsObservationStore(
            session_factory,
        ),
        AppKey.OPERATIONS_ACTION_AUDIT_STORE: SqlAlchemyOperationsActionAuditStore(
            session_factory,
        ),
        AppKey.OPERATIONS_PROJECTION_STORE: SqlAlchemyOperationsProjectionStore(
            session_factory,
        ),
    }


def _build_operations_projection_materializer(ctx) -> dict[str, Any]:
    channels = ctx.require(AppKey.CHANNEL_INFRASTRUCTURE)
    context = OperationsSourceReadModelContext(
        runtime_bootstrap_config=ctx.require(AppKey.RUNTIME_BOOTSTRAP_CONFIG),
        events_service=ctx.require(AppKey.EVENTS_SERVICE),
        event_contract_registry=ctx.require(AppKey.EVENT_CONTRACT_REGISTRY),
        event_definition_registry=ctx.require(AppKey.EVENT_DEFINITION_REGISTRY),
        operations_observation_store=ctx.require(AppKey.OPERATIONS_OBSERVATION_STORE),
        access_governance_repository=ctx.require(AppKey.ACCESS_GOVERNANCE_REPOSITORY),
        settings_query_service=ctx.require(AppKey.SETTINGS_QUERY_SERVICE),
        settings_environment=ctx.require(AppKey.CORE_SETTINGS).environment,
        orchestration_run_query_service=ctx.require(
            AppKey.ORCHESTRATION_RUN_QUERY_SERVICE,
        ),
        orchestration_executor_lease_query=ctx.require(
            AppKey.ORCHESTRATION_RUN_QUERY_SERVICE,
        ),
        tool_service=ctx.require(AppKey.TOOL_QUERY_SERVICE),
        access_service=ctx.require(AppKey.ACCESS_SERVICE),
        artifact_service=ctx.require(AppKey.ARTIFACT_SERVICE),
        remote_tool_registry=ctx.require(AppKey.TOOL_REMOTE_RUNTIME_REGISTRY),
        llm_service=ctx.require(AppKey.LLM_SERVICE),
        agent_service=ctx.require(AppKey.AGENT_SERVICE),
        memory_query_service=ctx.require(AppKey.MEMORY_QUERY_SERVICE),
        memory_watch_registry=(
            ctx.require(AppKey.MEMORY_WATCH_REGISTRY)
            if ctx.has(AppKey.MEMORY_WATCH_REGISTRY)
            else None
        ),
        context_workspace_service=ctx.require(AppKey.CONTEXT_WORKSPACE_SERVICE),
        context_tree_service=ctx.require(AppKey.CONTEXT_TREE_SERVICE),
        context_render_service=ctx.require(AppKey.CONTEXT_RENDER_SERVICE),
        skill_manager=ctx.require(AppKey.SKILL_MANAGER),
        browser_profile_service=ctx.require(AppKey.BROWSER_QUERY_SERVICE),
        channel_profile_service=channels.profile_service,
        channel_runtime_manager=channels.runtime_manager,
        channel_interaction_service=channels.interaction_service,
        daemon_service=ctx.require(AppKey.DAEMON_SERVICE),
        daemon_manager=ctx.require(AppKey.DAEMON_MANAGER),
        process_service=ctx.require(AppKey.PROCESS_SERVICE),
    )
    read_model_provider = build_operations_source_read_model_provider(context)
    return {
        AppKey.OPERATIONS_SOURCE_READ_MODEL_CONTEXT: context,
        AppKey.OPERATIONS_READ_MODEL_PROVIDER: read_model_provider,
        AppKey.OPERATIONS_PROJECTION_MATERIALIZER: OperationsProjectionMaterializer(
            source_provider=read_model_provider,
            projection_store=ctx.require(AppKey.OPERATIONS_PROJECTION_STORE),
            events_service=ctx.require(AppKey.EVENTS_SERVICE),
        ),
    }


__all__ = ["operations_factories"]
