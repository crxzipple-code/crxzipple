from __future__ import annotations

from typing import Any

from crxzipple.modules.operations.application.read_models.diagnostics import (
    build_loop_regression_baseline,
)
from crxzipple.modules.orchestration.application.ports import OrchestrationRunQueryPort
from crxzipple.modules.orchestration.domain import OrchestrationRun
from crxzipple.modules.workbench.application import view_models as models
from crxzipple.modules.workbench.application.projection_helpers import (
    optional_int,
    optional_text,
)
from crxzipple.modules.workbench.application.run_display_values import key_value


def loop_health_for_workbench(
    run_query: OrchestrationRunQueryPort,
    run: OrchestrationRun,
    *,
    llm_invocations: tuple[Any, ...],
) -> dict[str, object] | None:
    try:
        baseline = build_loop_regression_baseline(
            run_query,
            run_id=run.id,
            response_item_resolver=_response_item_resolver_from_invocations(
                llm_invocations,
            ),
        )
    except Exception:
        return None
    loop_health = baseline.get("loop_health")
    return loop_health if isinstance(loop_health, dict) else None


def _response_item_resolver_from_invocations(
    llm_invocations: tuple[Any, ...],
):
    response_items_by_id: dict[str, Any] = {}
    for invocation in llm_invocations:
        for response_item in tuple(getattr(invocation, "response_items", ()) or ()):
            item_id = optional_text(getattr(response_item, "id", None))
            if item_id is not None:
                response_items_by_id[item_id] = response_item

    def _resolve(item_id: str) -> Any | None:
        return response_items_by_id.get(item_id)

    return _resolve


def loop_health_section(
    loop_health: dict[str, object] | None,
):
    if loop_health is None:
        return models.WorkbenchKeyValueSection(
            id="loop_health",
            title="Loop Health",
            items=(key_value("Status", "unavailable", tone="neutral"),),
        )
    warnings = [
        warning
        for warning in loop_health.get("warnings", [])
        if isinstance(warning, str) and warning.strip()
    ]
    warning_text = ", ".join(warnings) if warnings else "none"
    warning_tone = "warning" if warnings else "success"
    max_streak = optional_int(loop_health.get("max_tool_only_streak")) or 0
    current_streak = optional_int(loop_health.get("current_tool_only_streak")) or 0
    validation_delta = loop_health.get("validation_delta")
    validation_delta_text = (
        str(validation_delta) if isinstance(validation_delta, int) else "-"
    )
    validation_lag = bool(loop_health.get("validation_lag_suspected"))
    segment_count = len(
        [
            segment
            for segment in loop_health.get("tool_only_streak_segments", [])
            if isinstance(segment, dict)
        ],
    )
    return models.WorkbenchKeyValueSection(
        id="loop_health",
        title="Loop Health",
        items=(
            key_value("Warnings", warning_text, tone=warning_tone),
            key_value("Max tool-only streak", str(max_streak)),
            key_value("Current tool-only streak", str(current_streak)),
            key_value("Tool-only segments", str(segment_count)),
            key_value(
                "Validation delta",
                validation_delta_text,
                tone="warning" if validation_lag else "neutral",
            ),
            key_value(
                "Validation lag",
                "yes" if validation_lag else "no",
                tone="warning" if validation_lag else "success",
            ),
        ),
    )
