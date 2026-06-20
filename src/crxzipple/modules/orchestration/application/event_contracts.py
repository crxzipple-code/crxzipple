from __future__ import annotations

from crxzipple.modules.events import EventTopicContract
from crxzipple.modules.orchestration.application.observers import (
    RUN_OBSERVATION_EVENT_NAMES,
    TOOL_OBSERVATION_SOURCE_EVENT_NAMES,
    orchestration_runtime_observation_topic,
    turn_session_live_topic,
    turn_session_topic,
)
from crxzipple.shared import (
    EventDefinition,
    EventDefinitionField,
    EventObserver,
    EventSurface,
    ORCHESTRATION_RUN_LLM_TEXT_DELTA_EVENT,
    ORCHESTRATION_RUN_TOOL_UPDATED_EVENT,
    ORCHESTRATION_RUNTIME_OBSERVATION_SOURCE_EVENT_NAMES,
    ORCHESTRATION_RUNTIME_STATUS_EVENT,
)
from crxzipple.shared.domain.events import named_event_topic

ORCHESTRATION_ORPHAN_TOOL_RESULT_OBSERVED_EVENT = (
    "orchestration.execution.orphan_tool_result_observed"
)
ORCHESTRATION_LLM_STEP_COMPLETED_EVENT = "orchestration.execution.llm_step_completed"

_OPERATION_DISPLAY_FIELDS: tuple[EventDefinitionField, ...] = (
    EventDefinitionField("level", "Operational severity level for display.", "string"),
    EventDefinitionField("summary", "Display-safe event summary.", "string"),
    EventDefinitionField("display_label", "Short display label for operations views.", "string"),
    EventDefinitionField("display_summary", "Human-readable operations summary.", "string"),
    EventDefinitionField("display_tone", "Display tone such as info, success, warning, or danger.", "string"),
    EventDefinitionField("entity_type", "Linked entity type for navigation or filtering.", "string"),
    EventDefinitionField("entity_id", "Linked entity identifier for navigation or filtering.", "string"),
)

_RUN_OPERATIONAL_EVENT_NAMES: tuple[str, ...] = (
    "orchestration.run.accepted",
    "orchestration.run.routed",
    "orchestration.run.bulk_ready",
    "orchestration.run.heartbeated",
)

_INGRESS_OPERATIONAL_EVENT_NAMES: tuple[str, ...] = (
    "orchestration.ingress.requested",
    "orchestration.ingress.claimed",
    "orchestration.ingress.completed",
    "orchestration.ingress.failed",
)

_EXECUTOR_OPERATIONAL_EVENT_NAMES: tuple[str, ...] = (
    "orchestration.executor.assignment.requested",
    "orchestration.executor.lease.registered",
    "orchestration.executor.lease.heartbeated",
    "orchestration.executor.lease.assignment_claimed",
    "orchestration.executor.lease.assignment_released",
    "orchestration.executor.lease.offline",
)

_EXECUTION_OPERATIONAL_EVENT_NAMES: tuple[str, ...] = (
    ORCHESTRATION_LLM_STEP_COMPLETED_EVENT,
    ORCHESTRATION_ORPHAN_TOOL_RESULT_OBSERVED_EVENT,
)

_RUN_OPERATIONAL_FIELDS: tuple[EventDefinitionField, ...] = (
    EventDefinitionField("event_name", "Stable orchestration run event name.", "string", True),
    EventDefinitionField("run_id", "Owning orchestration run identifier.", "string", True),
    EventDefinitionField("status", "Current run status.", "string", True),
    EventDefinitionField("stage", "Current orchestration stage.", "string", True),
    EventDefinitionField("current_step", "Current step counter for the run.", "integer", True),
    EventDefinitionField("source", "Ingress source that accepted the run.", "string"),
    EventDefinitionField("agent_id", "Agent profile selected for the run.", "string"),
    EventDefinitionField("session_key", "Resolved session key for the run.", "string"),
    EventDefinitionField("active_session_id", "Active session instance identifier.", "string"),
    EventDefinitionField("worker_id", "Worker currently claiming the run.", "string"),
    EventDefinitionField("lane_key", "Scheduler lane key.", "string"),
    EventDefinitionField("lane_lock_key", "Lane lock held by the worker.", "string"),
    EventDefinitionField("priority", "Scheduler priority.", "integer"),
    *_OPERATION_DISPLAY_FIELDS,
)

