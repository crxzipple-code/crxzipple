from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from crxzipple.shared.domain.events import named_event_topic


EventDefinitionStability = Literal["experimental", "stable"]
EventDefinitionDurability = Literal["persistent", "transient"]
EventDefinitionPublicationMode = Literal[
    "direct",
    "reduced",
    "hydrated",
    "translated",
    "mirrored",
]


def _normalize_text(value: str, *, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} is required.")
    return normalized


def _normalize_text_tuple(values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(item.strip() for item in values if isinstance(item, str) and item.strip())


@dataclass(frozen=True, slots=True)
class EventDefinitionField:
    field_path: str
    description: str
    field_type: str = "any"
    required: bool = False
    notes: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "field_path",
            _normalize_text(self.field_path, field_name="field_path"),
        )
        object.__setattr__(
            self,
            "description",
            _normalize_text(self.description, field_name="description"),
        )
        object.__setattr__(
            self,
            "field_type",
            _normalize_text(self.field_type, field_name="field_type"),
        )
        object.__setattr__(self, "notes", _normalize_text_tuple(self.notes))

    def to_payload(self) -> dict[str, Any]:
        return {
            "field_path": self.field_path,
            "description": self.description,
            "field_type": self.field_type,
            "required": self.required,
            "notes": list(self.notes),
        }


@dataclass(frozen=True, slots=True)
class EventDefinition:
    definition_id: str
    owner: str
    event_name: str
    description: str
    topics: tuple[str, ...] = field(default_factory=tuple)
    producers: tuple[str, ...] = field(default_factory=tuple)
    consumers: tuple[str, ...] = field(default_factory=tuple)
    fields: tuple[EventDefinitionField, ...] = field(default_factory=tuple)
    stability: EventDefinitionStability = "stable"
    durability: EventDefinitionDurability = "persistent"
    publication_mode: EventDefinitionPublicationMode = "direct"
    source_event_names: tuple[str, ...] = field(default_factory=tuple)
    notes: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "definition_id",
            _normalize_text(self.definition_id, field_name="definition_id"),
        )
        object.__setattr__(self, "owner", _normalize_text(self.owner, field_name="owner"))
        object.__setattr__(
            self,
            "event_name",
            _normalize_text(self.event_name, field_name="event_name"),
        )
        object.__setattr__(
            self,
            "description",
            _normalize_text(self.description, field_name="description"),
        )
        object.__setattr__(self, "topics", _normalize_text_tuple(self.topics))
        object.__setattr__(self, "producers", _normalize_text_tuple(self.producers))
        object.__setattr__(self, "consumers", _normalize_text_tuple(self.consumers))
        object.__setattr__(
            self,
            "source_event_names",
            _normalize_text_tuple(self.source_event_names),
        )
        object.__setattr__(self, "notes", _normalize_text_tuple(self.notes))

    def to_payload(self) -> dict[str, Any]:
        return {
            "definition_id": self.definition_id,
            "owner": self.owner,
            "event_name": self.event_name,
            "description": self.description,
            "topics": list(self.topics),
            "producers": list(self.producers),
            "consumers": list(self.consumers),
            "fields": [field.to_payload() for field in self.fields],
            "stability": self.stability,
            "durability": self.durability,
            "publication_mode": self.publication_mode,
            "source_event_names": list(self.source_event_names),
            "notes": list(self.notes),
        }


@dataclass(frozen=True, slots=True)
class EventSurface:
    surface_id: str
    owner: str
    description: str
    definition_ids: tuple[str, ...] = field(default_factory=tuple)
    topics: tuple[str, ...] = field(default_factory=tuple)
    consumers: tuple[str, ...] = field(default_factory=tuple)
    notes: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "surface_id",
            _normalize_text(self.surface_id, field_name="surface_id"),
        )
        object.__setattr__(self, "owner", _normalize_text(self.owner, field_name="owner"))
        object.__setattr__(
            self,
            "description",
            _normalize_text(self.description, field_name="description"),
        )
        object.__setattr__(self, "definition_ids", _normalize_text_tuple(self.definition_ids))
        object.__setattr__(self, "topics", _normalize_text_tuple(self.topics))
        object.__setattr__(self, "consumers", _normalize_text_tuple(self.consumers))
        object.__setattr__(self, "notes", _normalize_text_tuple(self.notes))

    def to_payload(self) -> dict[str, Any]:
        return {
            "surface_id": self.surface_id,
            "owner": self.owner,
            "description": self.description,
            "definition_ids": list(self.definition_ids),
            "topics": list(self.topics),
            "consumers": list(self.consumers),
            "notes": list(self.notes),
        }


