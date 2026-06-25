from __future__ import annotations

from typing import Any

from crxzipple.modules.llm.domain import LlmInvocation, LlmProfile
from crxzipple.modules.llm.application.error_classification import (
    llm_error_family as _error_family,
)
from crxzipple.modules.operations.application.observation_models import OperationsObservedEvent
from crxzipple.modules.operations.application.read_models.llm_error_fact_items import (
    error_fact_items as _error_fact_items,
)
from crxzipple.modules.operations.application.read_models.llm_invocation_detail_payloads import (
    result_payload as _result_payload,
    result_summary as _result_summary,
)
from crxzipple.modules.operations.application.read_models.llm_invocation_detail_items import (
    summary_items as _summary_items,
)
from crxzipple.modules.operations.application.read_models.llm_invocation_detail_runtime import (
    runtime_observations_section as _runtime_observations_section,
)
from crxzipple.modules.operations.application.read_models.llm_invocation_request_context_items import (
    request_context_items as _request_context_items,
)
from crxzipple.modules.operations.application.read_models.llm_invocation_streaming import (
    streaming_invocation_ids as _streaming_invocation_ids,
)
from crxzipple.modules.operations.application.read_models.llm_invocation_labels import (
    invocation_status_tone as _status_tone,
    provider_render_report as _provider_render_report,
)
from crxzipple.modules.operations.application.read_models.llm_models import (
    LlmInvocationDetailModel,
)
from crxzipple.modules.operations.application.read_models.llm_policy_trace_tables import (
    policy_trace_table_for_invocation as _policy_trace_table_for_invocation,
)
from crxzipple.modules.operations.application.read_models.llm_provider_context_mapping import (
    provider_context_mapping_table as _provider_context_mapping_table,
)
from crxzipple.modules.operations.application.read_models.llm_provider_request_diagnostics import (
    provider_wire_preview as _provider_wire_preview,
    request_payload as _request_payload,
    runtime_request_summary as _runtime_request_summary,
)
from crxzipple.modules.operations.application.read_models.llm_resolver_sections import (
    resolver_facts_section as _resolver_facts_section,
)
from crxzipple.modules.operations.application.read_models.llm_response_event_tables import (
    events_table_for_invocation as _events_table_for_invocation,
    response_events_table_for_invocation as _response_events_table_for_invocation,
)
from crxzipple.modules.operations.application.read_models.llm_response_item_tables import (
    response_items_table_for_invocation as _response_items_table_for_invocation,
    response_runtime_mapping_table_for_invocation as _response_runtime_mapping_table_for_invocation,
)
from crxzipple.modules.operations.application.read_models.models import (
    OperationsKeyValueSectionModel,
)


def invocation_details(
    invocations: tuple[LlmInvocation, ...],
    *,
    profiles_by_id: dict[str, LlmProfile],
    events_by_invocation: dict[str, tuple[OperationsObservedEvent, ...]],
    run_contexts: dict[str, dict[str, str]],
    resolver_events_by_run_id: dict[str, OperationsObservedEvent],
    observed_events: tuple[OperationsObservedEvent, ...],
    response_events_by_invocation: dict[str, tuple[Any, ...]],
    response_event_retention_policy: dict[str, object],
) -> tuple[LlmInvocationDetailModel, ...]:
    streaming_ids = _streaming_invocation_ids(observed_events)
    details: list[LlmInvocationDetailModel] = []
    for invocation in invocations:
        profile = profiles_by_id.get(invocation.llm_id)
        events = events_by_invocation.get(invocation.id, ())
        response_events = response_events_by_invocation.get(invocation.id, ())
        run_context = run_contexts.get(invocation.id, {})
        resolver_event = resolver_events_by_run_id.get(run_context.get("run_id", ""))
        error_code = invocation.error.code if invocation.error is not None else "-"
        category = _error_family(error_code) if invocation.error is not None else "-"
        details.append(
            LlmInvocationDetailModel(
                invocation_id=invocation.id,
                title=f"{invocation.llm_id} / {invocation.id}",
                status=invocation.status.value,
                tone=_status_tone(invocation.status.value),
                summary=_summary_items(
                    invocation,
                    profile=profile,
                    run_context=run_context,
                    response_events=response_events,
                ),
                request_context=_request_context_items(
                    invocation,
                    events=events,
                    streaming_ids=streaming_ids,
                ),
                runtime_observations=_runtime_observations_section(
                    invocation,
                    response_event_retention_policy=response_event_retention_policy,
                ),
                runtime_request_summary=_runtime_request_summary(invocation),
                request_payload=_request_payload(invocation),
                provider_render_report=_provider_render_report(invocation),
                provider_wire_preview=_provider_wire_preview(invocation),
                provider_context_mapping=_provider_context_mapping_table(invocation),
                result_payload=_result_payload(invocation),
                result_summary=_result_summary(invocation),
                error=invocation.error.message if invocation.error is not None else "",
                resolver=_resolver_facts_section(
                    invocation,
                    resolver_event=resolver_event,
                    run_context=run_context,
                ),
                error_facts=OperationsKeyValueSectionModel(
                    id="error_facts",
                    title="Error Facts",
                    items=_error_fact_items(
                        invocation,
                        category=category,
                        error_code=error_code,
                    ),
                ),
                policy_trace=_policy_trace_table_for_invocation(invocation),
                response_items=_response_items_table_for_invocation(invocation),
                response_runtime_mapping=_response_runtime_mapping_table_for_invocation(
                    invocation,
                ),
                response_events=_response_events_table_for_invocation(
                    invocation.id,
                    response_events,
                ),
                events=_events_table_for_invocation(invocation.id, events),
            ),
        )
    return tuple(details)

__all__ = ["invocation_details"]