_INGRESS_OPERATIONAL_FIELDS: tuple[EventDefinitionField, ...] = (
    EventDefinitionField("event_name", "Stable orchestration ingress event name.", "string", True),
    EventDefinitionField("request_id", "Ingress request identifier.", "string", True),
    EventDefinitionField("run_id", "Owning orchestration run identifier.", "string"),
    EventDefinitionField("kind", "Ingress request kind.", "string", True),
    EventDefinitionField("status", "Ingress request status.", "string", True),
    EventDefinitionField("worker_id", "Scheduler worker processing the request.", "string"),
    EventDefinitionField("source", "External source or bound-turn source.", "string"),
    EventDefinitionField("target_lane", "Requested scheduler lane or target session.", "string"),
    EventDefinitionField("priority", "Scheduler priority.", "integer"),
    EventDefinitionField("queue_policy", "Queue policy selected for the run.", "string"),
    EventDefinitionField("requested_llm_id", "Requested LLM profile id or auto route.", "string"),
    EventDefinitionField("code", "Failure code for failed ingress requests.", "string"),
    EventDefinitionField("message", "Failure message for failed ingress requests.", "string"),
    EventDefinitionField("details", "Failure details for failed ingress requests.", "object"),
    *_OPERATION_DISPLAY_FIELDS,
)

_EXECUTOR_OPERATIONAL_FIELDS: tuple[EventDefinitionField, ...] = (
    EventDefinitionField("event_name", "Stable orchestration executor event name.", "string", True),
    EventDefinitionField("run_id", "Assigned orchestration run identifier.", "string"),
    EventDefinitionField("worker_id", "Executor worker identifier.", "string", True),
    EventDefinitionField("status", "Executor lease status.", "string"),
    EventDefinitionField("lane_key", "Scheduler lane key for the requested assignment.", "string"),
    EventDefinitionField("max_inflight_assignments", "Configured executor assignment capacity.", "integer"),
    EventDefinitionField("inflight_assignment_count", "Current claimed assignment count.", "integer"),
    EventDefinitionField("available_assignment_slots", "Available assignment slots after the event.", "integer"),
    EventDefinitionField("active_run_ids", "Run ids currently reported as active by the executor.", "array"),
    EventDefinitionField("last_heartbeat_at", "Most recent executor heartbeat timestamp.", "string"),
    EventDefinitionField("lease_expires_at", "Executor lease expiration timestamp.", "string"),
    *_OPERATION_DISPLAY_FIELDS,
)

_EXECUTION_OPERATIONAL_FIELDS: tuple[EventDefinitionField, ...] = (
    EventDefinitionField("event_name", "Stable orchestration execution event name.", "string", True),
    EventDefinitionField("status", "Observed execution consistency status.", "string", True),
    EventDefinitionField("tool_run_id", "Terminal tool run identifier.", "string", True),
    EventDefinitionField("run_id", "Owning orchestration run id from tool metadata, when available.", "string"),
    EventDefinitionField("orchestration_run_id", "Owning orchestration run id from tool metadata, when available.", "string"),
    EventDefinitionField("tool_status", "Terminal tool lifecycle status.", "string"),
    EventDefinitionField("tool_id", "Tool identifier.", "string"),
    EventDefinitionField("function_id", "Tool function identifier.", "string"),
    EventDefinitionField("source_id", "Tool source identifier.", "string"),
    EventDefinitionField("mode", "Tool execution mode.", "string"),
    EventDefinitionField("strategy", "Tool execution strategy.", "string"),
    EventDefinitionField("environment", "Tool execution environment.", "string"),
    EventDefinitionField("reason", "Reason the terminal result could not be merged into the execution chain.", "string", True),
    EventDefinitionField("error_message", "Terminal tool error message when available.", "string"),
    *_OPERATION_DISPLAY_FIELDS,
)