@dataclass(frozen=True, slots=True)
class EventObserver:
    observer_id: str
    owner: str
    description: str
    source_event_names: tuple[str, ...] = field(default_factory=tuple)
    output_definition_ids: tuple[str, ...] = field(default_factory=tuple)
    handlers: tuple[str, ...] = field(default_factory=tuple)
    notes: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "observer_id",
            _normalize_text(self.observer_id, field_name="observer_id"),
        )
        object.__setattr__(self, "owner", _normalize_text(self.owner, field_name="owner"))
        object.__setattr__(
            self,
            "description",
            _normalize_text(self.description, field_name="description"),
        )
        object.__setattr__(
            self,
            "source_event_names",
            _normalize_text_tuple(self.source_event_names),
        )
        object.__setattr__(
            self,
            "output_definition_ids",
            _normalize_text_tuple(self.output_definition_ids),
        )
        object.__setattr__(self, "handlers", _normalize_text_tuple(self.handlers))
        object.__setattr__(self, "notes", _normalize_text_tuple(self.notes))

    def to_payload(self) -> dict[str, Any]:
        return {
            "observer_id": self.observer_id,
            "owner": self.owner,
            "description": self.description,
            "source_event_names": list(self.source_event_names),
            "output_definition_ids": list(self.output_definition_ids),
            "handlers": list(self.handlers),
            "notes": list(self.notes),
        }


TOOL_RUN_EVENT_NAMES: tuple[str, ...] = (
    "tool.run.created",
    "tool.run.queued",
    "tool.run.dispatching",
    "tool.run.started",
    "tool.run.heartbeated",
    "tool.run.succeeded",
    "tool.run.failed",
    "tool.run.requeued",
    "tool.run.cancel_requested",
    "tool.run.cancelled",
    "tool.run.timed_out",
)

TOOL_ASSIGNMENT_EVENT_NAMES: tuple[str, ...] = (
    "tool.assignment.created",
    "tool.assignment.started",
    "tool.assignment.heartbeated",
    "tool.assignment.succeeded",
    "tool.assignment.failed",
    "tool.assignment.cancelled",
    "tool.assignment.expired",
)

TOOL_WORKER_EVENT_NAMES: tuple[str, ...] = (
    "tool.worker.registered",
    "tool.worker.recovered",
    "tool.worker.capabilities_updated",
    "tool.worker.stale",
    "tool.worker.pruned",
)

TOOL_CATALOG_EVENT_NAMES: tuple[str, ...] = (
    "tool.enabled",
    "tool.disabled",
)

TOOL_SOURCE_EVENT_NAMES: tuple[str, ...] = (
    "tool.source.created",
    "tool.source.updated",
    "tool.source.disabled",
    "tool.source.restored",
    "tool.source.deleted",
    "tool.source.discovery_completed",
    "tool.source.discovery_failed",
)

TOOL_FUNCTION_EVENT_NAMES: tuple[str, ...] = (
    "tool.function.created",
    "tool.function.updated",
    "tool.function.stale",
    "tool.function.deprecated",
    "tool.function.enabled",
    "tool.function.disabled",
    "tool.function.policy_updated",
)

TOOL_CLI_EVENT_NAMES: tuple[str, ...] = (
    "tool.cli.output_observed",
)

LLM_INVOCATION_EVENT_NAMES: tuple[str, ...] = (
    "llm.invocation_started",
    "llm.invocation_provider_request_prepared",
    "llm.invocation_succeeded",
    "llm.invocation_failed",
)

