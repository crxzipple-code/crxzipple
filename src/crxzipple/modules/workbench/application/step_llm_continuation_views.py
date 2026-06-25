from __future__ import annotations

from typing import Any

from crxzipple.modules.workbench.application import view_models as models
from crxzipple.modules.orchestration.domain import OrchestrationRun
from crxzipple.modules.orchestration.domain.value_objects import ExecutionStepItemKind
from crxzipple.modules.workbench.application.execution_projection import (
    execution_item_summary,
    request_render_snapshot_id as execution_request_render_snapshot_id,
    summary_bool,
    summary_text,
)
from crxzipple.modules.workbench.application.projection_helpers import optional_text
from crxzipple.modules.workbench.application.step_view_factory import make_step_view


def continuation_decision_step_views(
    run: OrchestrationRun,
    *,
    turn_id: str,
    bundle: Any,
) -> tuple[Any, ...]:
    views: list[Any] = []
    for index, item in enumerate(bundle.items):
        if item.kind is not ExecutionStepItemKind.CONTINUATION_DECISION:
            continue
        summary = execution_item_summary(item)
        request_render_snapshot_id = execution_request_render_snapshot_id(
            run,
            summary=summary,
        )
        reason = summary_text(summary, "reason") or "unknown"
        needs_follow_up = summary_bool(summary, "needs_follow_up")
        end_turn = summary.get("end_turn")
        provider_state = summary.get("provider_continuation_state")
        provider_state = dict(provider_state) if isinstance(provider_state, dict) else {}
        provider_mode = optional_text(provider_state.get("mode"))
        provider_transport = optional_text(provider_state.get("transport"))
        fallback_reason = optional_text(provider_state.get("fallback_reason"))
        if not _continuation_decision_step_is_user_visible(
            reason=reason,
            fallback_reason=fallback_reason,
        ):
            continue
        end_turn_label = (
            f"end_turn={str(end_turn).lower()}"
            if isinstance(end_turn, bool)
            else "end_turn=-"
        )
        follow_up_label = f"follow_up={str(needs_follow_up).lower()}"
        summary_parts = [reason, end_turn_label, follow_up_label]
        if provider_mode is not None:
            summary_parts.append(f"provider={provider_mode}")
        if provider_transport is not None:
            summary_parts.append(f"transport={provider_transport}")
        if fallback_reason is not None:
            summary_parts.append(f"fallback={fallback_reason}")
        views.append(
            make_step_view(
                run=run,
                turn_id=turn_id,
                step_id=f"execution:{bundle.step.id}:continuation:{index}",
                step_type="continuation_decision",
                status="running" if needs_follow_up else "success",
                title="Continuation Decision",
                summary="; ".join(summary_parts),
                started_at=item.created_at,
                completed_at=item.completed_at or bundle.step.completed_at,
                badges=_continuation_decision_badges(
                    needs_follow_up=needs_follow_up,
                    reason=reason,
                    provider_mode=provider_mode,
                    provider_transport=provider_transport,
                    fallback_reason=fallback_reason,
                ),
                llm_invocation_id=summary_text(
                    summary,
                    "llm_invocation_id",
                ),
                request_render_snapshot_id=request_render_snapshot_id,
                trace_step_id=bundle.step.id,
            ),
        )
    return tuple(views)


def _continuation_decision_step_is_user_visible(
    *,
    reason: str,
    fallback_reason: str | None,
) -> bool:
    if fallback_reason is not None:
        return True
    return reason not in {"none", "tool_call", "unknown", ""}


def _continuation_decision_badges(
    *,
    needs_follow_up: bool,
    reason: str,
    provider_mode: str | None,
    provider_transport: str | None,
    fallback_reason: str | None,
) -> tuple[models.StatusBadgeModel, ...]:
    badges = [
        models.StatusBadgeModel(
            label="Follow-up" if needs_follow_up else "End turn",
            tone="info" if needs_follow_up else "success",
        ),
        models.StatusBadgeModel(label=reason, tone="neutral"),
    ]
    if provider_mode is not None:
        badges.append(models.StatusBadgeModel(label=provider_mode, tone="info"))
    if provider_transport is not None:
        badges.append(
            models.StatusBadgeModel(label=provider_transport, tone="neutral"),
        )
    if fallback_reason is not None:
        badges.append(
            models.StatusBadgeModel(label="Continuation fallback", tone="warning"),
        )
    return tuple(badges)