_LLM_STEP_COMPLETED_FIELDS: tuple[EventDefinitionField, ...] = (
    EventDefinitionField("event_name", "Stable orchestration execution event name.", "string", True),
    EventDefinitionField("run_id", "Owning orchestration run identifier.", "string", True),
    EventDefinitionField("session_key", "Resolved session key for the run.", "string"),
    EventDefinitionField("active_session_id", "Active session instance identifier.", "string"),
    EventDefinitionField("status", "Current run status before reduction.", "string", True),
    EventDefinitionField("stage", "Current orchestration stage before reduction.", "string", True),
    EventDefinitionField("current_step", "Current step counter for the run.", "integer", True),
    EventDefinitionField("llm_invocation_id", "LLM invocation completed for this execution step.", "string", True),
    EventDefinitionField("request_render_snapshot_id", "Request render snapshot used for this LLM invocation.", "string"),
    EventDefinitionField("llm_response_item_ids", "LLM response item ids emitted by this invocation.", "array"),
    EventDefinitionField("session_item_ids", "Session item ids persisted for this invocation.", "array"),
    EventDefinitionField("assistant_progress_item_ids", "Assistant progress session item ids.", "array"),
    EventDefinitionField("tool_call_session_item_ids", "Assistant function_call session item ids.", "array"),
    EventDefinitionField("tool_result_session_item_ids", "Tool result session item ids recorded during this outcome.", "array"),
    EventDefinitionField("tool_call_names", "Tool call names requested by the model.", "array"),
    EventDefinitionField("text_present", "Whether the LLM result included assistant text.", "boolean"),
    EventDefinitionField("text_chars", "Character count of the LLM result text.", "integer"),
)

_ORCHESTRATION_OPERATIONAL_EVENT_DESCRIPTIONS: dict[str, str] = {
    "orchestration.run.accepted": "Run intake accepted an orchestration run.",
    "orchestration.run.routed": "Run routing selected agent, lane, and priority metadata.",
    "orchestration.run.bulk_ready": "Run was bound to durable session state and is ready to queue.",
    "orchestration.run.heartbeated": "Executor heartbeat refreshed a running orchestration run.",
    "orchestration.ingress.requested": "Scheduler ingress request was queued for run preparation.",
    "orchestration.ingress.claimed": "Scheduler worker claimed an ingress request.",
    "orchestration.ingress.completed": "Scheduler ingress request completed successfully.",
    "orchestration.ingress.failed": "Scheduler ingress request failed.",
    "orchestration.executor.assignment.requested": "Scheduler requested executor processing for a run.",
    "orchestration.executor.lease.registered": "Executor registered or refreshed its capacity lease.",
    "orchestration.executor.lease.heartbeated": "Executor lease heartbeat refreshed capacity and activity.",
    "orchestration.executor.lease.assignment_claimed": "Executor lease claimed assignment capacity.",
    "orchestration.executor.lease.assignment_released": "Executor lease released assignment capacity.",
    "orchestration.executor.lease.offline": "Executor lease was marked offline.",
    ORCHESTRATION_LLM_STEP_COMPLETED_EVENT: (
        "LLM execution outcome was reduced into assistant progress and tool-call session facts."
    ),
    ORCHESTRATION_ORPHAN_TOOL_RESULT_OBSERVED_EVENT: (
        "Terminal orchestration-owned tool run could not be matched to an execution step item."
    ),
}


def _direct_operational_definition(
    *,
    event_name: str,
    producers: tuple[str, ...],
    fields: tuple[EventDefinitionField, ...],
    notes: tuple[str, ...] = (),
) -> EventDefinition:
    return EventDefinition(
        definition_id=event_name,
        owner="orchestration",
        event_name=event_name,
        description=_ORCHESTRATION_OPERATIONAL_EVENT_DESCRIPTIONS[event_name],
        topics=(named_event_topic(event_name),),
        producers=producers,
        consumers=("operations observer", "trace read model", "diagnostics"),
        fields=fields,
        durability="persistent",
        publication_mode="direct",
        notes=notes,
    )