LLM_PROFILE_EVENT_NAMES: tuple[str, ...] = (
    "llm.profile_registered",
    "llm.profile_updated",
    "llm.profile_warmup_succeeded",
    "llm.profile_warmup_skipped",
    "llm.profile_warmup_failed",
)

LLM_STREAM_EVENT_NAMES: tuple[str, ...] = (
    "llm.stream_delta_observed",
)

TOOL_LLM_EVENT_NAMES: tuple[str, ...] = (
    *TOOL_RUN_EVENT_NAMES,
    *TOOL_ASSIGNMENT_EVENT_NAMES,
    *TOOL_WORKER_EVENT_NAMES,
    *TOOL_CATALOG_EVENT_NAMES,
    *TOOL_SOURCE_EVENT_NAMES,
    *TOOL_FUNCTION_EVENT_NAMES,
    *TOOL_CLI_EVENT_NAMES,
    *LLM_INVOCATION_EVENT_NAMES,
    *LLM_PROFILE_EVENT_NAMES,
    *LLM_STREAM_EVENT_NAMES,
)


_EVENT_NAME_FIELD = EventDefinitionField(
    "event_name",
    "Stable named event emitted on Event.name.",
    "string",
    True,
)

_TOOL_RUN_FIELDS: tuple[EventDefinitionField, ...] = (
    _EVENT_NAME_FIELD,
    EventDefinitionField("run_id", "Tool run identifier.", "string", True),
    EventDefinitionField("tool_id", "Tool catalog identifier.", "string", True),
    EventDefinitionField("worker_id", "Worker currently claiming the run.", "string"),
    EventDefinitionField("attempt_count", "Current execution attempt counter.", "integer"),
    EventDefinitionField("mode", "Tool execution mode.", "string"),
    EventDefinitionField("strategy", "Tool execution strategy.", "string"),
    EventDefinitionField("environment", "Tool execution environment.", "string"),
    EventDefinitionField("status", "Normalized run status implied by the event suffix.", "string"),
    EventDefinitionField("heartbeat_at", "Most recent run heartbeat timestamp.", "string"),
    EventDefinitionField("lease_expires_at", "Run lease expiration timestamp.", "string"),
    EventDefinitionField("error_message", "Terminal tool error message.", "string"),
    EventDefinitionField("reason", "Requeue or cancellation reason.", "string"),
)

_TOOL_ASSIGNMENT_FIELDS: tuple[EventDefinitionField, ...] = (
    _EVENT_NAME_FIELD,
    EventDefinitionField("assignment_id", "Tool run assignment identifier.", "string", True),
    EventDefinitionField("run_id", "Tool run identifier.", "string", True),
    EventDefinitionField("tool_id", "Tool catalog identifier.", "string", True),
    EventDefinitionField("worker_id", "Assigned worker identifier.", "string", True),
    EventDefinitionField("attempt_count", "Execution attempt assigned to the worker.", "integer"),
    EventDefinitionField("status", "Normalized assignment status implied by the event suffix.", "string"),
    EventDefinitionField("heartbeat_at", "Most recent assignment heartbeat timestamp.", "string"),
    EventDefinitionField("lease_expires_at", "Assignment lease expiration timestamp.", "string"),
    EventDefinitionField("reason", "Terminal assignment reason when available.", "string"),
)

_TOOL_WORKER_FIELDS: tuple[EventDefinitionField, ...] = (
    _EVENT_NAME_FIELD,
    EventDefinitionField("worker_id", "Tool worker identifier.", "string", True),
    EventDefinitionField("status", "Worker status at publication time.", "string"),
    EventDefinitionField("previous_status", "Worker status before recovery.", "string"),
    EventDefinitionField("max_in_flight", "Configured concurrent assignment capacity.", "integer"),
    EventDefinitionField("current_in_flight", "Current claimed assignment count.", "integer"),
    EventDefinitionField("lease_expires_at", "Worker lease expiration timestamp.", "string"),
    EventDefinitionField("previous_lease_expires_at", "Previous lease expiration timestamp.", "string"),
    EventDefinitionField("last_heartbeat", "Most recent worker heartbeat timestamp.", "string"),
    EventDefinitionField("retention_seconds", "Expired worker retention window used for pruning.", "integer"),
)

