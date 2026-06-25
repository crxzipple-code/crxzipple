from __future__ import annotations

from collections import Counter

from crxzipple.modules.llm.domain import LlmInvocation
from crxzipple.modules.operations.application.observation_models import OperationsObservedEvent
from crxzipple.modules.operations.application.read_models.models import (
    OperationsChartSectionModel,
    OperationsChartSegmentModel,
    OperationsKeyValueItemModel,
    OperationsKeyValueSectionModel,
)
from crxzipple.modules.operations.application.read_models.llm_resolver_labels import (
    optional_int_label,
    resolver_replay_window_label,
    text_value,
)


def resolver_events_by_run_id(
    resolver_events: tuple[OperationsObservedEvent, ...],
) -> dict[str, OperationsObservedEvent]:
    result: dict[str, OperationsObservedEvent] = {}
    for event in resolver_events:
        run_id = text_value(event.payload.get("run_id"))
        if run_id is None:
            continue
        result.setdefault(run_id, event)
    return result


def resolver_bucket(event: OperationsObservedEvent) -> str:
    payload = event.payload
    requested = text_value(payload.get("requested_llm_id"))
    resolved = text_value(payload.get("resolved_llm_id"))
    strategy = (
        text_value(payload.get("strategy"))
        or text_value(payload.get("resolution_strategy"))
        or text_value(payload.get("resolved_by"))
        or ""
    ).lower()
    status = event.status.lower()
    if status in {"failed", "error"} or not resolved:
        return "no_match"
    if requested and resolved and requested != resolved:
        return "fallback_used"
    if "override" in strategy or "explicit" in strategy:
        return "explicit_override"
    return "agent_default"


def model_resolver_section(
    resolver_events: tuple[OperationsObservedEvent, ...],
) -> OperationsChartSectionModel:
    counts = Counter(resolver_bucket(event) for event in resolver_events)
    segments = tuple(
        OperationsChartSegmentModel(
            id=bucket,
            label=label,
            value=counts[bucket],
            tone=tone,
        )
        for bucket, label, tone in (
            ("agent_default", "Agent Default", "success"),
            ("explicit_override", "Explicit Override", "info"),
            ("fallback_used", "Fallback Used", "warning"),
            ("no_match", "No Match / Error", "danger"),
        )
        if counts[bucket]
    )
    return OperationsChartSectionModel(
        id="model_resolver",
        title="Model Resolver",
        kind="donut",
        total=sum(counts.values()),
        segments=segments,
    )


def resolver_facts_section(
    invocation: LlmInvocation,
    *,
    resolver_event: OperationsObservedEvent | None,
    run_context: dict[str, str],
) -> OperationsKeyValueSectionModel:
    if resolver_event is None:
        return OperationsKeyValueSectionModel(
            id="resolver",
            title="Resolver Decision",
            items=(
                OperationsKeyValueItemModel("Requested", "-"),
                OperationsKeyValueItemModel("Resolved", invocation.llm_id),
                OperationsKeyValueItemModel("Strategy", "-"),
                OperationsKeyValueItemModel("Run ID", run_context.get("run_id", "-")),
            ),
        )
    payload = resolver_event.payload
    bucket = resolver_bucket(resolver_event)
    return OperationsKeyValueSectionModel(
        id="resolver",
        title="Resolver Decision",
        items=(
            OperationsKeyValueItemModel(
                "Requested",
                text_value(payload.get("requested_llm_id")) or "-",
            ),
            OperationsKeyValueItemModel(
                "Resolved",
                text_value(payload.get("resolved_llm_id")) or "-",
                "success" if text_value(payload.get("resolved_llm_id")) else "danger",
            ),
            OperationsKeyValueItemModel(
                "Strategy",
                text_value(payload.get("strategy")) or "-",
            ),
            OperationsKeyValueItemModel(
                "Decision",
                {
                    "agent_default": "Agent Default",
                    "explicit_override": "Explicit Override",
                    "fallback_used": "Fallback Used",
                    "no_match": "No Match / Error",
                }.get(bucket, bucket),
                {
                    "agent_default": "success",
                    "explicit_override": "info",
                    "fallback_used": "warning",
                    "no_match": "danger",
                }.get(bucket, "neutral"),
            ),
            OperationsKeyValueItemModel(
                "Reason",
                text_value(payload.get("reason")) or "-",
                "warning" if text_value(payload.get("reason")) else "neutral",
            ),
            OperationsKeyValueItemModel(
                "Routing Input Blocks",
                optional_int_label(payload.get("routing_input_block_count")),
            ),
            OperationsKeyValueItemModel(
                "Session Replay Window",
                resolver_replay_window_label(payload.get("session_replay_window")),
            ),
            OperationsKeyValueItemModel(
                "Run ID",
                text_value(payload.get("run_id")) or run_context.get("run_id", "-"),
            ),
        ),
    )