def orchestration_event_topic_contracts() -> tuple[EventTopicContract, ...]:
    return (
        EventTopicContract(
            contract_id="turn.session",
            topic_pattern=turn_session_topic("{session_key}"),
            owner="orchestration",
            description="Session scoped durable run facts.",
            kinds=("fact",),
            producers=("RunObservationObserver.observe_run_event",),
            consumers=("WebChannel SSE /channels/web/events",),
            ordering="session_key | run_id",
            notes=("source topic for web observation",),
        ),
        EventTopicContract(
            contract_id="turn.live.session",
            topic_pattern=turn_session_live_topic("{session_key}"),
            owner="orchestration",
            description=(
                "Session scoped live orchestration deltas, especially LLM text "
                "stream updates."
            ),
            kinds=("live",),
            producers=("RunExecutionService.publish_llm_stream_update",),
            consumers=("WebChannel SSE /channels/web/events",),
            ordering="run_id",
            notes=("source topic for direct web live streaming",),
        ),
        EventTopicContract(
            contract_id="orchestration.runtime_observation",
            topic_pattern=orchestration_runtime_observation_topic(),
            owner="orchestration",
            description=(
                "Runtime health snapshots for orchestration scheduling and "
                "execution capacity."
            ),
            kinds=("fact",),
            producers=("RuntimeObservationObserver.observe_runtime_event",),
            consumers=("web console", "diagnostics", "daemon monitors"),
            ordering="orchestration.runtime",
            notes=(
                "Derived from run state changes and executor lease events.",
                "This is a scheduler/runtime health surface, not a run lifecycle surface.",
            ),
        ),
        EventTopicContract(
            contract_id="orchestration.llm_resolution",
            topic_pattern=named_event_topic("orchestration.llm_resolved"),
            owner="orchestration",
            description=(
                "Runtime request LLM routing decisions observed for operations "
                "and diagnostics."
            ),
            kinds=("observe",),
            producers=("RuntimeLlmRequestDraftCollector._publish_llm_resolution_event",),
            consumers=("operations observer", "diagnostics"),
            ordering="run_id",
            notes=(
                "Records both successful model selection and resolver failures.",
            ),
        ),
    )