_OPERATIONS_DISPLAY_FIELDS: tuple[EventDefinitionField, ...] = (
    EventDefinitionField("level", "Operational severity level for display.", "string"),
    EventDefinitionField("summary", "Display-safe event summary.", "string"),
    EventDefinitionField("display_label", "Short display label for operations views.", "string"),
    EventDefinitionField("display_summary", "Human-readable operations summary.", "string"),
    EventDefinitionField("display_tone", "Display tone such as info, success, warning, or danger.", "string"),
    EventDefinitionField("entity_type", "Linked entity type for navigation or filtering.", "string"),
    EventDefinitionField("entity_id", "Linked entity identifier for navigation or filtering.", "string"),
)

_TOOL_CATALOG_FIELDS: tuple[EventDefinitionField, ...] = (
    _EVENT_NAME_FIELD,
    EventDefinitionField("tool_id", "Tool catalog identifier.", "string", True),
    EventDefinitionField("tool_name", "Display-safe tool name.", "string"),
    EventDefinitionField("enabled", "Tool enabled state after the change.", "boolean"),
    EventDefinitionField("status", "Normalized catalog status after the change.", "string"),
    *_OPERATIONS_DISPLAY_FIELDS,
)

_TOOL_SOURCE_FIELDS: tuple[EventDefinitionField, ...] = (
    _EVENT_NAME_FIELD,
    EventDefinitionField("source_id", "Tool source catalog identifier.", "string", True),
    EventDefinitionField("kind", "Tool source catalog kind.", "string"),
    EventDefinitionField("display_name", "Display-safe source name.", "string"),
    EventDefinitionField("status", "Source status after the change.", "string"),
    EventDefinitionField("previous_status", "Source status before the change.", "string"),
    EventDefinitionField("revision", "Source catalog revision.", "integer"),
    EventDefinitionField("config_hash", "Stable source configuration hash.", "string"),
    EventDefinitionField("discovery_status", "Discovery run status.", "string"),
    EventDefinitionField("function_count", "Function count discovered from the source.", "integer"),
    EventDefinitionField(
        "provider_backend_count",
        "Provider backend count discovered from the source.",
        "integer",
    ),
    EventDefinitionField("error_message", "Discovery or source lifecycle error message.", "string"),
    EventDefinitionField("changed_fields", "Changed source fields.", "array"),
    *_OPERATIONS_DISPLAY_FIELDS,
)

_TOOL_FUNCTION_FIELDS: tuple[EventDefinitionField, ...] = (
    _EVENT_NAME_FIELD,
    EventDefinitionField("function_id", "Tool function identifier.", "string", True),
    EventDefinitionField("source_id", "Owning tool source identifier.", "string", True),
    EventDefinitionField("stable_key", "Source-stable function key.", "string"),
    EventDefinitionField("schema_hash", "Stable function schema hash.", "string"),
    EventDefinitionField("status", "Function catalog status after the change.", "string"),
    EventDefinitionField("previous_status", "Function catalog status before the change.", "string"),
    EventDefinitionField("enabled", "Function enabled state after the change.", "boolean"),
    EventDefinitionField("revision", "Function catalog revision.", "integer"),
    EventDefinitionField("changed_fields", "Changed function fields.", "array"),
    *_OPERATIONS_DISPLAY_FIELDS,
)

