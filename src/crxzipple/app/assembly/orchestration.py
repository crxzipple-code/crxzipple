"""Orchestration runtime app assembly."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from crxzipple.app.assembly.runtime_defaults import (
    RuntimeSettingsBootstrapConfig,
)
from crxzipple.app.integration.context_workspace_orchestration.adapter import (
    ContextWorkspacePromptSnapshotAdapter,
)
from crxzipple.app.keys import AppKey
from crxzipple.app.plan import ApplicationFactory, AssemblyTarget
from crxzipple.modules.orchestration.application import (
    OrchestrationEngine,
    OrchestrationExecutorService,
    OrchestrationIngressRuntimeService,
    OrchestrationIngressSubmissionService,
    OrchestrationInspectionService,
    OrchestrationRunQueryService,
    OrchestrationSchedulerService,
    OrchestrationSessionRecorder,
    RunPromptInputCollector,
    ToolResolver,
)
from crxzipple.modules.orchestration.application.cancellation import (
    RunCancellationService,
    build_run_cancellation_service,
)
from crxzipple.modules.orchestration.application.intake_service import (
    OrchestrationIntakeService,
)
from crxzipple.modules.orchestration.application.service_graph import (
    OrchestrationServiceGraph,
)
from crxzipple.modules.memory.application import MemoryActorContext
from crxzipple.modules.orchestration.infrastructure.adapters import (
    AuthorizationServiceAdapter,
    LlmServiceAdapter,
    OrchestrationDispatchAdapter,
    ToolServiceAdapter,
)


ORCHESTRATION_ADMIN_RUNTIME_TARGETS: tuple[AssemblyTarget, ...] = (
    AssemblyTarget.API,
    AssemblyTarget.CLI_ADMIN,
)

ORCHESTRATION_TEST_RUNTIME_TARGETS: tuple[AssemblyTarget, ...] = (
    AssemblyTarget.TEST,
)

ORCHESTRATION_SCHEDULER_TARGETS: tuple[AssemblyTarget, ...] = (
    AssemblyTarget.ORCHESTRATION_SCHEDULER,
)

ORCHESTRATION_EXECUTOR_TARGETS: tuple[AssemblyTarget, ...] = (
    AssemblyTarget.ORCHESTRATION_EXECUTOR,
)

ORCHESTRATION_QUERY_ONLY_TARGETS: tuple[AssemblyTarget, ...] = (
    AssemblyTarget.EVENT_RELAY_WORKER,
    AssemblyTarget.OPERATIONS_OBSERVER,
    AssemblyTarget.TOOL_WORKER,
    AssemblyTarget.CHANNEL_RUNTIME,
)

ORCHESTRATION_RUN_QUERY_TARGETS: tuple[AssemblyTarget, ...] = (
    ORCHESTRATION_QUERY_ONLY_TARGETS + (AssemblyTarget.ORCHESTRATION_EXECUTOR,)
)

ORCHESTRATION_SUBMISSION_TARGETS: tuple[AssemblyTarget, ...] = (
    AssemblyTarget.CHANNEL_RUNTIME,
)

ORCHESTRATION_INGRESS_RUNTIME_TARGETS: tuple[AssemblyTarget, ...] = (
    AssemblyTarget.ORCHESTRATION_EXECUTOR,
    AssemblyTarget.TOOL_WORKER,
)


def orchestration_factories() -> tuple[ApplicationFactory, ...]:
    """Build orchestration runtime applications from composed module ports."""

    return (
        ApplicationFactory(
            key="orchestration.run_query_service",
            provides=(AppKey.ORCHESTRATION_RUN_QUERY_SERVICE,),
            requires=(AppKey.UNIT_OF_WORK_FACTORY,),
            build=lambda ctx: OrchestrationRunQueryService(
                ctx.require(AppKey.UNIT_OF_WORK_FACTORY),
            ),
            targets=ORCHESTRATION_RUN_QUERY_TARGETS,
        ),
        ApplicationFactory(
            key="orchestration.submission_service",
            provides=(AppKey.ORCHESTRATION_SUBMISSION_SERVICE,),
            requires=(AppKey.UNIT_OF_WORK_FACTORY,),
            build=lambda ctx: OrchestrationIngressSubmissionService(
                uow_factory=ctx.require(AppKey.UNIT_OF_WORK_FACTORY),
            ),
            targets=ORCHESTRATION_SUBMISSION_TARGETS,
        ),
        ApplicationFactory(
            key="orchestration.ingress_runtime_service",
            provides=(
                AppKey.ORCHESTRATION_SUBMISSION_SERVICE,
                AppKey.ORCHESTRATION_INGRESS_PROCESSING_SERVICE,
            ),
            requires=(
                AppKey.UNIT_OF_WORK_FACTORY,
                AppKey.ORCHESTRATION_RUN_QUERY_SERVICE,
                AppKey.SESSION_RESOLUTION_SERVICE,
                AppKey.DISPATCH_SERVICE,
            ),
            build=_build_orchestration_ingress_runtime_service,
            targets=ORCHESTRATION_INGRESS_RUNTIME_TARGETS,
        ),
        ApplicationFactory(
            key="orchestration.cancellation_service",
            provides=(AppKey.ORCHESTRATION_CANCELLATION_SERVICE,),
            requires=(
                AppKey.UNIT_OF_WORK_FACTORY,
                AppKey.ORCHESTRATION_RUN_QUERY_SERVICE,
                AppKey.SESSION_SERVICE,
                AppKey.DISPATCH_SERVICE,
                AppKey.TOOL_RUN_CONTROL_SERVICE,
            ),
            build=_build_orchestration_cancellation_service,
            targets=ORCHESTRATION_INGRESS_RUNTIME_TARGETS,
        ),
        ApplicationFactory(
            key="orchestration.runtime",
            provides=(
                AppKey.ORCHESTRATION_RUN_QUERY_SERVICE,
                AppKey.ORCHESTRATION_INSPECTION_SERVICE,
                AppKey.ORCHESTRATION_APPROVAL_CONTROL_SERVICE,
                AppKey.ORCHESTRATION_CANCELLATION_SERVICE,
                AppKey.ORCHESTRATION_INTAKE_SERVICE,
                AppKey.ORCHESTRATION_SUBMISSION_SERVICE,
                AppKey.ORCHESTRATION_SCHEDULER_MAINTENANCE_SERVICE,
                AppKey.ORCHESTRATION_EXECUTOR_CONTROL_SERVICE,
            ),
            requires=(
                AppKey.CORE_SETTINGS,
                AppKey.RUNTIME_BOOTSTRAP_CONFIG,
                AppKey.UNIT_OF_WORK_FACTORY,
                AppKey.AUTHORIZATION_SERVICE,
                AppKey.LLM_SERVICE,
                AppKey.TOOL_ORCHESTRATION_PORT,
                AppKey.MEMORY_RUNTIME_SERVICE,
                AppKey.AGENT_SERVICE,
                AppKey.SESSION_SERVICE,
                AppKey.SESSION_RESOLUTION_SERVICE,
                AppKey.DISPATCH_SERVICE,
                AppKey.SKILL_MANAGER,
                AppKey.ARTIFACT_SERVICE,
                AppKey.ACCESS_SERVICE,
                AppKey.CONTEXT_WORKSPACE_SERVICE,
                AppKey.CONTEXT_TREE_SERVICE,
                AppKey.CONTEXT_RENDER_SERVICE,
            ),
            build=_build_orchestration_admin_runtime_factory,
            targets=ORCHESTRATION_ADMIN_RUNTIME_TARGETS,
        ),
        ApplicationFactory(
            key="orchestration.test_runtime",
            provides=(
                AppKey.ORCHESTRATION_RUN_QUERY_SERVICE,
                AppKey.ORCHESTRATION_INSPECTION_SERVICE,
                AppKey.ORCHESTRATION_APPROVAL_CONTROL_SERVICE,
                AppKey.ORCHESTRATION_CANCELLATION_SERVICE,
                AppKey.ORCHESTRATION_INTAKE_SERVICE,
                AppKey.ORCHESTRATION_SUBMISSION_SERVICE,
                AppKey.ORCHESTRATION_SCHEDULER_MAINTENANCE_SERVICE,
                AppKey.ORCHESTRATION_EXECUTOR_CONTROL_SERVICE,
                AppKey.ORCHESTRATION_SCHEDULER_SERVICE,
                AppKey.ORCHESTRATION_EXECUTOR_SERVICE,
            ),
            requires=(
                AppKey.CORE_SETTINGS,
                AppKey.RUNTIME_BOOTSTRAP_CONFIG,
                AppKey.UNIT_OF_WORK_FACTORY,
                AppKey.AUTHORIZATION_SERVICE,
                AppKey.LLM_SERVICE,
                AppKey.TOOL_ORCHESTRATION_PORT,
                AppKey.MEMORY_RUNTIME_SERVICE,
                AppKey.AGENT_SERVICE,
                AppKey.SESSION_SERVICE,
                AppKey.SESSION_RESOLUTION_SERVICE,
                AppKey.DISPATCH_SERVICE,
                AppKey.SKILL_MANAGER,
                AppKey.ARTIFACT_SERVICE,
                AppKey.ACCESS_SERVICE,
                AppKey.CONTEXT_WORKSPACE_SERVICE,
                AppKey.CONTEXT_TREE_SERVICE,
                AppKey.CONTEXT_RENDER_SERVICE,
            ),
            build=_build_orchestration_test_runtime_factory,
            targets=ORCHESTRATION_TEST_RUNTIME_TARGETS,
        ),
        ApplicationFactory(
            key="orchestration.scheduler_runtime",
            provides=(AppKey.ORCHESTRATION_SCHEDULER_SERVICE,),
            requires=(
                AppKey.CORE_SETTINGS,
                AppKey.RUNTIME_BOOTSTRAP_CONFIG,
                AppKey.UNIT_OF_WORK_FACTORY,
                AppKey.AUTHORIZATION_SERVICE,
                AppKey.LLM_SERVICE,
                AppKey.TOOL_ORCHESTRATION_PORT,
                AppKey.MEMORY_RUNTIME_SERVICE,
                AppKey.AGENT_SERVICE,
                AppKey.SESSION_SERVICE,
                AppKey.SESSION_RESOLUTION_SERVICE,
                AppKey.DISPATCH_SERVICE,
                AppKey.SKILL_MANAGER,
                AppKey.ARTIFACT_SERVICE,
                AppKey.ACCESS_SERVICE,
                AppKey.CONTEXT_WORKSPACE_SERVICE,
                AppKey.CONTEXT_TREE_SERVICE,
                AppKey.CONTEXT_RENDER_SERVICE,
            ),
            build=_build_orchestration_scheduler_factory,
            targets=ORCHESTRATION_SCHEDULER_TARGETS,
        ),
        ApplicationFactory(
            key="orchestration.executor_runtime",
            provides=(AppKey.ORCHESTRATION_EXECUTOR_SERVICE,),
            requires=(
                AppKey.CORE_SETTINGS,
                AppKey.RUNTIME_BOOTSTRAP_CONFIG,
                AppKey.UNIT_OF_WORK_FACTORY,
                AppKey.AUTHORIZATION_SERVICE,
                AppKey.LLM_SERVICE,
                AppKey.TOOL_ORCHESTRATION_PORT,
                AppKey.MEMORY_RUNTIME_SERVICE,
                AppKey.AGENT_SERVICE,
                AppKey.SESSION_SERVICE,
                AppKey.SESSION_RESOLUTION_SERVICE,
                AppKey.DISPATCH_SERVICE,
                AppKey.SKILL_MANAGER,
                AppKey.ARTIFACT_SERVICE,
                AppKey.ACCESS_SERVICE,
                AppKey.CONTEXT_WORKSPACE_SERVICE,
                AppKey.CONTEXT_TREE_SERVICE,
                AppKey.CONTEXT_RENDER_SERVICE,
            ),
            build=_build_orchestration_executor_factory,
            targets=ORCHESTRATION_EXECUTOR_TARGETS,
        ),
        ApplicationFactory(
            key="orchestration.run_enqueued_callback_binding",
            provides=(AppKey.ORCHESTRATION_RUN_ENQUEUED_CALLBACK_BINDING_SERVICE,),
            requires=(AppKey.ORCHESTRATION_SUBMISSION_SERVICE,),
            build=lambda ctx: ctx.require(AppKey.ORCHESTRATION_SUBMISSION_SERVICE),
            targets=(
                AssemblyTarget.API,
                AssemblyTarget.TEST,
            ),
        ),
        ApplicationFactory(
            key="orchestration.scheduler_run_enqueued_callback_binding",
            provides=(AppKey.ORCHESTRATION_RUN_ENQUEUED_CALLBACK_BINDING_SERVICE,),
            requires=(AppKey.ORCHESTRATION_SCHEDULER_SERVICE,),
            build=lambda ctx: ctx.require(AppKey.ORCHESTRATION_SCHEDULER_SERVICE),
            targets=ORCHESTRATION_SCHEDULER_TARGETS,
        ),
    )


def _build_orchestration_ingress_runtime_service(
    ctx,
) -> dict[str, OrchestrationIngressRuntimeService]:
    service = OrchestrationIngressRuntimeService(
        uow_factory=ctx.require(AppKey.UNIT_OF_WORK_FACTORY),
        run_query_service=ctx.require(AppKey.ORCHESTRATION_RUN_QUERY_SERVICE),
        session_resolution_service=ctx.require(AppKey.SESSION_RESOLUTION_SERVICE),
        dispatch_port=OrchestrationDispatchAdapter(
            ctx.require(AppKey.DISPATCH_SERVICE),
        ),
    )
    return {
        AppKey.ORCHESTRATION_SUBMISSION_SERVICE: service,
        AppKey.ORCHESTRATION_INGRESS_PROCESSING_SERVICE: service,
    }


def _build_orchestration_cancellation_service(ctx) -> RunCancellationService:
    tool_control = ctx.require(AppKey.TOOL_RUN_CONTROL_SERVICE)
    return build_run_cancellation_service(
        uow_factory=ctx.require(AppKey.UNIT_OF_WORK_FACTORY),
        session_service=ctx.require(AppKey.SESSION_SERVICE),
        run_query_service=ctx.require(AppKey.ORCHESTRATION_RUN_QUERY_SERVICE),
        dispatch_port=OrchestrationDispatchAdapter(
            ctx.require(AppKey.DISPATCH_SERVICE),
        ),
        cancel_tool_run=tool_control.cancel_tool_run,
    )


def _build_orchestration_admin_runtime_factory(ctx) -> dict[str, Any]:
    runtime = _build_orchestration_runtime(ctx)
    return {
        AppKey.ORCHESTRATION_RUN_QUERY_SERVICE: runtime.run_query_service,
        AppKey.ORCHESTRATION_INSPECTION_SERVICE: runtime.inspection_service,
        AppKey.ORCHESTRATION_APPROVAL_CONTROL_SERVICE: runtime.approval_control_service,
        AppKey.ORCHESTRATION_CANCELLATION_SERVICE: runtime.cancellation_service,
        AppKey.ORCHESTRATION_INTAKE_SERVICE: runtime.intake_service,
        AppKey.ORCHESTRATION_SUBMISSION_SERVICE: runtime.scheduler_service,
        AppKey.ORCHESTRATION_SCHEDULER_MAINTENANCE_SERVICE: runtime.scheduler_service,
        AppKey.ORCHESTRATION_EXECUTOR_CONTROL_SERVICE: runtime.executor_service,
    }


def _build_orchestration_test_runtime_factory(ctx) -> dict[str, Any]:
    runtime = _build_orchestration_runtime(ctx)
    return {
        AppKey.ORCHESTRATION_RUN_QUERY_SERVICE: runtime.run_query_service,
        AppKey.ORCHESTRATION_INSPECTION_SERVICE: runtime.inspection_service,
        AppKey.ORCHESTRATION_APPROVAL_CONTROL_SERVICE: runtime.approval_control_service,
        AppKey.ORCHESTRATION_CANCELLATION_SERVICE: runtime.cancellation_service,
        AppKey.ORCHESTRATION_INTAKE_SERVICE: runtime.intake_service,
        AppKey.ORCHESTRATION_SUBMISSION_SERVICE: runtime.scheduler_service,
        AppKey.ORCHESTRATION_SCHEDULER_MAINTENANCE_SERVICE: runtime.scheduler_service,
        AppKey.ORCHESTRATION_EXECUTOR_CONTROL_SERVICE: runtime.executor_service,
        AppKey.ORCHESTRATION_SCHEDULER_SERVICE: runtime.scheduler_service,
        AppKey.ORCHESTRATION_EXECUTOR_SERVICE: runtime.executor_service,
    }


def _build_orchestration_scheduler_factory(ctx) -> OrchestrationSchedulerService:
    return _build_orchestration_runtime(ctx).scheduler_service


def _build_orchestration_executor_factory(ctx) -> OrchestrationExecutorService:
    return _build_orchestration_runtime(ctx).executor_service


def _build_orchestration_runtime(ctx) -> OrchestrationRuntimeAssembly:
    return build_orchestration_runtime(
        settings=ctx.require(AppKey.CORE_SETTINGS),
        runtime_bootstrap_config=ctx.require(AppKey.RUNTIME_BOOTSTRAP_CONFIG),
        uow_factory=ctx.require(AppKey.UNIT_OF_WORK_FACTORY),
        authorization_service=ctx.require(AppKey.AUTHORIZATION_SERVICE),
        llm_service=ctx.require(AppKey.LLM_SERVICE),
        tool_service=ctx.require(AppKey.TOOL_ORCHESTRATION_PORT),
        memory_port=ctx.require(AppKey.MEMORY_RUNTIME_SERVICE),
        agent_service=ctx.require(AppKey.AGENT_SERVICE),
        session_service=ctx.require(AppKey.SESSION_SERVICE),
        session_resolution_service=ctx.require(AppKey.SESSION_RESOLUTION_SERVICE),
        dispatch_service=ctx.require(AppKey.DISPATCH_SERVICE),
        skill_manager=ctx.require(AppKey.SKILL_MANAGER),
        artifact_service=ctx.require(AppKey.ARTIFACT_SERVICE),
        access_service=ctx.require(AppKey.ACCESS_SERVICE),
        context_workspace_service=ctx.require(AppKey.CONTEXT_WORKSPACE_SERVICE),
        context_tree_service=ctx.require(AppKey.CONTEXT_TREE_SERVICE),
        context_render_service=ctx.require(AppKey.CONTEXT_RENDER_SERVICE),
        events_service=(
            ctx.require(AppKey.EVENTS_SERVICE) if ctx.has(AppKey.EVENTS_SERVICE) else None
        ),
    )


@dataclass(slots=True)
class OrchestrationRuntimeAssembly:
    run_query_service: OrchestrationRunQueryService
    inspection_service: OrchestrationInspectionService
    approval_control_service: Any
    cancellation_service: RunCancellationService
    intake_service: OrchestrationIntakeService
    scheduler_service: OrchestrationSchedulerService
    executor_service: OrchestrationExecutorService
    authorization_port: Any
    llm_port: Any
    tool_port: Any


def build_orchestration_runtime(
    *,
    settings: Any,
    runtime_bootstrap_config: RuntimeSettingsBootstrapConfig,
    uow_factory: Callable[[], Any],
    authorization_service: Any,
    llm_service: Any,
    tool_service: Any,
    memory_port: Any,
    agent_service: Any,
    session_service: Any,
    session_resolution_service: Any,
    dispatch_service: Any,
    skill_manager: Any,
    artifact_service: Any,
    access_service: Any,
    context_workspace_service: Any,
    context_tree_service: Any,
    context_render_service: Any,
    events_service: Any | None,
) -> OrchestrationRuntimeAssembly:
    authorization_port = AuthorizationServiceAdapter(authorization_service)
    llm_port = LlmServiceAdapter(llm_service)
    tool_port = ToolServiceAdapter(tool_service)
    run_query_service = OrchestrationRunQueryService(uow_factory)
    prompt_inputs = RunPromptInputCollector(
        agent_service=agent_service,
        llm_port=llm_port,
        skill_catalog_port=skill_manager,
        session_service=session_service,
        artifact_service=artifact_service,
        access_port=access_service,
        events_service=events_service,
        execution_query=run_query_service,
        context_block_max_chars=settings.prompt_system_max_chars,
        context_block_max_tokens=settings.prompt_system_max_tokens,
        context_block_context_window_ratio=(
            settings.prompt_system_context_window_ratio
        ),
        llm_image_max_bytes=settings.artifact_image_llm_max_bytes,
        llm_file_max_bytes=settings.artifact_file_llm_max_bytes,
        llm_text_file_max_chars=settings.artifact_text_file_llm_max_chars,
        runtime_llm_defaults=settings.llm_request_defaults.to_payload(),
    )
    tool_resolver = ToolResolver(
        tool_catalog=tool_port,
        authorization_port=authorization_port,
        access_port=access_service,
        run_context_provider=_run_context_provider_factory(
            agent_service=agent_service,
            session_service=session_service,
            memory_port=memory_port,
        ),
    )
    context_snapshot_port = ContextWorkspacePromptSnapshotAdapter(
        workspace_service=context_workspace_service,
        render_service=context_render_service,
        tree_service=context_tree_service,
        artifact_service=artifact_service,
    )
    orchestration_engine = OrchestrationEngine(
        prompt_inputs=prompt_inputs,
        session_recorder=OrchestrationSessionRecorder(
            session_service=session_service,
            execution_item_lookup=run_query_service,
        ),
        llm_port=llm_port,
        tool_resolver=tool_resolver,
        tool_execution_port=tool_port,
        memory_port=memory_port,
        context_snapshot_port=context_snapshot_port,
        detailed_phase_metrics_enabled=(
            settings.orchestration_detailed_engine_metrics_enabled
        ),
    )
    service_graph = OrchestrationServiceGraph(
        uow_factory,
        dispatch_port=OrchestrationDispatchAdapter(
            dispatch_service=dispatch_service,
        ),
        agent_service=agent_service,
        authorization_port=authorization_port,
        llm_port=llm_port,
        memory_port=memory_port,
        session_service=session_service,
        session_resolution_service=session_resolution_service,
        engine=orchestration_engine,
        worker_lease_seconds=runtime_bootstrap_config.orchestration_run_lease_seconds,
        worker_heartbeat_seconds=(
            runtime_bootstrap_config.orchestration_run_heartbeat_seconds
        ),
        auto_compaction_enabled=(
            runtime_bootstrap_config.orchestration_auto_compaction_enabled
        ),
        auto_compaction_reserve_tokens=(
            runtime_bootstrap_config.orchestration_auto_compaction_reserve_tokens
        ),
        auto_compaction_soft_threshold_tokens=(
            runtime_bootstrap_config.orchestration_auto_compaction_soft_threshold_tokens
        ),
        events_service=events_service,
        run_query_service=run_query_service,
    )
    return OrchestrationRuntimeAssembly(
        run_query_service=run_query_service,
        inspection_service=service_graph.inspection_service,
        approval_control_service=service_graph.approval_control_service,
        cancellation_service=service_graph.cancellation_service,
        intake_service=service_graph.intake_service,
        scheduler_service=service_graph.scheduler_service,
        executor_service=service_graph.executor_service,
        authorization_port=authorization_port,
        llm_port=llm_port,
        tool_port=tool_port,
    )


def _run_context_provider_factory(*, agent_service: Any, session_service: Any, memory_port: Any):
    def _run_context_provider(run) -> dict[str, object]:
        workspace_dir: str | None = None
        session_key = str(run.metadata.get("session_key", "")).strip()
        if session_key:
            try:
                session = session_service.get_session(session_key)
            except Exception:
                session = None
            if session is not None:
                workspace_dir = session.runtime_binding().workspace
        available_scopes: list[str] = []
        if session_key:
            available_scopes.append("session_context")
        if run.agent_id is not None:
            try:
                memory_port.resolve_access_plan(
                    MemoryActorContext(
                        agent_id=run.agent_id,
                        run_id=run.id,
                        session_key=session_key,
                        active_session_id=run.active_session_id,
                        workspace_dir=workspace_dir,
                    ),
                )
            except ValueError:
                pass
            else:
                available_scopes.append("memory_context")
        if workspace_dir is not None and workspace_dir.strip():
            available_scopes.append("workspace_bound")
        attrs: dict[str, object] = {
            "available_scopes": available_scopes,
        }
        if run.agent_id is not None:
            try:
                agent_profile = agent_service.get_profile(run.agent_id)
            except Exception:
                agent_profile = None
            if agent_profile is not None:
                browser_profile = _agent_default_browser_profile(agent_profile)
                if browser_profile is not None:
                    attrs["agent_default_browser_profile"] = browser_profile
        if workspace_dir is not None and workspace_dir.strip():
            attrs["workspace_dir"] = workspace_dir.strip()
        return attrs

    return _run_context_provider


def _agent_default_browser_profile(agent_profile: Any) -> str | None:
    runtime_preferences = getattr(agent_profile, "runtime_preferences", None)
    attrs = getattr(runtime_preferences, "attrs", None)
    if not isinstance(attrs, dict):
        return None
    value = attrs.get("default_browser_profile")
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


__all__ = [
    "ORCHESTRATION_EXECUTOR_TARGETS",
    "ORCHESTRATION_INGRESS_RUNTIME_TARGETS",
    "ORCHESTRATION_QUERY_ONLY_TARGETS",
    "ORCHESTRATION_RUN_QUERY_TARGETS",
    "ORCHESTRATION_SCHEDULER_TARGETS",
    "ORCHESTRATION_SUBMISSION_TARGETS",
    "OrchestrationIngressSubmissionService",
    "orchestration_factories",
]
