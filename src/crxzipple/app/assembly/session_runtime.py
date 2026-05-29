from __future__ import annotations

from crxzipple.app.integration.session_runtime_control import (
    IngressBackedSessionRuntimeControl,
    SchedulerBackedSessionRuntimeControl,
)
from crxzipple.app.keys import AppKey
from crxzipple.app.plan import ApplicationFactory, AssemblyTarget


SESSION_RUNTIME_CONTROL_TARGETS: tuple[AssemblyTarget, ...] = (
    AssemblyTarget.API,
    AssemblyTarget.CLI_ADMIN,
    AssemblyTarget.TEST,
)

INGRESS_SESSION_RUNTIME_CONTROL_TARGETS: tuple[AssemblyTarget, ...] = (
    AssemblyTarget.ORCHESTRATION_EXECUTOR,
    AssemblyTarget.TOOL_WORKER,
)


def session_runtime_factories() -> tuple[ApplicationFactory, ...]:
    """Build session runtime ports from already assembled applications."""

    return (
        ApplicationFactory(
            key="session.workspace_lookup",
            provides=(AppKey.SESSION_WORKSPACE_LOOKUP,),
            requires=(AppKey.SESSION_SERVICE,),
            build=_build_session_workspace_lookup,
        ),
        ApplicationFactory(
            key="session.runtime_control",
            provides=(AppKey.SESSION_RUNTIME_CONTROL,),
            requires=(
                AppKey.ORCHESTRATION_RUN_QUERY_SERVICE,
                AppKey.ORCHESTRATION_SUBMISSION_SERVICE,
                AppKey.ORCHESTRATION_CANCELLATION_SERVICE,
            ),
            build=lambda ctx: SchedulerBackedSessionRuntimeControl(
                run_query_service=ctx.require(AppKey.ORCHESTRATION_RUN_QUERY_SERVICE),
                scheduler_service=ctx.require(AppKey.ORCHESTRATION_SUBMISSION_SERVICE),
                cancellation_service=ctx.require(
                    AppKey.ORCHESTRATION_CANCELLATION_SERVICE,
                ),
            ),
            targets=SESSION_RUNTIME_CONTROL_TARGETS,
        ),
        ApplicationFactory(
            key="session.ingress_runtime_control",
            provides=(AppKey.SESSION_RUNTIME_CONTROL,),
            requires=(
                AppKey.ORCHESTRATION_RUN_QUERY_SERVICE,
                AppKey.ORCHESTRATION_SUBMISSION_SERVICE,
                AppKey.ORCHESTRATION_INGRESS_PROCESSING_SERVICE,
                AppKey.ORCHESTRATION_CANCELLATION_SERVICE,
            ),
            build=_build_ingress_session_runtime_control,
            targets=INGRESS_SESSION_RUNTIME_CONTROL_TARGETS,
        ),
    )


def _build_session_workspace_lookup(ctx):
    session_service = ctx.require(AppKey.SESSION_SERVICE)

    def _session_workspace_lookup(session_key: str) -> str | None:
        try:
            session = session_service.get_session(session_key)
        except Exception:
            return None
        workspace = session.runtime_binding().workspace
        if workspace is None:
            return None
        normalized = workspace.strip()
        return normalized or None

    return _session_workspace_lookup


def _build_ingress_session_runtime_control(ctx) -> IngressBackedSessionRuntimeControl:
    return IngressBackedSessionRuntimeControl(
        run_query_service=ctx.require(AppKey.ORCHESTRATION_RUN_QUERY_SERVICE),
        submission_service=ctx.require(AppKey.ORCHESTRATION_SUBMISSION_SERVICE),
        ingress_processing_service=ctx.require(
            AppKey.ORCHESTRATION_INGRESS_PROCESSING_SERVICE,
        ),
        cancellation_service=ctx.require(AppKey.ORCHESTRATION_CANCELLATION_SERVICE),
    )


__all__ = [
    "session_runtime_factories",
]