_TOOL_CLI_FIELDS: tuple[EventDefinitionField, ...] = (
    _EVENT_NAME_FIELD,
    EventDefinitionField("source_id", "Owning configured CLI source identifier.", "string", True),
    EventDefinitionField("provider", "Configured CLI provider name.", "string"),
    EventDefinitionField("process_id", "Process application session identifier.", "string", True),
    EventDefinitionField("session_key", "Optional caller correlation key.", "string"),
    EventDefinitionField("stream", "Observed stream: stdout, stderr, or status.", "string", True),
    EventDefinitionField("offset", "Stream offset before this observation.", "integer"),
    EventDefinitionField("next_offset", "Stream offset after this observation.", "integer"),
    EventDefinitionField("text", "Observed output text chunk.", "string"),
    EventDefinitionField("text_length", "Observed output text length.", "integer"),
    EventDefinitionField("status", "Process status when this observation was made.", "string"),
    EventDefinitionField("exit_code", "Process exit code when known.", "integer"),
    *_OPERATIONS_DISPLAY_FIELDS,
)

_LLM_INVOCATION_FIELDS: tuple[EventDefinitionField, ...] = (
    _EVENT_NAME_FIELD,
    EventDefinitionField("invocation_id", "LLM invocation identifier.", "string", True),
    EventDefinitionField("llm_id", "LLM profile identifier.", "string", True),
    EventDefinitionField("provider", "LLM provider.", "string"),
    EventDefinitionField("api_family", "Adapter API family.", "string"),
    EventDefinitionField("model_name", "Provider model name.", "string"),
    EventDefinitionField("model_family", "Model family used for routing and display.", "string"),
    EventDefinitionField("concurrency_key", "Limiter key used for this invocation.", "string"),
    EventDefinitionField("max_concurrency", "Profile concurrency limit.", "integer"),
    EventDefinitionField("timeout_seconds", "Profile timeout in seconds.", "number"),
    EventDefinitionField("streaming", "Whether the invocation used streaming.", "boolean"),
    EventDefinitionField("message_count", "Input message count.", "integer"),
    EventDefinitionField("tool_schema_count", "Tool schema count supplied to the adapter.", "integer"),
    EventDefinitionField("response_format_configured", "Whether a response format was configured.", "boolean"),
    EventDefinitionField("provider_request_id", "Provider request identifier when returned.", "string"),
    EventDefinitionField("duration_seconds", "Invocation duration after completion.", "number"),
    EventDefinitionField("finish_reason", "Provider finish reason.", "string"),
    EventDefinitionField("tool_call_count", "Tool call count in the final result.", "integer"),
    EventDefinitionField("usage", "Provider usage payload.", "object"),
    EventDefinitionField("error_code", "Normalized invocation error code.", "string"),
    EventDefinitionField("error_family", "Display-safe error family.", "string"),
    EventDefinitionField("retryable", "Whether the invocation failure may be retried.", "boolean"),
    EventDefinitionField("error_message", "Invocation failure message.", "string"),
    EventDefinitionField("error_details", "Provider or adapter error details.", "object"),
)

_LLM_PROFILE_FIELDS: tuple[EventDefinitionField, ...] = (
    _EVENT_NAME_FIELD,
    EventDefinitionField("llm_id", "LLM profile identifier.", "string", True),
    EventDefinitionField("provider", "LLM provider.", "string", True),
    EventDefinitionField("api_family", "Adapter API family.", "string", True),
    EventDefinitionField("source_kind", "Profile source kind when synced.", "string"),
    EventDefinitionField("status", "Profile operation status.", "string"),
    EventDefinitionField("transport", "Provider transport used by profile operation.", "string"),
    EventDefinitionField("endpoint", "Provider endpoint used by profile operation.", "string"),
    EventDefinitionField("reused_connection", "Whether warmup reused an existing provider connection.", "boolean"),
    EventDefinitionField("reason", "Display-safe reason for skipped or failed profile operation.", "string"),
    EventDefinitionField("details", "Provider profile operation details.", "object"),
)

_LLM_STREAM_FIELDS: tuple[EventDefinitionField, ...] = (
    _EVENT_NAME_FIELD,
    EventDefinitionField("invocation_id", "LLM invocation identifier.", "string", True),
    EventDefinitionField("llm_id", "LLM profile identifier.", "string"),
    EventDefinitionField("status", "Streaming observation status.", "string"),
    EventDefinitionField("streaming", "Whether the invocation is currently streaming.", "boolean"),
    EventDefinitionField("text_delta", "Incremental text delta when retained for diagnostics.", "string"),
    EventDefinitionField("text_delta_length", "Character count for the observed delta.", "integer"),
    EventDefinitionField("token_count", "Token count associated with the delta when available.", "integer"),
    *_OPERATIONS_DISPLAY_FIELDS,
)


