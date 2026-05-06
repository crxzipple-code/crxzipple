from __future__ import annotations

import time
import unittest
from types import SimpleNamespace

from crxzipple.modules.orchestration.application import OrchestrationExecutorService
from crxzipple.shared.runtime_metrics import RuntimeMetricsRegistry


def _executor_service_for_metrics(metrics: RuntimeMetricsRegistry) -> OrchestrationExecutorService:
    return OrchestrationExecutorService(
        uow_factory=lambda: SimpleNamespace(),
        events_service=None,
        worker_lease_seconds=30,
        lease_manager=SimpleNamespace(),
        admit_assignment_fn=lambda **kwargs: None,
        advance_once_fn=lambda **kwargs: None,
        next_assigned_assignment_fn=lambda **kwargs: None,
        process_assigned_assignment_fn=lambda **kwargs: None,
        process_assigned_assignment_async_fn=lambda **kwargs: None,
        process_next_assigned_assignment_fn=lambda **kwargs: None,
        heartbeat_assignment_fn=lambda *args, **kwargs: None,
        advance_assignment_fn=lambda data: None,
        wait_assignment_on_tool_fn=lambda data: None,
        complete_assignment_fn=lambda data: None,
        fail_assignment_fn=lambda data: None,
        metrics=metrics,
    )


class RuntimeMetricsTestCase(unittest.TestCase):
    def test_runtime_metrics_registry_records_counters_gauges_and_timings(self) -> None:
        metrics = RuntimeMetricsRegistry()

        metrics.increment_counter(
            "orchestration.executor.assignment_completions",
            labels={"worker_id": "executor-1"},
        )
        metrics.set_gauge(
            "orchestration.executor.active_assignments",
            2,
            labels={"worker_id": "executor-1"},
        )
        with metrics.timed(
            "orchestration.executor.assignment_seconds",
            labels={"worker_id": "executor-1"},
        ):
            time.sleep(0.001)

        snapshot = metrics.snapshot(prefixes=("orchestration.",))

        self.assertEqual(
            snapshot["counters"],
            [
                {
                    "name": "orchestration.executor.assignment_completions",
                    "labels": {"worker_id": "executor-1"},
                    "value": 1,
                },
            ],
        )
        self.assertEqual(
            snapshot["gauges"],
            [
                {
                    "name": "orchestration.executor.active_assignments",
                    "labels": {"worker_id": "executor-1"},
                    "value": 2.0,
                },
            ],
        )
        timing = snapshot["timings"][0]
        self.assertEqual(timing["name"], "orchestration.executor.assignment_seconds")
        self.assertEqual(timing["labels"], {"worker_id": "executor-1"})
        self.assertEqual(timing["count"], 1)
        self.assertGreater(timing["total_seconds"], 0)

    def test_orchestration_executor_snapshot_includes_llm_limiter_metrics(self) -> None:
        metrics = RuntimeMetricsRegistry()
        metrics.set_gauge(
            "llm.profile_limiter.active",
            1,
            labels={"llm_id": "vllm.qwen3.5-35b"},
        )
        metrics.set_gauge("unrelated.metric", 99)
        service = _executor_service_for_metrics(metrics)

        snapshot = service.runtime_metrics_snapshot()

        self.assertEqual(
            snapshot["gauges"],
            [
                {
                    "name": "llm.profile_limiter.active",
                    "labels": {"llm_id": "vllm.qwen3.5-35b"},
                    "value": 1.0,
                },
            ],
        )
