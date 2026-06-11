"""Context Workspace module app assembly."""

from __future__ import annotations

from crxzipple.app.keys import AppKey
from crxzipple.app.plan import ApplicationFactory, AssemblyTarget
from crxzipple.app.integration.context_workspace_skills import (
    SkillContextNodeProvider,
)
from crxzipple.app.integration.context_workspace_session import (
    SessionContextNodeProvider,
)
from crxzipple.app.integration.context_workspace_memory import (
    MemoryContextNodeProvider,
)
from crxzipple.app.integration.context_workspace_tool import (
    ToolContextNodeProvider,
)
from crxzipple.app.integration.context_workspace_artifacts import (
    ArtifactContextNodeProvider,
)
from crxzipple.app.integration.context_workspace_agent import (
    AgentHomeContextNodeProvider,
)
from crxzipple.app.integration.context_workspace_workspace import (
    WorkspaceContextNodeProvider,
)
from crxzipple.modules.context_workspace.application import (
    ContextOwnerRegistry,
    ContextRenderService,
    ContextTreeService,
    ContextWorkspaceService,
    ContextWorkspaceServices,
)
from crxzipple.modules.context_workspace.infrastructure import (
    SqlAlchemyContextNodeRepository,
    SqlAlchemyContextOperationRepository,
    SqlAlchemyContextRenderSnapshotRepository,
    SqlAlchemyContextWorkspaceRepository,
)

CONTEXT_TOOL_PROVIDER_TARGETS: tuple[AssemblyTarget, ...] = (
    AssemblyTarget.API,
    AssemblyTarget.CLI_ADMIN,
    AssemblyTarget.TEST,
    AssemblyTarget.ORCHESTRATION_EXECUTOR,
)


def context_workspace_factories() -> tuple[ApplicationFactory, ...]:
    """Build Context Workspace module-local application services."""

    return (
        ApplicationFactory(
            key="context_workspace.services",
            provides=(
                AppKey.CONTEXT_OWNER_REGISTRY,
                AppKey.CONTEXT_WORKSPACE_SERVICE,
                AppKey.CONTEXT_TREE_SERVICE,
                AppKey.CONTEXT_RENDER_SERVICE,
            ),
            requires=(AppKey.DATABASE_SESSION_FACTORY,),
            build=_build_context_workspace_services,
        ),
    )


def context_workspace_integration_factories() -> tuple[ApplicationFactory, ...]:
    """Register owner adapters that feed Context Workspace nodes."""

    return (
        ApplicationFactory(
            key="context_workspace.session_provider",
            provides=(AppKey.CONTEXT_SESSION_NODE_PROVIDER,),
            requires=(
                AppKey.CONTEXT_OWNER_REGISTRY,
                AppKey.SESSION_SERVICE,
            ),
            build=_build_session_node_provider,
        ),
        ApplicationFactory(
            key="context_workspace.agent_home_provider",
            provides=(AppKey.CONTEXT_AGENT_HOME_NODE_PROVIDER,),
            requires=(AppKey.CONTEXT_OWNER_REGISTRY, AppKey.AGENT_SERVICE),
            build=_build_agent_home_node_provider,
        ),
        ApplicationFactory(
            key="context_workspace.skill_provider",
            provides=(AppKey.CONTEXT_SKILL_NODE_PROVIDER,),
            requires=(AppKey.CONTEXT_OWNER_REGISTRY, AppKey.SKILL_MANAGER),
            build=_build_skill_node_provider,
        ),
        ApplicationFactory(
            key="context_workspace.tool_provider",
            provides=(AppKey.CONTEXT_TOOL_NODE_PROVIDER,),
            requires=(
                AppKey.CONTEXT_OWNER_REGISTRY,
                AppKey.TOOL_SERVICE,
                AppKey.TOOL_SOURCE_QUERY_SERVICE,
            ),
            build=_build_tool_node_provider,
            targets=CONTEXT_TOOL_PROVIDER_TARGETS,
        ),
        ApplicationFactory(
            key="context_workspace.memory_provider",
            provides=(AppKey.CONTEXT_MEMORY_NODE_PROVIDER,),
            requires=(AppKey.CONTEXT_OWNER_REGISTRY, AppKey.MEMORY_RUNTIME_SERVICE),
            build=_build_memory_node_provider,
        ),
        ApplicationFactory(
            key="context_workspace.artifact_provider",
            provides=(AppKey.CONTEXT_ARTIFACT_NODE_PROVIDER,),
            requires=(
                AppKey.CONTEXT_OWNER_REGISTRY,
                AppKey.SESSION_SERVICE,
                AppKey.ARTIFACT_SERVICE,
            ),
            build=_build_artifact_node_provider,
        ),
        ApplicationFactory(
            key="context_workspace.workspace_provider",
            provides=(AppKey.CONTEXT_WORKSPACE_NODE_PROVIDER,),
            requires=(AppKey.CONTEXT_OWNER_REGISTRY,),
            build=_build_workspace_node_provider,
        ),
    )