def _lifecycle_definition(
    *,
    event_name: str,
    owner: str,
    description: str,
    producers: tuple[str, ...],
    consumers: tuple[str, ...],
    fields: tuple[EventDefinitionField, ...],
    notes: tuple[str, ...] = (),
) -> EventDefinition:
    return EventDefinition(
        definition_id=event_name,
        owner=owner,
        event_name=event_name,
        description=description,
        topics=(named_event_topic(event_name),),
        producers=producers,
        consumers=consumers,
        fields=fields,
        durability="persistent",
        publication_mode="direct",
        notes=notes,
    )


def tool_llm_event_definitions() -> tuple[EventDefinition, ...]:
    tool_run_definitions = tuple(
        _lifecycle_definition(
            event_name=event_name,
            owner="tool",
            description="Tool run lifecycle fact emitted by the tool module.",
            producers=("ToolRun", "ToolSchedulerService"),
            consumers=(
                "ToolRunObservationObserver",
                "operations observer",
                "trace read model",
            ),
            fields=_TOOL_RUN_FIELDS,
            notes=(
                "tool owns run lifecycle truth; orchestration observes these facts",
            ),
        )
        for event_name in TOOL_RUN_EVENT_NAMES
    )
    assignment_definitions = tuple(
        _lifecycle_definition(
            event_name=event_name,
            owner="tool",
            description="Tool assignment lifecycle fact emitted by the tool module.",
            producers=("ToolRunAssignment", "ToolWorkerApplicationService"),
            consumers=("operations observer", "trace read model"),
            fields=_TOOL_ASSIGNMENT_FIELDS,
            notes=("assignment lifecycle is worker claim truth, not run completion truth",),
        )
        for event_name in TOOL_ASSIGNMENT_EVENT_NAMES
    )
    worker_definitions = tuple(
        _lifecycle_definition(
            event_name=event_name,
            owner="tool",
            description="Tool worker lifecycle fact emitted by the tool module.",
            producers=("ToolWorkerRegistration", "ToolWorkerApplicationService"),
            consumers=("operations observer", "trace read model"),
            fields=_TOOL_WORKER_FIELDS,
            notes=("worker lifecycle facts describe capacity and lease visibility",),
        )
        for event_name in TOOL_WORKER_EVENT_NAMES
    )
    catalog_definitions = tuple(
        _lifecycle_definition(
            event_name=event_name,
            owner="tool",
            description="Tool catalog availability fact emitted by the tool module.",
            producers=("Tool.enable", "Tool.disable", "ToolApplicationService"),
            consumers=("operations observer", "trace read model"),
            fields=_TOOL_CATALOG_FIELDS,
            notes=(
                "tool catalog state is tool-owned; operations observes enablement changes",
            ),
        )
        for event_name in TOOL_CATALOG_EVENT_NAMES
    )
    source_definitions = tuple(
        _lifecycle_definition(
            event_name=event_name,
            owner="tool",
            description="Tool source lifecycle fact emitted by the tool module.",
            producers=("ToolSourceCommandService",),
            consumers=("operations observer", "trace read model"),
            fields=_TOOL_SOURCE_FIELDS,
            notes=(
                "tool source state is tool-owned; operations observes configured and bundled source facts",
            ),
        )
        for event_name in TOOL_SOURCE_EVENT_NAMES
    )
    function_definitions = tuple(
        _lifecycle_definition(
            event_name=event_name,
            owner="tool",
            description="Tool function catalog lifecycle fact emitted by the tool module.",
            producers=("ToolCatalogReconcileService", "ToolFunctionCommandService"),
            consumers=("operations observer", "trace read model"),
            fields=_TOOL_FUNCTION_FIELDS,
            notes=(
                "tool function catalog state is tool-owned; operations observes source reconciliation outcomes",
            ),
        )
        for event_name in TOOL_FUNCTION_EVENT_NAMES
    )
    cli_definitions = tuple(
        _lifecycle_definition(
            event_name=event_name,
            owner="tool",
            description="Configured CLI process output observation fact emitted by the tool module.",
            producers=("CliGuidedRuntime",),
            consumers=("operations observer", "trace read model", "settings console"),
            fields=_TOOL_CLI_FIELDS,
            notes=(
                "CLI output facts are incremental observations keyed by process_id and stream offset",
            ),
        )
        for event_name in TOOL_CLI_EVENT_NAMES
    )
    invocation_definitions = tuple(
        _lifecycle_definition(
            event_name=event_name,
            owner="llm",
            description="LLM invocation lifecycle fact emitted by the LLM module.",
            producers=("LlmApplicationService",),
            consumers=("operations observer", "trace read model"),
            fields=_LLM_INVOCATION_FIELDS,
            notes=("LLM module owns invocation truth; orchestration observes outcomes",),
        )
        for event_name in LLM_INVOCATION_EVENT_NAMES
    )
    profile_definitions = tuple(
        _lifecycle_definition(
            event_name=event_name,
            owner="llm",
            description="LLM profile lifecycle fact emitted by the LLM module.",
            producers=("LlmApplicationService",),
            consumers=("operations observer", "trace read model"),
            fields=_LLM_PROFILE_FIELDS,
            notes=("profile events describe routing capacity, not invocation outcomes",),
        )
        for event_name in LLM_PROFILE_EVENT_NAMES
    )
    stream_definitions = tuple(
        _lifecycle_definition(
            event_name=event_name,
            owner="llm",
            description="LLM streaming delta observation fact emitted for diagnostics.",
            producers=("LlmApplicationService", "LLM stream observers"),
            consumers=("operations observer", "trace read model"),
            fields=_LLM_STREAM_FIELDS,
            notes=(
                "stream deltas are observation facts; consumers should not rebuild final invocation truth from raw deltas",
            ),
        )
        for event_name in LLM_STREAM_EVENT_NAMES
    )
    return (
        *tool_run_definitions,
        *assignment_definitions,
        *worker_definitions,
        *catalog_definitions,
        *source_definitions,
        *function_definitions,
        *cli_definitions,
        *invocation_definitions,
        *profile_definitions,
        *stream_definitions,
    )


