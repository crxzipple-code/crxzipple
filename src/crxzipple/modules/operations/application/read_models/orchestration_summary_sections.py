from __future__ import annotations

from datetime import datetime
from typing import Any

from crxzipple.modules.orchestration.domain import (
    OrchestrationIngressRequest,
    OrchestrationRun,
)
from crxzipple.modules.operations.application.read_models.models import (
    MetricCardModel,
)
from crxzipple.modules.operations.application.read_models.orchestration_metrics import (
    average_latency_label,
    failed_metric,
    health_delta_value,
    health_label_value,
    health_tone_value,
    ingress_rate_label,
)
from crxzipple.modules.operations.application.read_models.orchestration_observation_metrics import (
    observation_metric,
)


def overview_metrics(
    *,
    health: str,
    visible_ingress_count: int,
    ingress_requests: list[OrchestrationIngressRequest],
    running_runs: list[OrchestrationRun],
    waiting_runs: list[OrchestrationRun],
    queued_runs: list[OrchestrationRun],
    available_executor_slots: int,
    online_executor_count: int,
    inflight_executor_count: int,
    executor_capacity: int,
    failed_runs: list[OrchestrationRun],
    recent_failed_runs: list[OrchestrationRun],
    now: datetime,
) -> tuple[MetricCardModel, ...]:
    return (
        MetricCardModel(
            id="health",
            label="Overall Health",
            value=health_label_value(health),
            delta=health_delta_value(health),
            tone=health_tone_value(health),
        ),
        MetricCardModel(
            id="ingress",
            label="Ingress Queue",
            value=str(visible_ingress_count),
            delta="ingress requests",
            tone="neutral",
        ),
        MetricCardModel(
            id="ingress_rate",
            label="Ingress Rate",
            value=ingress_rate_label(
                ingress_requests,
                fallback_runs=[],
                now=now,
            ),
            delta="requests/sec",
            tone="info",
        ),
        MetricCardModel(
            id="active",
            label="Active Runs",
            value=str(len(running_runs)),
            delta=f"{len(waiting_runs)} waiting",
            tone="info",
        ),
        MetricCardModel(
            id="run_queue",
            label="Run Queue",
            value=str(len(queued_runs)),
            delta=f"{available_executor_slots} executor slots available",
            tone="warning" if queued_runs else "success",
        ),
        MetricCardModel(
            id="executor_capacity",
            label="Executor Capacity",
            value=f"{inflight_executor_count}/{executor_capacity}",
            delta=f"{online_executor_count} online workers",
            tone="success" if available_executor_slots else "warning",
        ),
        failed_metric(
            failed_runs=failed_runs,
            recent_failed_runs=recent_failed_runs,
            cancelled_runs=[],
        ),
    )


def page_metrics(
    *,
    health: str,
    visible_ingress_count: int,
    ingress_requests: list[OrchestrationIngressRequest],
    running_runs: list[OrchestrationRun],
    waiting_runs: list[OrchestrationRun],
    queued_runs: list[OrchestrationRun],
    backpressure_total: int,
    approval_waiting_count: int,
    failed_runs: list[OrchestrationRun],
    recent_failed_runs: list[OrchestrationRun],
    cancelled_runs: list[OrchestrationRun],
    runs: list[OrchestrationRun],
    observer_state: Any | None,
    now: datetime,
) -> tuple[MetricCardModel, ...]:
    return (
        MetricCardModel(
            id="health",
            label="Overall Health",
            value=health_label_value(health),
            delta=health_delta_value(health),
            tone=health_tone_value(health),
        ),
        MetricCardModel(
            id="ingress",
            label="Ingress Queue",
            value=str(visible_ingress_count),
            delta="ingress requests",
            tone="neutral",
        ),
        MetricCardModel(
            id="ingress_rate",
            label="Ingress Rate",
            value=ingress_rate_label(
                ingress_requests,
                fallback_runs=[],
                now=now,
            ),
            delta="requests/sec",
            tone="info",
        ),
        MetricCardModel(
            id="active",
            label="Active Runs",
            value=str(len(running_runs)),
            delta=f"{len(waiting_runs)} waiting",
            tone="info",
        ),
        MetricCardModel(
            id="run_queue",
            label="Run Queue",
            value=str(len(queued_runs)),
            delta=f"{len(waiting_runs)} waiting",
            tone="warning" if queued_runs else "success",
        ),
        MetricCardModel(
            id="backpressure",
            label="Backpressure",
            value=str(backpressure_total),
            delta="Waiting runs",
            tone="warning" if backpressure_total else "success",
        ),
        MetricCardModel(
            id="approval_waiting",
            label="Approval Waiting",
            value=str(approval_waiting_count),
            delta="Monitoring only",
            tone="warning" if approval_waiting_count else "success",
        ),
        failed_metric(
            failed_runs=failed_runs,
            recent_failed_runs=recent_failed_runs,
            cancelled_runs=cancelled_runs,
        ),
        MetricCardModel(
            id="latency",
            label="Average Latency",
            value=average_latency_label(
                runs,
                running_runs=running_runs,
                now=now,
            ),
            delta="avg runtime",
            tone="info",
        ),
        observation_metric(observer_state),
    )