def _build_context_workspace_services(ctx) -> dict[str, object]:
    session_factory = ctx.require(AppKey.DATABASE_SESSION_FACTORY)
    owner_registry = ContextOwnerRegistry()
    workspace_repository = SqlAlchemyContextWorkspaceRepository(session_factory)
    node_repository = SqlAlchemyContextNodeRepository(session_factory)
    operation_repository = SqlAlchemyContextOperationRepository(session_factory)
    snapshot_repository = SqlAlchemyContextRenderSnapshotRepository(session_factory)
    workspace_service = ContextWorkspaceService(
        workspace_repository=workspace_repository,
        node_repository=node_repository,
        owner_registry=owner_registry,
    )
    tree_service = ContextTreeService(
        workspace_repository=workspace_repository,
        node_repository=node_repository,
        operation_repository=operation_repository,
        owner_registry=owner_registry,
    )
    render_service = ContextRenderService(
        workspace_repository=workspace_repository,
        node_repository=node_repository,
        snapshot_repository=snapshot_repository,
        owner_registry=owner_registry,
    )
    services = ContextWorkspaceServices(
        workspaces=workspace_service,
        tree=tree_service,
        render=render_service,
    )
    return {
        AppKey.CONTEXT_OWNER_REGISTRY: owner_registry,
        AppKey.CONTEXT_WORKSPACE_SERVICE: services.workspaces,
        AppKey.CONTEXT_TREE_SERVICE: services.tree,
        AppKey.CONTEXT_RENDER_SERVICE: services.render,
    }


def _build_session_node_provider(ctx) -> SessionContextNodeProvider:
    registry = ctx.require(AppKey.CONTEXT_OWNER_REGISTRY)
    provider = SessionContextNodeProvider(
        session_service=ctx.require(AppKey.SESSION_SERVICE),
        execution_query=ctx.registry.get(AppKey.ORCHESTRATION_RUN_QUERY_SERVICE),
    )
    registry.register(provider)
    return provider


def _build_agent_home_node_provider(ctx) -> AgentHomeContextNodeProvider:
    registry = ctx.require(AppKey.CONTEXT_OWNER_REGISTRY)
    provider = AgentHomeContextNodeProvider(
        agent_service=ctx.require(AppKey.AGENT_SERVICE),
    )
    registry.register(provider)
    return provider


def _build_skill_node_provider(ctx) -> SkillContextNodeProvider:
    registry = ctx.require(AppKey.CONTEXT_OWNER_REGISTRY)
    provider = SkillContextNodeProvider(
        skill_service=ctx.require(AppKey.SKILL_MANAGER),
    )
    registry.register(provider)
    return provider


def _build_tool_node_provider(ctx) -> ToolContextNodeProvider:
    registry = ctx.require(AppKey.CONTEXT_OWNER_REGISTRY)
    provider = ToolContextNodeProvider(
        tool_service=ctx.require(AppKey.TOOL_SERVICE),
        prompt_catalog=ctx.require(AppKey.TOOL_SOURCE_QUERY_SERVICE),
    )
    registry.register(provider)
    return provider


def _build_memory_node_provider(ctx) -> MemoryContextNodeProvider:
    registry = ctx.require(AppKey.CONTEXT_OWNER_REGISTRY)
    provider = MemoryContextNodeProvider(
        memory_runtime_service=ctx.require(AppKey.MEMORY_RUNTIME_SERVICE),
    )
    registry.register(provider)
    return provider


def _build_artifact_node_provider(ctx) -> ArtifactContextNodeProvider:
    registry = ctx.require(AppKey.CONTEXT_OWNER_REGISTRY)
    provider = ArtifactContextNodeProvider(
        session_service=ctx.require(AppKey.SESSION_SERVICE),
        artifact_service=ctx.require(AppKey.ARTIFACT_SERVICE),
    )
    registry.register(provider)
    return provider


def _build_workspace_node_provider(ctx) -> WorkspaceContextNodeProvider:
    registry = ctx.require(AppKey.CONTEXT_OWNER_REGISTRY)
    provider = WorkspaceContextNodeProvider()
    registry.register(provider)
    return provider


__all__ = ["context_workspace_factories", "context_workspace_integration_factories"]
