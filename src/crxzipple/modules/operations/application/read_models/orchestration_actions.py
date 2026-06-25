from __future__ import annotations

from crxzipple.modules.operations.application.read_models.models import (
    RuntimeActionModel,
)


def overview_actions() -> tuple[RuntimeActionModel, ...]:
    return (
        _open_run_action(),
        _open_trace_action(),
        _cancel_run_action(),
        _force_release_lane_action(),
    )


def page_actions() -> tuple[RuntimeActionModel, ...]:
    return (
        _open_run_action(),
        _open_trace_action(),
        _cancel_run_action(),
        RuntimeActionModel(
            id="requeue",
            label="Requeue",
            owner="orchestration",
            risk="controlled",
            requires_confirmation=True,
            audit_event="orchestration.run.resume",
            method="POST",
            endpoint="/operations/orchestration/runs/{run_id}/resume",
        ),
        _force_release_lane_action(),
    )


def _open_run_action() -> RuntimeActionModel:
    return RuntimeActionModel(
        id="open_run",
        label="Open Run",
        owner="orchestration",
        kind="navigation",
        method="GET",
        endpoint="/ui/workbench/runs/{run_id}",
    )


def _open_trace_action() -> RuntimeActionModel:
    return RuntimeActionModel(
        id="open_trace",
        label="Open Trace",
        owner="events",
        kind="navigation",
        method="GET",
        endpoint="/workbench/traces/{trace_id}",
    )


def _cancel_run_action() -> RuntimeActionModel:
    return RuntimeActionModel(
        id="cancel_run",
        label="Cancel Run",
        owner="orchestration",
        risk="controlled",
        requires_confirmation=True,
        audit_event="orchestration.run.cancel",
        method="POST",
        endpoint="/operations/orchestration/runs/{run_id}/cancel",
    )


def _force_release_lane_action() -> RuntimeActionModel:
    return RuntimeActionModel(
        id="force_release_lane",
        label="Force Release Lane",
        owner="orchestration",
        risk="dangerous",
        allowed=False,
        disabled_reason=(
            "Lane force-release is not exposed as an operations action; "
            "recover the owning run or worker lease instead."
        ),
        requires_confirmation=True,
        reason_required=True,
    )
