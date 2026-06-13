"""Event-driven runtime sidecar app assembly."""

from __future__ import annotations

from crxzipple.app.keys import AppKey
from crxzipple.app.plan import ApplicationFactory, AssemblyTarget
from crxzipple.modules.dispatch.application import DispatchWakeupObserver
from crxzipple.modules.event_relay import (
    EventRelayRuntimeService,
    WorkbenchEventRelayObserver,
)
from crxzipple.modules.events import EventsApplicationService
from crxzipple.modules.operations.application.observation import (
    OperationsEventObserver,
    observed_event_from_record,
)
from crxzipple.modules.operations.application.projections import (
    OPERATIONS_PROJECTION_MODULES,
)
from crxzipple.modules.operations.application.runtime import (
    OperationsObserverRuntimeService,
    operations_observer_event_names,
)
from crxzipple.modules.orchestration.application import (
    OrchestrationDispatchRecoveryReaction,
    OrchestrationRuntimeEventService,
    OrchestrationToolTerminalReaction,
    RUN_OBSERVATION_EVENT_NAMES,
    RunObservationObserver,
    TOOL_OBSERVATION_SOURCE_EVENT_NAMES,
    ToolRunObservationObserver,
)
from crxzipple.modules.tool.application import (
    ToolDispatchEventSubscriber,
    ToolRuntimeEventService,
)
from crxzipple.shared import ORCHESTRATION_RUN_LLM_TEXT_DELTA_EVENT

OPERATIONS_STATE_PROJECTION_MODULES: tuple[str, ...] = OPERATIONS_PROJECTION_MODULES
OPERATIONS_STATE_PROJECTION_INTERVAL_SECONDS = 300.0
OPERATIONS_EVENT_PROJECTION_DEBOUNCE_SECONDS = 1.0
OPERATIONS_EVENT_PROJECTION_MIN_INTERVAL_SECONDS: dict[str, float] = {
    "orchestration": 10.0,
    "tool": 15.0,
    "browser": 10.0,
    "llm": 15.0,
    "access": 10.0,
    "channels": 10.0,
    "memory": 15.0,
    "skills": 10.0,
    "events": 15.0,
    "daemon": 10.0,
}


def event_runtime_factories() -> tuple[ApplicationFactory, ...]:
    """Build event consumers for scheduler wakeups, relay and operations."""

    return (
        ApplicationFactory(
            key="orchestration.scheduler_runtime_event_service",
            provides=(AppKey.ORCHESTRATION_SCHEDULER_RUNTIME_EVENT_SERVICE,),
            requires=(
                AppKey.EVENTS_SERVICE,
                AppKey.TOOL_QUERY_SERVICE,
                AppKey.ORCHESTRATION_SCHEDULER_SERVICE,
            ),
            build=_build_orchestration_scheduler_runtime_event_service,
            targets=(AssemblyTarget.ORCHESTRATION_SCHEDULER, AssemblyTarget.TEST),
        ),
        ApplicationFactory(
            key="event_relay.runtime_event_service",
            provides=(AppKey.EVENT_RELAY_RUNTIME_EVENT_SERVICE,),
            requires=(
                AppKey.EVENTS_SERVICE,
                AppKey.TOOL_QUERY_SERVICE,
                AppKey.ORCHESTRATION_RUN_QUERY_SERVICE,
            ),
            build=_build_event_relay_runtime_event_service,
            targets=(AssemblyTarget.EVENT_RELAY_WORKER, AssemblyTarget.TEST),
        ),
        ApplicationFactory(
            key="tool.runtime_event_service",
            provides=(AppKey.TOOL_RUNTIME_EVENT_SERVICE,),
            requires=(AppKey.EVENTS_SERVICE, AppKey.TOOL_WORKER_SERVICE),
            build=_build_tool_runtime_event_service,
            targets=(AssemblyTarget.TOOL_WORKER, AssemblyTarget.TEST),
        ),
        ApplicationFactory(
            key="operations.observer_runtime_event_service",
            provides=(AppKey.OPERATIONS_OBSERVER_RUNTIME_EVENT_SERVICE,),
            requires=(
                AppKey.EVENTS_SERVICE,
                AppKey.OPERATIONS_OBSERVATION_STORE,
                AppKey.EVENT_DEFINITION_REGISTRY,
                AppKey.OPERATIONS_PROJECTION_MATERIALIZER,
            ),
            build=_build_operations_observer_runtime_event_service,
            targets=(AssemblyTarget.OPERATIONS_OBSERVER, AssemblyTarget.TEST),
        ),
    )


def _build_orchestration_scheduler_runtime_event_service(ctx):
    events_service = ctx.require(AppKey.EVENTS_SERVICE)
    if not isinstance(events_service, EventsApplicationService):
        return None
    scheduler_service = ctx.require(AppKey.ORCHESTRATION_SCHEDULER_SERVICE)
    runtime = OrchestrationRuntimeEventService(
        events_service=events_service,
        runtime_name="orchestration.scheduler-runtime",
    )
    wake_observer = DispatchWakeupObserver(events_service=events_service)
    tool_terminal_reaction = OrchestrationToolTerminalReaction(
        scheduler_service=scheduler_service,
        tool_run_lookup=ctx.require(AppKey.TOOL_QUERY_SERVICE).get_tool_run,
    )
    dispatch_recovery_reaction = OrchestrationDispatchRecoveryReaction(
        scheduler_service=scheduler_service,
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
        handler=dispatch_recovery_reaction.react_to_recovered_dispatch_task,
    )
    scheduler_service.runtime_event_service = runtime
    return runtime


