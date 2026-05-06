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
    ORCHESTRATION_RUN_MESSAGE_APPENDED_EVENT,
    SESSION_MESSAGE_APPENDED_SOURCE_EVENT,
    ORCHESTRATION_RUN_TOOL_UPDATED_EVENT,
    ORCHESTRATION_RUNTIME_OBSERVATION_SOURCE_EVENT_NAMES,
    ORCHESTRATION_RUNTIME_STATUS_EVENT,
)
from crxzipple.shared.domain.events import named_event_topic


def orchestration_event_topic_contracts() -> tuple[EventTopicContract, ...]:
    return (
        EventTopicContract(
            contract_id="turn.session",
            topic_pattern=turn_session_topic("{session_key}"),
            owner="orchestration",
            description=(
                "Session scoped durable run facts and appended session messages."
            ),
            kinds=("fact",),
            producers=(
                "RunObservationObserver.observe_run_event",
                "SessionMessageObservationObserver.observe_message_appended",
            ),
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
                "Prompt assembly LLM routing decisions observed for operations "
                "and diagnostics."
            ),
            kinds=("observe",),
            producers=("PromptAssembler._publish_llm_resolution_event",),
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
            definition_id=ORCHESTRATION_RUN_MESSAGE_APPENDED_EVENT,
            owner="orchestration",
            event_name=ORCHESTRATION_RUN_MESSAGE_APPENDED_EVENT,
            description="Run-scoped message fact forwarded into the orchestration observation surface.",
            topics=("turn.session.{session_key}",),
            producers=("SessionMessageObservationObserver.observe_message_appended",),
            consumers=("channel runtimes", "web console", "diagnostics"),
            fields=(
                EventDefinitionField("event_name", "Stable session event name.", "string", True),
                EventDefinitionField("message_id", "Session message identifier.", "string", True),
                EventDefinitionField("session_key", "Owning session key.", "string", True),
                EventDefinitionField("session_id", "Owning session instance id.", "string", True),
                EventDefinitionField("role", "Message role.", "string", True),
                EventDefinitionField("kind", "Message kind.", "string", True),
                EventDefinitionField("source_kind", "Source entity type for this message.", "string"),
                EventDefinitionField("source_id", "Source entity id for this message.", "string"),
                EventDefinitionField("message", "Durable message payload including blocks and metadata.", "object", True),
            ),
            durability="persistent",
            publication_mode="translated",
            source_event_names=(SESSION_MESSAGE_APPENDED_SOURCE_EVENT,),
            notes=(
                "session emits a self-describing message fact and orchestration forwards it under an orchestration-owned contract name",
                "channel runtimes should publish attachments/artifacts from the durable message payload",
            ),
        )
    )
    definitions.append(
        EventDefinition(
            definition_id="orchestration.llm_resolved",
            owner="orchestration",
            event_name="orchestration.llm_resolved",
            description="Prompt assembly LLM routing decision observed for operations.",
            topics=(named_event_topic("orchestration.llm_resolved"),),
            producers=("PromptAssembler._publish_llm_resolution_event",),
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
                "and the web console. Durable run facts, durable appended "
                "messages, translated tool lifecycle facts, and transient live "
                "deltas belong to this single consumer-facing contract."
            ),
            definition_ids=(
                *RUN_OBSERVATION_EVENT_NAMES,
                ORCHESTRATION_RUN_LLM_TEXT_DELTA_EVENT,
                ORCHESTRATION_RUN_MESSAGE_APPENDED_EVENT,
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
            observer_id="orchestration.session.message_observation",
            owner="orchestration",
            description=(
                "Observes appended session message source events into translated "
                "session-scoped observation facts."
            ),
            source_event_names=(SESSION_MESSAGE_APPENDED_SOURCE_EVENT,),
            output_definition_ids=(ORCHESTRATION_RUN_MESSAGE_APPENDED_EVENT,),
            handlers=("SessionMessageObservationObserver.observe_message_appended",),
            notes=(
                "Translates the session-owned message fact into an orchestration-owned run observation contract.",
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