def orchestration_event_definitions() -> tuple[EventDefinition, ...]:
    run_fields = (
        EventDefinitionField("event_name", "Stable orchestration event name.", "string", True),
        EventDefinitionField("run_id", "Owning orchestration run identifier.", "string", True),
        EventDefinitionField("session_key", "Resolved session key for the run.", "string"),
        EventDefinitionField("active_session_id", "Active session instance identifier.", "string"),
        EventDefinitionField("status", "Current run status after reduction.", "string", True),
        EventDefinitionField("stage", "Current orchestration stage.", "string", True),
        EventDefinitionField("current_step", "Current step counter for the run.", "integer", True),
        EventDefinitionField("waiting_reason", "Structured waiting reason when present.", "string"),
        EventDefinitionField("pending_tool_run_ids", "Background tool run ids still pending.", "array"),
        EventDefinitionField("pending_approval_request", "Approval request payload when awaiting approval.", "object"),
        EventDefinitionField("last_approval_resolution", "Most recent approval resolution payload.", "object"),
    )
    definitions = [
        EventDefinition(
            definition_id=event_name,
            owner="orchestration",
            event_name=event_name,
            description="Reduced orchestration run fact published for session-scoped observers.",
            topics=("turn.session.{session_key}",),
            producers=("RunObservationObserver.observe_run_event",),
            consumers=("channel runtimes", "web console", "diagnostics"),
            fields=run_fields,
            durability="persistent",
            publication_mode="reduced",
            source_event_names=(event_name,),
            notes=("payload is reduced from the latest durable run state",),
        )
        for event_name in RUN_OBSERVATION_EVENT_NAMES
    ]
    definitions.extend(
        _direct_operational_definition(
            event_name=event_name,
            producers=("OrchestrationRun", "OrchestrationExecutorService"),
            fields=_RUN_OPERATIONAL_FIELDS,
            notes=(
                "These are orchestration-owned source facts consumed directly by Operations.",
                "Session-scoped run observation remains the reduced consumer surface for channel runtimes.",
            ),
        )
        for event_name in _RUN_OPERATIONAL_EVENT_NAMES
    )
    definitions.extend(
        _direct_operational_definition(
            event_name=event_name,
            producers=("OrchestrationIngressRequest", "RunIngressCoordinator"),
            fields=_INGRESS_OPERATIONAL_FIELDS,
            notes=(
                "Ingress facts describe scheduler intake and preparation state.",
            ),
        )
        for event_name in _INGRESS_OPERATIONAL_EVENT_NAMES
    )
    definitions.extend(
        _direct_operational_definition(
            event_name=event_name,
            producers=("OrchestrationSchedulerService", "OrchestrationExecutorLease"),
            fields=_EXECUTOR_OPERATIONAL_FIELDS,
            notes=(
                "Executor assignment and lease facts describe capacity, not tool or LLM ownership.",
            ),
        )
        for event_name in _EXECUTOR_OPERATIONAL_EVENT_NAMES
    )
    definitions.append(
        _direct_operational_definition(
            event_name=ORCHESTRATION_LLM_STEP_COMPLETED_EVENT,
            producers=("RunExecutionService._publish_llm_step_completed_event",),
            fields=_LLM_STEP_COMPLETED_FIELDS,
            notes=(
                "Diagnostic execution fact for Trace and Operations.",
                "Payload contains ids only, not full assistant progress text.",
            ),
        )
    )
    definitions.append(
        _direct_operational_definition(
            event_name=ORCHESTRATION_ORPHAN_TOOL_RESULT_OBSERVED_EVENT,
            producers=("OrchestrationToolResumeCoordinator",),
            fields=_EXECUTION_OPERATIONAL_FIELDS,
            notes=(
                "This fact is emitted only for orchestration-owned tool runs whose terminal result cannot be merged into the execution chain.",
                "Consumers should treat it as an execution-chain consistency warning, not as tool ownership.",
            ),
        )
    )
    definitions.append(
        EventDefinition(
            definition_id=ORCHESTRATION_RUN_LLM_TEXT_DELTA_EVENT,
            owner="orchestration",
            event_name=ORCHESTRATION_RUN_LLM_TEXT_DELTA_EVENT,
            description="Live incremental model text update emitted while a run is streaming.",
            topics=(
                "turn.live.session.{session_key}",
                named_event_topic(ORCHESTRATION_RUN_LLM_TEXT_DELTA_EVENT),
            ),
            producers=("RunExecutionService.publish_llm_stream_update",),
            consumers=("channel runtimes", "web console"),
            fields=(
                EventDefinitionField("event_name", "Stable orchestration live event name.", "string", True),
                EventDefinitionField("run_id", "Owning orchestration run identifier.", "string", True),
                EventDefinitionField("session_key", "Resolved session key for the run.", "string", True),
                EventDefinitionField("active_session_id", "Active session instance identifier.", "string"),
                EventDefinitionField("status", "Current run status while streaming.", "string", True),
                EventDefinitionField("stage", "Current orchestration stage.", "string", True),
                EventDefinitionField("current_step", "Current step counter for the run.", "integer", True),
                EventDefinitionField("invocation_id", "Stable model invocation identifier for this stream.", "string", True),
                EventDefinitionField("text_delta", "Incremental text delta, if supplied by the model adapter.", "string"),
                EventDefinitionField("text", "Full accumulated text for the current invocation.", "string", True),
                EventDefinitionField("text_length", "Character count of the accumulated text.", "integer", True),
            ),
            durability="transient",
            publication_mode="direct",
            notes=("transient event intended for low-latency observation consumers",),
        )
    )
    definitions.append(
        EventDefinition(
            definition_id="orchestration.llm_resolved",
            owner="orchestration",
            event_name="orchestration.llm_resolved",
            description="Runtime request LLM routing decision observed for operations.",
            topics=(named_event_topic("orchestration.llm_resolved"),),
            producers=("RuntimeLlmRequestDraftCollector._publish_llm_resolution_event",),
            consumers=("operations observer", "diagnostics"),
            fields=(
                EventDefinitionField("event_name", "Stable event name.", "string", True),
                EventDefinitionField("status", "Resolution status.", "string", True),
                EventDefinitionField("run_id", "Owning orchestration run identifier.", "string", True),
                EventDefinitionField("agent_id", "Agent profile used for routing.", "string"),
                EventDefinitionField("session_key", "Resolved session key for the run.", "string"),
                EventDefinitionField("active_session_id", "Active session instance identifier.", "string"),
                EventDefinitionField("requested_llm_id", "Requested LLM profile id or auto route.", "string", True),
                EventDefinitionField("resolved_llm_id", "Selected LLM profile id when resolved.", "string"),
                EventDefinitionField("strategy", "Routing strategy.", "string", True),
                EventDefinitionField("routing_input_block_count", "Number of content blocks provided to auto LLM routing.", "integer"),
                EventDefinitionField("session_replay_window", "Replay window metadata used to build routing input.", "object"),
                EventDefinitionField("input_has_image", "Whether routing saw image input.", "boolean", True),
                EventDefinitionField("input_has_file", "Whether routing saw file input.", "boolean", True),
                EventDefinitionField("provider", "Selected provider when resolved.", "string"),
                EventDefinitionField("api_family", "Selected provider API family.", "string"),
                EventDefinitionField("model_name", "Selected model name.", "string"),
                EventDefinitionField("model_family", "Selected model family.", "string"),
                EventDefinitionField("context_window_tokens", "Selected model context window.", "integer"),
                EventDefinitionField("capabilities", "Selected model capabilities.", "array"),
                EventDefinitionField("reason", "Failure or fallback reason when available.", "string"),
            ),
            durability="persistent",
            publication_mode="direct",
        )
    )
    definitions.append(
        EventDefinition(
            definition_id=ORCHESTRATION_RUN_TOOL_UPDATED_EVENT,
            owner="orchestration",
            event_name=ORCHESTRATION_RUN_TOOL_UPDATED_EVENT,
            description="Run-scoped tool lifecycle fact translated from tool module source events.",
            topics=("turn.session.{session_key}",),
            producers=("ToolRunObservationObserver.observe_tool_event",),
            consumers=("channel runtimes", "web console", "diagnostics"),
            fields=(
                EventDefinitionField("event_name", "Stable orchestration tool observation event name.", "string", True),
                EventDefinitionField("source_event_name", "Original tool lifecycle event name.", "string", True),
                EventDefinitionField("run_id", "Owning orchestration run identifier.", "string", True),
                EventDefinitionField("session_key", "Resolved session key for the owning run.", "string", True),
                EventDefinitionField("active_session_id", "Active session instance identifier when available.", "string"),
                EventDefinitionField("tool_run_id", "Tool run identifier.", "string", True),
                EventDefinitionField("tool_id", "Tool identifier.", "string", True),
                EventDefinitionField("tool_name", "Display-safe tool label, currently derived from tool id.", "string", True),
                EventDefinitionField("tool_status", "Current tool run status.", "string", True),
                EventDefinitionField("tool_mode", "Tool execution mode.", "string", True),
                EventDefinitionField("tool_strategy", "Tool execution strategy.", "string", True),
                EventDefinitionField("tool_environment", "Tool execution environment.", "string", True),
                EventDefinitionField("attempt_count", "Current tool attempt counter.", "integer", True),
                EventDefinitionField("max_attempts", "Configured maximum retry attempts.", "integer", True),
                EventDefinitionField("output_payload", "Tool result summary when available.", "object"),
                EventDefinitionField("error_message", "Tool error summary when available.", "string"),
                EventDefinitionField("created_at", "Tool run creation time.", "string", True),
                EventDefinitionField("started_at", "Tool run start time when available.", "string"),
                EventDefinitionField("completed_at", "Tool run completion time when available.", "string"),
            ),
            durability="persistent",
            publication_mode="translated",
            source_event_names=TOOL_OBSERVATION_SOURCE_EVENT_NAMES,
            notes=(
                "tool module owns source lifecycle events and orchestration translates them into run-scoped observation facts",
                "consumers should use tool_status rather than inferring tool lifecycle from appended messages",
            ),
        )
    )
    definitions.append(
        EventDefinition(
            definition_id=ORCHESTRATION_RUNTIME_STATUS_EVENT,
            owner="orchestration",
            event_name=ORCHESTRATION_RUNTIME_STATUS_EVENT,
            description=(
                "Hydrated orchestration runtime health snapshot for scheduler "
                "queue, lane pressure, executor capacity, and LLM limiter metrics."
            ),
            topics=(orchestration_runtime_observation_topic(),),
            producers=("RuntimeObservationObserver.observe_runtime_event",),
            consumers=("web console", "diagnostics", "daemon monitors"),
            fields=(
                EventDefinitionField("event_name", "Stable runtime observation event name.", "string", True),
                EventDefinitionField("source_event_name", "Source event that triggered this snapshot.", "string", True),
                EventDefinitionField("source_event_id", "Source event id that triggered this snapshot.", "string", True),
                EventDefinitionField("observed_at", "Snapshot observation timestamp.", "string", True),
                EventDefinitionField("queue", "Scheduler queue health summary.", "object", True),
                EventDefinitionField("queue.queued_run_count", "Queued run count.", "integer", True),
                EventDefinitionField("queue.running_run_count", "Running run count.", "integer", True),
                EventDefinitionField("queue.waiting_run_count", "Waiting run count.", "integer", True),
                EventDefinitionField("lanes", "Lane pressure and blocked-lane summary.", "object", True),
                EventDefinitionField("executor", "Executor lease and assignment capacity summary.", "object", True),
                EventDefinitionField("executor.lease_count", "Total executor lease records retained in orchestration state.", "integer", True),
                EventDefinitionField("executor.visible_lease_count", "Non-expired executor lease records included in snapshot details.", "integer", True),
                EventDefinitionField("executor.expired_lease_count", "Expired executor lease records omitted from snapshot details.", "integer", True),
                EventDefinitionField("executor.capacity_executor_count", "Online, non-expired executor count.", "integer", True),
                EventDefinitionField("executor.total_available_assignment_slots", "Available assignment slots across online, non-expired executors.", "integer", True),
                EventDefinitionField("llm", "LLM runtime limiter metrics from executor leases.", "object", True),
            ),
            durability="persistent",
            publication_mode="hydrated",
            source_event_names=ORCHESTRATION_RUNTIME_OBSERVATION_SOURCE_EVENT_NAMES,
            notes=(
                "Consumers should use this surface for runtime health and capacity dashboards.",
                "Run lifecycle consumers should stay on orchestration.observation.",
            ),
        )
    )
    return tuple(definitions)


