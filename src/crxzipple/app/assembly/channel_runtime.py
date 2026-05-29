"""Channel runtime app integrations."""

from __future__ import annotations

from typing import Any

from crxzipple.app.keys import AppKey
from crxzipple.app.plan import ActivationTask, ApplicationFactory, AssemblyTarget
from crxzipple.modules.channels import (
    LarkChannelRuntimeService,
    WebChannelRuntimeService,
    WebhookChannelRuntimeService,
)
from crxzipple.modules.events import EventsApplicationService
from crxzipple.modules.orchestration.application import turn_session_topic


def channel_runtime_factories() -> tuple[ApplicationFactory, ...]:
    """Build channel runtimes from Channels + Orchestration + Access ports."""

    return (
        ApplicationFactory(
            key="channels.runtime_services",
            provides=(
                AppKey.LARK_CHANNEL_RUNTIME_SERVICE,
                AppKey.WEB_CHANNEL_RUNTIME_SERVICE,
                AppKey.WEBHOOK_CHANNEL_RUNTIME_SERVICE,
            ),
            requires=(
                AppKey.CORE_SETTINGS,
                AppKey.CHANNEL_INFRASTRUCTURE,
                AppKey.AGENT_SERVICE,
                AppKey.ORCHESTRATION_SUBMISSION_SERVICE,
                AppKey.ORCHESTRATION_RUN_QUERY_SERVICE,
                AppKey.ARTIFACT_SERVICE,
                AppKey.EVENTS_SERVICE,
                AppKey.ACCESS_SERVICE,
            ),
            build=_build_channel_runtime_services,
            targets=(
                AssemblyTarget.API,
                AssemblyTarget.CHANNEL_RUNTIME,
                AssemblyTarget.TEST,
            ),
        ),
    )


def channel_runtime_activation_tasks() -> tuple[ActivationTask, ...]:
    return (
        ActivationTask(
            key="channels.bind_scheduler_run_enqueued_callback",
            requires=(
                AppKey.CHANNEL_INFRASTRUCTURE,
                AppKey.EVENTS_SERVICE,
                AppKey.ORCHESTRATION_RUN_ENQUEUED_CALLBACK_BINDING_SERVICE,
            ),
            run=_bind_scheduler_run_enqueued_callback,
            targets=(
                AssemblyTarget.API,
                AssemblyTarget.ORCHESTRATION_SCHEDULER,
                AssemblyTarget.TEST,
            ),
        ),
    )


def _build_channel_runtime_services(ctx) -> dict[str, Any]:
    infrastructure = ctx.require(AppKey.CHANNEL_INFRASTRUCTURE)
    events_service = ctx.require(AppKey.EVENTS_SERVICE)
    if not isinstance(events_service, EventsApplicationService):
        raise TypeError("channel runtimes require an EventsApplicationService")

    agent_service = ctx.require(AppKey.AGENT_SERVICE)
    submission_service = ctx.require(AppKey.ORCHESTRATION_SUBMISSION_SERVICE)
    run_query_service = ctx.require(AppKey.ORCHESTRATION_RUN_QUERY_SERVICE)
    access_service = ctx.require(AppKey.ACCESS_SERVICE)
    web_runtime = WebChannelRuntimeService(
        profile_service=infrastructure.profile_service,
        runtime_manager=infrastructure.runtime_manager,
        events_service=events_service,
        access_service=access_service,
    )
    webhook_runtime = WebhookChannelRuntimeService(
        agent_service=agent_service,
        orchestration_submission_port=submission_service,
        orchestration_run_lookup=run_query_service,
        interaction_service=infrastructure.interaction_service,
        profile_service=infrastructure.profile_service,
        runtime_manager=infrastructure.runtime_manager,
        events_service=events_service,
        access_service=access_service,
    )
    lark_runtime = LarkChannelRuntimeService(
        agent_service=agent_service,
        orchestration_submission_port=submission_service,
        orchestration_run_lookup=run_query_service,
        artifact_service=ctx.require(AppKey.ARTIFACT_SERVICE),
        interaction_service=infrastructure.interaction_service,
        profile_service=infrastructure.profile_service,
        runtime_manager=infrastructure.runtime_manager,
        events_service=events_service,
        access_service=access_service,
    )
    return {
        AppKey.LARK_CHANNEL_RUNTIME_SERVICE: lark_runtime,
        AppKey.WEB_CHANNEL_RUNTIME_SERVICE: web_runtime,
        AppKey.WEBHOOK_CHANNEL_RUNTIME_SERVICE: webhook_runtime,
    }


def _bind_scheduler_run_enqueued_callback(ctx) -> None:
    infrastructure = ctx.require(AppKey.CHANNEL_INFRASTRUCTURE)
    scheduler_service = ctx.require(
        AppKey.ORCHESTRATION_RUN_ENQUEUED_CALLBACK_BINDING_SERVICE,
    )
    scheduler_service.on_run_enqueued = _channel_run_binding_callback(
        interaction_service=infrastructure.interaction_service,
        events_service=ctx.require(AppKey.EVENTS_SERVICE),
    )


def _channel_run_binding_callback(*, interaction_service, events_service):
    def _bind_channel_interactions_to_run(run) -> None:
        session_key = (
            run.session_key.strip()
            if isinstance(run.session_key, str) and run.session_key.strip()
            else None
        )
        metadata: dict[str, object] = {
            "active_session_id": run.active_session_id,
        }
        if session_key is not None:
            metadata["observe_cursor"] = events_service.snapshot_event_topic(
                turn_session_topic(session_key),
            )
        interaction_service.bind_run_by_run_id(
            run.id,
            session_key=session_key,
            agent_id=run.agent_id,
            status=run.status.value,
            metadata=metadata,
        )

    return _bind_channel_interactions_to_run


__all__ = ["channel_runtime_activation_tasks", "channel_runtime_factories"]
