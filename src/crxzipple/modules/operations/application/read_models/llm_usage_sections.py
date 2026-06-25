from __future__ import annotations

from collections import Counter, defaultdict

from crxzipple.modules.llm.domain import LlmInvocation, LlmInvocationStatus, LlmProfile
from crxzipple.modules.operations.application.read_models.llm_invocation_facts import (
    duration_seconds,
    invocation_input_tokens,
    metadata_int,
)
from crxzipple.modules.operations.application.read_models.models import (
    OperationsChartSectionModel,
    OperationsChartSegmentModel,
)
from crxzipple.modules.operations.application.read_models.presenters import (
    status_tone,
)


def latency_section(
    invocations: list[LlmInvocation],
    *,
    profiles_by_id: dict[str, LlmProfile],
) -> OperationsChartSectionModel:
    durations_by_provider: dict[str, list[float]] = defaultdict(list)
    for invocation in invocations:
        if invocation.status is not LlmInvocationStatus.SUCCEEDED:
            continue
        duration = duration_seconds(invocation)
        if duration is None:
            continue
        profile = profiles_by_id.get(invocation.llm_id)
        key = profile.provider.value if profile is not None else invocation.llm_id
        durations_by_provider[key].append(duration)
    provider_averages = {
        key: sum(values) / len(values) for key, values in durations_by_provider.items()
    }
    total_average = (
        sum(provider_averages.values()) / len(provider_averages)
        if provider_averages
        else 0
    )
    return OperationsChartSectionModel(
        id="latency",
        title="Latency",
        kind="bar",
        total=int(total_average * 1000),
        segments=tuple(
            OperationsChartSegmentModel(
                id=provider,
                label=provider,
                value=int(seconds * 1000),
                tone=_chart_tone(index),
            )
            for index, (provider, seconds) in enumerate(
                sorted(provider_averages.items()),
            )
        ),
    )


def token_usage_section(invocations: list[LlmInvocation]) -> OperationsChartSectionModel:
    input_tokens = 0
    output_tokens = 0
    reasoning_tokens = 0
    total_tokens = 0
    for invocation in invocations:
        if invocation.result is None or invocation.result.usage is None:
            continue
        usage = invocation.result.usage
        input_tokens += usage.input_tokens or 0
        output_tokens += usage.output_tokens or 0
        reasoning_tokens += usage.reasoning_tokens or 0
        total_tokens += (
            usage.total_tokens
            if usage.total_tokens is not None
            else (usage.input_tokens or 0) + (usage.output_tokens or 0)
        )
    unclassified = max(total_tokens - input_tokens - output_tokens - reasoning_tokens, 0)
    values = (
        ("input", "Input", input_tokens, "info"),
        ("output", "Output", output_tokens, "success"),
        ("reasoning", "Reasoning", reasoning_tokens, "warning"),
        ("unclassified", "Unclassified", unclassified, "neutral"),
    )
    return OperationsChartSectionModel(
        id="token_usage",
        title="Token Usage",
        kind="donut",
        total=total_tokens,
        segments=tuple(
            OperationsChartSegmentModel(id=id_, label=label, value=value, tone=tone)
            for id_, label, value, tone in values
            if value
        ),
    )


def invocation_rate_section(
    invocations: list[LlmInvocation],
) -> OperationsChartSectionModel:
    counts = Counter(invocation.status.value for invocation in invocations)
    return OperationsChartSectionModel(
        id="invocation_rate",
        title="Invocation Rate",
        kind="donut",
        total=sum(counts.values()),
        segments=tuple(
            OperationsChartSegmentModel(
                id=status,
                label=_status_label(status),
                value=counts[status],
                tone=_status_tone(status),
            )
            for status in ("running", "succeeded", "failed", "created")
            if counts[status]
        ),
    )


def context_pressure_section(
    invocations: list[LlmInvocation],
    *,
    profiles_by_id: dict[str, LlmProfile],
) -> OperationsChartSectionModel:
    counts: Counter[str] = Counter()
    for invocation in invocations:
        profile = profiles_by_id.get(invocation.llm_id)
        if profile is None or not profile.context_window_tokens:
            continue
        input_tokens = invocation_input_tokens(invocation) or metadata_int(
            invocation,
            "estimated_provider_input_tokens",
        )
        if input_tokens <= 0:
            continue
        ratio = input_tokens / profile.context_window_tokens
        if ratio >= 0.9:
            counts["high"] += 1
        elif ratio >= 0.8:
            counts["elevated"] += 1
        else:
            counts["normal"] += 1
    return OperationsChartSectionModel(
        id="context_pressure",
        title="Context Window Pressure",
        kind="donut",
        total=sum(counts.values()),
        segments=tuple(
            OperationsChartSegmentModel(id=id_, label=label, value=counts[id_], tone=tone)
            for id_, label, tone in (
                ("normal", "<80%", "success"),
                ("elevated", "80-90%", "warning"),
                ("high", ">90%", "danger"),
            )
            if counts[id_]
        ),
    )


def _status_label(status: str) -> str:
    return {
        "created": "Created",
        "running": "Running",
        "succeeded": "Succeeded",
        "failed": "Failed",
    }.get(status, status)


def _status_tone(status: str) -> str:
    return status_tone(
        status,
        danger=frozenset({"failed"}),
        warning=frozenset(),
        success=frozenset({"succeeded"}),
        info=frozenset({"running"}),
    )


def _chart_tone(index: int) -> str:
    return ("info", "success", "warning", "danger", "neutral")[index % 5]