class EventDefinitionRegistry:
    def __init__(
        self,
        *,
        definitions: tuple[EventDefinition, ...] | None = None,
        surfaces: tuple[EventSurface, ...] | None = None,
        observers: tuple[EventObserver, ...] | None = None,
        include_builtin_definitions: bool | None = None,
    ) -> None:
        self._definitions_by_id: dict[str, EventDefinition] = {}
        self._definitions_by_event_name: dict[str, EventDefinition] = {}
        self._surfaces_by_id: dict[str, EventSurface] = {}
        self._observers_by_id: dict[str, EventObserver] = {}
        if include_builtin_definitions is None:
            include_builtin_definitions = (
                definitions is None and surfaces is None and observers is None
            )
        initial_definitions = (
            (*tool_llm_event_definitions(), *(definitions or ()))
            if include_builtin_definitions
            else definitions or ()
        )
        for definition in initial_definitions:
            self.register(definition)
        for surface in surfaces or ():
            self.register_surface(surface)
        for observer in observers or ():
            self.register_observer(observer)

    def register(self, definition: EventDefinition) -> None:
        if definition.definition_id in self._definitions_by_id:
            raise ValueError(
                f"event definition '{definition.definition_id}' is already registered.",
            )
        if definition.event_name in self._definitions_by_event_name:
            raise ValueError(
                f"event name '{definition.event_name}' is already registered.",
            )
        self._definitions_by_id[definition.definition_id] = definition
        self._definitions_by_event_name[definition.event_name] = definition

    def register_many(self, definitions: tuple[EventDefinition, ...]) -> None:
        for definition in definitions:
            self.register(definition)

    def register_surface(self, surface: EventSurface) -> None:
        if surface.surface_id in self._surfaces_by_id:
            raise ValueError(
                f"event surface '{surface.surface_id}' is already registered.",
            )
        missing_definition_ids = tuple(
            definition_id
            for definition_id in surface.definition_ids
            if definition_id not in self._definitions_by_id
        )
        if missing_definition_ids:
            missing_text = ", ".join(missing_definition_ids)
            raise ValueError(
                f"event surface '{surface.surface_id}' references unregistered "
                f"definitions: {missing_text}",
            )
        self._surfaces_by_id[surface.surface_id] = surface

    def register_surfaces(self, surfaces: tuple[EventSurface, ...]) -> None:
        for surface in surfaces:
            self.register_surface(surface)

    def register_observer(self, observer: EventObserver) -> None:
        if observer.observer_id in self._observers_by_id:
            raise ValueError(
                f"event observer '{observer.observer_id}' is already registered.",
            )
        missing_definition_ids = tuple(
            definition_id
            for definition_id in observer.output_definition_ids
            if definition_id not in self._definitions_by_id
        )
        if missing_definition_ids:
            missing_text = ", ".join(missing_definition_ids)
            raise ValueError(
                f"event observer '{observer.observer_id}' references unregistered "
                f"definitions: {missing_text}",
            )
        self._observers_by_id[observer.observer_id] = observer

    def register_observers(self, observers: tuple[EventObserver, ...]) -> None:
        for observer in observers:
            self.register_observer(observer)

    def list_definitions(self) -> tuple[EventDefinition, ...]:
        return tuple(
            self._definitions_by_id[key]
            for key in sorted(self._definitions_by_id)
        )

    def list_surfaces(self) -> tuple[EventSurface, ...]:
        return tuple(
            self._surfaces_by_id[key]
            for key in sorted(self._surfaces_by_id)
        )

    def list_observers(self) -> tuple[EventObserver, ...]:
        return tuple(
            self._observers_by_id[key]
            for key in sorted(self._observers_by_id)
        )

    def get(self, definition_id: str) -> EventDefinition | None:
        return self._definitions_by_id.get(definition_id.strip())

    def get_by_event_name(self, event_name: str) -> EventDefinition | None:
        return self._definitions_by_event_name.get(event_name.strip())

    def get_surface(self, surface_id: str) -> EventSurface | None:
        return self._surfaces_by_id.get(surface_id.strip())

    def get_observer(self, observer_id: str) -> EventObserver | None:
        return self._observers_by_id.get(observer_id.strip())

    def list_surfaces_for_definition(
        self,
        definition_id: str,
    ) -> tuple[EventSurface, ...]:
        normalized_definition_id = definition_id.strip()
        if not normalized_definition_id:
            return ()
        return tuple(
            surface
            for surface in self.list_surfaces()
            if normalized_definition_id in surface.definition_ids
        )

    def list_surfaces_for_event_name(
        self,
        event_name: str,
    ) -> tuple[EventSurface, ...]:
        definition = self.get_by_event_name(event_name)
        if definition is None:
            return ()
        return self.list_surfaces_for_definition(definition.definition_id)

    def list_observers_for_event_name(
        self,
        event_name: str,
    ) -> tuple[EventObserver, ...]:
        normalized_event_name = event_name.strip()
        if not normalized_event_name:
            return ()
        return tuple(
            observer
            for observer in self.list_observers()
            if normalized_event_name in observer.source_event_names
            or normalized_event_name in observer.output_definition_ids
        )

    def to_payload(self) -> dict[str, Any]:
        definitions = [definition.to_payload() for definition in self.list_definitions()]
        surfaces = [surface.to_payload() for surface in self.list_surfaces()]
        observers = [observer.to_payload() for observer in self.list_observers()]
        return {
            "definition_count": len(definitions),
            "definitions": definitions,
            "surface_count": len(surfaces),
            "surfaces": surfaces,
            "observer_count": len(observers),
            "observers": observers,
        }