def orchestration_event_surfaces() -> tuple[EventSurface, ...]:
    return (
        EventSurface(
            surface_id="orchestration.observation",
            owner="orchestration",
            description=(
                "Unified orchestration observation surface for channel runtimes "
                "and the web console. Durable run facts, translated tool "
                "lifecycle facts, and transient live "
                "deltas belong to this single consumer-facing contract."
            ),
            definition_ids=(
                *RUN_OBSERVATION_EVENT_NAMES,
                ORCHESTRATION_RUN_LLM_TEXT_DELTA_EVENT,
                ORCHESTRATION_RUN_TOOL_UPDATED_EVENT,
            ),
            topics=(
                turn_session_topic("{session_key}"),
                turn_session_live_topic("{session_key}"),
                named_event_topic(ORCHESTRATION_RUN_LLM_TEXT_DELTA_EVENT),
            ),
            consumers=("channel runtimes", "web console"),
            notes=(
                "Consumers should treat persistent and transient events as transport characteristics inside one contract surface.",
                "Session-scoped observation is the single durable source for orchestration facts.",
            ),
        ),
        EventSurface(
            surface_id="orchestration.runtime_observation",
            owner="orchestration",
            description=(
                "Unified orchestration runtime health surface for queue, lane, "
                "executor capacity, and LLM limiter visibility."
            ),
            definition_ids=(ORCHESTRATION_RUNTIME_STATUS_EVENT,),
            topics=(orchestration_runtime_observation_topic(),),
            consumers=("web console", "diagnostics", "daemon monitors"),
            notes=(
                "This surface intentionally stays separate from run lifecycle observation.",
                "It is derived from current orchestration shared state when runtime source events arrive.",
            ),
        ),
        EventSurface(
            surface_id="orchestration.operational",
            owner="orchestration",
            description=(
                "Direct orchestration-owned operational facts for scheduler "
                "intake, executor assignment, and executor lease state."
            ),
            definition_ids=(
                *_RUN_OPERATIONAL_EVENT_NAMES,
                *_INGRESS_OPERATIONAL_EVENT_NAMES,
                *_EXECUTOR_OPERATIONAL_EVENT_NAMES,
                *_EXECUTION_OPERATIONAL_EVENT_NAMES,
            ),
            topics=tuple(
                named_event_topic(event_name)
                for event_name in (
                    *_RUN_OPERATIONAL_EVENT_NAMES,
                    *_INGRESS_OPERATIONAL_EVENT_NAMES,
                    *_EXECUTOR_OPERATIONAL_EVENT_NAMES,
                    *_EXECUTION_OPERATIONAL_EVENT_NAMES,
                )
            ),
            consumers=("operations observer", "trace read model", "diagnostics"),
            notes=(
                "This surface describes source operational facts, not the reduced session observation contract.",
            ),
        ),
    )