def _build_event_relay_runtime_event_service(ctx):
    events_service = ctx.require(AppKey.EVENTS_SERVICE)
    if not isinstance(events_service, EventsApplicationService):
        return None
    runtime = EventRelayRuntimeService(
        events_service=events_service,
        runtime_name="event_relay.runtime",
    )
    run_query = ctx.require(AppKey.ORCHESTRATION_RUN_QUERY_SERVICE)
    tool_service = ctx.require(AppKey.TOOL_QUERY_SERVICE)
    workbench_observer = WorkbenchEventRelayObserver(
        events_service=events_service,
        run_lookup=run_query,
        tool_execution_port=tool_service,
    )
    turn_session_run_observer = RunObservationObserver(
        events_service=events_service,
        run_lookup=run_query,
    )
    turn_session_tool_observer = ToolRunObservationObserver(
        events_service=events_service,
        run_lookup=run_query,
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
        "session.item.appended",
        subscription_id="event_relay.workbench.session-item",
        handler=workbench_observer.observe_session_item_event,
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


def _build_tool_runtime_event_service(ctx):
    events_service = ctx.require(AppKey.EVENTS_SERVICE)
    if not isinstance(events_service, EventsApplicationService):
        return None
    return ToolRuntimeEventService(
        events_service=events_service,
        dispatch_subscriber=ToolDispatchEventSubscriber(
            service=ctx.require(AppKey.TOOL_WORKER_SERVICE),
        ),
    )


def _build_operations_observer_runtime_event_service(ctx):
    events_service = ctx.require(AppKey.EVENTS_SERVICE)
    if not isinstance(events_service, EventsApplicationService):
        return None
    observation_store = ctx.require(AppKey.OPERATIONS_OBSERVATION_STORE)
    definition_registry = ctx.require(AppKey.EVENT_DEFINITION_REGISTRY)
    projection_materializer = ctx.require(AppKey.OPERATIONS_PROJECTION_MATERIALIZER)
    observer = OperationsEventObserver(
        observation_store=observation_store,
        definition_registry=definition_registry,
    )

    pending_projection_modules: set[str] = set()
    next_projection_at: float | None = None
    last_projection_at_by_module: dict[str, float] = {}
    import time

    next_state_projection_at = time.monotonic() + OPERATIONS_STATE_PROJECTION_INTERVAL_SECONDS

    def _flush_due_projection() -> None:
        nonlocal next_projection_at, next_state_projection_at

        now = time.monotonic()
        if next_projection_at is not None and now >= next_projection_at:
            due_modules: list[str] = []
            next_due_at: float | None = None
            for module in sorted(pending_projection_modules):
                min_interval = OPERATIONS_EVENT_PROJECTION_MIN_INTERVAL_SECONDS.get(
                    module,
                    10.0,
                )
                last_projected_at = last_projection_at_by_module.get(module, 0.0)
                due_at = last_projected_at + min_interval
                if now >= due_at:
                    due_modules.append(module)
                elif next_due_at is None or due_at < next_due_at:
                    next_due_at = due_at
            for module in due_modules:
                pending_projection_modules.discard(module)
            next_projection_at = next_due_at if pending_projection_modules else None
            modules = tuple(due_modules)
            if modules:
                projection_materializer.materialize_observed_modules(modules)
                projected_at = time.monotonic()
                for module in modules:
                    last_projection_at_by_module[module] = projected_at
        if now >= next_state_projection_at:
            projection_materializer.materialize_modules(OPERATIONS_STATE_PROJECTION_MODULES)
            projected_at = time.monotonic()
            for module in OPERATIONS_STATE_PROJECTION_MODULES:
                last_projection_at_by_module[module] = projected_at
            next_state_projection_at = projected_at + OPERATIONS_STATE_PROJECTION_INTERVAL_SECONDS

    def _schedule_projection(records) -> None:  # noqa: ANN001
        nonlocal next_projection_at

        pending_projection_modules.update(
            observed_event_from_record(
                record,
                definition_registry=definition_registry,
            ).module
            for record in records
        )
        if pending_projection_modules and next_projection_at is None:
            next_projection_at = time.monotonic() + OPERATIONS_EVENT_PROJECTION_DEBOUNCE_SECONDS
        _flush_due_projection()

    def _observe_event_records(records) -> None:  # noqa: ANN001
        observer.observe_event_records(records)
        _schedule_projection(records)

    runtime = OperationsObserverRuntimeService(
        events_service=events_service,
        runtime_name="operations.observer",
        heartbeat_handler=observation_store.record_observer_heartbeat,
        maintenance_handler=_flush_due_projection,
        start_at_tail_when_no_cursor=True,
    )
    for event_name in operations_observer_event_names(definition_registry):
        runtime.subscribe_event_name(
            event_name,
            subscription_id=f"operations.observer.{event_name}",
            handler=observer.observe_event_record,
            batch_handler=_observe_event_records,
        )
    if ctx.has(AppKey.OPERATIONS_SOURCE_READ_MODEL_CONTEXT):
        ctx.require(AppKey.OPERATIONS_SOURCE_READ_MODEL_CONTEXT).attach_operations_observer_runtime(
            runtime,
        )
    return runtime


__all__ = ["event_runtime_factories"]
