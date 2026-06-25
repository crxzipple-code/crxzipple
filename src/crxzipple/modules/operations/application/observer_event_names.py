from __future__ import annotations

from crxzipple.modules.access.application.events import ACCESS_OPERATION_EVENT_NAMES
from crxzipple.modules.browser.application.events import BROWSER_OPERATION_EVENT_NAMES
from crxzipple.modules.memory.application.events import MEMORY_OPERATION_EVENT_NAMES
from crxzipple.modules.operations.application.event_contracts import (
    OPERATIONS_PROJECTION_INVALIDATED_EVENT,
)
from crxzipple.modules.operations.application.orchestration_observation import (
    ORCHESTRATION_OPERATIONAL_EVENT_NAMES,
)
from crxzipple.modules.skills.application.events import SKILL_OPERATION_EVENT_NAMES
from crxzipple.shared import (
    ORCHESTRATION_RUN_LLM_TEXT_DELTA_EVENT,
    ORCHESTRATION_RUN_OBSERVATION_EVENT_NAMES,
    ORCHESTRATION_RUN_TOOL_UPDATED_EVENT,
    ORCHESTRATION_RUNTIME_OBSERVATION_SOURCE_EVENT_NAMES,
    ORCHESTRATION_RUNTIME_STATUS_EVENT,
    SESSION_ITEM_APPENDED_SOURCE_EVENT,
    TOOL_RUN_OBSERVATION_SOURCE_EVENT_NAMES,
)
from crxzipple.shared.event_contracts import (
    EventDefinitionRegistry,
    TOOL_CLI_EVENT_NAMES,
    TOOL_FUNCTION_EVENT_NAMES,
    TOOL_SOURCE_EVENT_NAMES,
)

_OPERATIONS_OBSERVER_STATIC_EVENT_NAMES: tuple[str, ...] = (
    *ORCHESTRATION_OPERATIONAL_EVENT_NAMES,
    *ORCHESTRATION_RUN_OBSERVATION_EVENT_NAMES,
    SESSION_ITEM_APPENDED_SOURCE_EVENT,
    ORCHESTRATION_RUN_TOOL_UPDATED_EVENT,
    ORCHESTRATION_RUN_LLM_TEXT_DELTA_EVENT,
    ORCHESTRATION_RUNTIME_STATUS_EVENT,
    *ORCHESTRATION_RUNTIME_OBSERVATION_SOURCE_EVENT_NAMES,
    *TOOL_RUN_OBSERVATION_SOURCE_EVENT_NAMES,
    "dispatch.task.queued",
    "dispatch.task.requeued",
    "dispatch.task.recovered",
    "tool.enabled",
    "tool.disabled",
    *TOOL_SOURCE_EVENT_NAMES,
    *TOOL_FUNCTION_EVENT_NAMES,
    *TOOL_CLI_EVENT_NAMES,
    "tool.assignment.created",
    "tool.assignment.started",
    "tool.assignment.succeeded",
    "tool.assignment.failed",
    "tool.assignment.cancelled",
    "tool.assignment.expired",
    "tool.worker.registered",
    "tool.worker.capabilities_updated",
    "tool.worker.recovered",
    "tool.worker.pruned",
    "tool.worker.stale",
    "llm.profile_registered",
    "llm.profile_updated",
    "llm.profile_warmup_succeeded",
    "llm.profile_warmup_skipped",
    "llm.profile_warmup_failed",
    "llm.invocation_started",
    "llm.invocation_provider_request_prepared",
    "llm.invocation_succeeded",
    "llm.invocation_failed",
    "llm.stream_delta_observed",
    "orchestration.llm_resolved",
    "channel.connection.subscription_updated",
    "channel.observation.dead_lettered",
    *MEMORY_OPERATION_EVENT_NAMES,
    *ACCESS_OPERATION_EVENT_NAMES,
    *SKILL_OPERATION_EVENT_NAMES,
    *BROWSER_OPERATION_EVENT_NAMES,
)


def operations_observer_event_names(
    definition_registry: EventDefinitionRegistry | None = None,
) -> tuple[str, ...]:
    excluded = {OPERATIONS_PROJECTION_INVALIDATED_EVENT}
    names: list[str] = []
    if definition_registry is not None:
        names.extend(
            definition.event_name
            for definition in definition_registry.list_definitions()
            if definition.durability == "persistent"
            and definition.event_name not in excluded
        )
    names.extend(_OPERATIONS_OBSERVER_STATIC_EVENT_NAMES)
    return tuple(
        dict.fromkeys(
            name.strip()
            for name in names
            if isinstance(name, str) and name.strip() and name not in excluded
        ),
    )