def orchestration_event_observers() -> tuple[EventObserver, ...]:
    return (
        EventObserver(
            observer_id="orchestration.run.observation",
            owner="orchestration",
            description=(
                "Observes thin orchestration run source events into reduced "
                "session-scoped observation facts."
            ),
            source_event_names=RUN_OBSERVATION_EVENT_NAMES,
            output_definition_ids=RUN_OBSERVATION_EVENT_NAMES,
            handlers=("RunObservationObserver.observe_run_event",),
            notes=(
                "Rehydrates the latest durable run state before publishing a reduced contract event.",
            ),
        ),
        EventObserver(
            observer_id="orchestration.tool.observation",
            owner="orchestration",
            description=(
                "Observes tool module lifecycle events into orchestration-owned run tool observation facts."
            ),
            source_event_names=TOOL_OBSERVATION_SOURCE_EVENT_NAMES,
            output_definition_ids=(ORCHESTRATION_RUN_TOOL_UPDATED_EVENT,),
            handlers=("ToolRunObservationObserver.observe_tool_event",),
            notes=(
                "Uses stable tool read models plus invocation context to translate tool lifecycle into run-scoped observation.",
            ),
        ),
        EventObserver(
            observer_id="orchestration.runtime.observation",
            owner="orchestration",
            description=(
                "Observes scheduler and executor source events into hydrated "
                "orchestration runtime health snapshots."
            ),
            source_event_names=ORCHESTRATION_RUNTIME_OBSERVATION_SOURCE_EVENT_NAMES,
            output_definition_ids=(ORCHESTRATION_RUNTIME_STATUS_EVENT,),
            handlers=("RuntimeObservationObserver.observe_runtime_event",),
            notes=(
                "Rehydrates queue, lane, executor lease, and limiter state from orchestration-owned stores.",
            ),
        ),
    )
