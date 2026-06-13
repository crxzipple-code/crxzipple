from __future__ import annotations

from types import SimpleNamespace

from crxzipple.modules.orchestration.application.loop_regression_baseline import (
    build_loop_regression_baseline,
)
from crxzipple.modules.orchestration.domain.value_objects import (
    ExecutionStepItemKind,
    OrchestrationRunStatus,
)


def test_loop_regression_baseline_extracts_run_metrics() -> None:
    run = SimpleNamespace(
        id="run-flight",
        status=OrchestrationRunStatus.COMPLETED,
        metadata={
            "repeated_probe_observation": {
                "repeated_count": 2,
                "repeated": [{"target": "www.ceair.com/app.js", "count": 3}],
            },
        },
        result_payload={
            "verified_facts": ["Observed flight search result page."],
            "gaps": ["Fare may change."],
        },
    )
    chain = SimpleNamespace(id="chain-1")
    steps = [
        SimpleNamespace(id="step-1", step_index=1),
        SimpleNamespace(id="step-2", step_index=2),
        SimpleNamespace(id="step-3", step_index=3),
    ]
    items_by_step = {
        "step-1": [
            SimpleNamespace(
                step_id="step-1",
                kind=ExecutionStepItemKind.LLM_INVOCATION,
                summary_payload={
                    "llm_invocation_id": "llm-1",
                    "assistant_progress_item_ids": ["item-progress-1"],
                    "assistant_progress_text": "我先检查页面状态。",
                    "tool_call_session_item_ids": ["item-tool-call-1"],
                    "tool_call_names": ["browser.observe"],
                },
            ),
        ],
        "step-2": [
            SimpleNamespace(
                step_id="step-2",
                kind=ExecutionStepItemKind.TOOL_CALL,
                summary_payload={
                    "tool_id": "browser.observe",
                    "tool_name": "browser.observe",
                    "endpoint": "/portal/v3/shopping/briefInfo",
                },
            ),
            SimpleNamespace(
                step_id="step-2",
                kind=ExecutionStepItemKind.TOOL_RUN,
                summary_payload={
                    "tool_id": "browser.observe",
                    "tool_name": "browser.observe",
                    "status": "completed",
                },
            ),
        ],
        "step-3": [
            SimpleNamespace(
                step_id="step-3",
                kind=ExecutionStepItemKind.LLM_INVOCATION,
                summary_payload={
                    "llm_invocation_id": "llm-2",
                    "tool_call_names": ["web.fetch_json"],
                },
            ),
            SimpleNamespace(
                step_id="step-3",
                kind=ExecutionStepItemKind.TOOL_CALL,
                summary_payload={
                    "tool_id": "web.fetch_json",
                    "tool_name": "web.fetch_json",
                    "validation_result": {"status": "ok"},
                },
            ),
        ],
    }
    query = _FakeLoopRegressionQuery(
        run=run,
        chains=[chain],
        steps_by_chain={"chain-1": steps},
        items_by_step=items_by_step,
    )

    baseline = build_loop_regression_baseline(
        query,
        run_id="run-flight",
        task_label="flight regression",
    )

    assert baseline == {
        "task": "flight regression",
        "run_id": "run-flight",
        "status": "completed",
        "orchestration_steps": 3,
        "ui_steps": 2,
        "llm_calls": 2,
        "tool_calls": 2,
        "llm_text_tool_call_steps": 1,
        "llm_tool_only_steps": 1,
        "max_consecutive_llm_tool_only_steps": 1,
        "current_consecutive_llm_tool_only_steps": 1,
        "tool_only_loop_suspected": False,
        "assistant_progress_item_count": 1,
        "tool_call_session_item_count": 1,
        "assistant_progress_item_ids": ["item-progress-1"],
        "tool_call_session_item_ids": ["item-tool-call-1"],
        "progress_without_tool_call_items": False,
        "repeated_target_count": 2,
        "first_endpoint_discovery_step": 2,
        "first_candidate_validation_step": 3,
        "candidate_discovery_to_validation_delta": 1,
        "completed_cancelled_failed": "completed",
        "final_answer_has_verified_facts": True,
        "final_answer_has_gaps": True,
        "metrics_missing": [],
        "repeated_probe_observation": {
            "repeated_count": 2,
            "repeated": [{"target": "www.ceair.com/app.js", "count": 3}],
        },
    }


def test_loop_regression_baseline_flags_consecutive_tool_only_steps() -> None:
    run = SimpleNamespace(
        id="run-tool-only",
        status=OrchestrationRunStatus.RUNNING,
        metadata={},
        result_payload=None,
    )
    chain = SimpleNamespace(id="chain-1")
    steps = [
        SimpleNamespace(id=f"step-{index}", step_index=index)
        for index in range(1, 5)
    ]
    items_by_step = {
        step.id: [
            SimpleNamespace(
                step_id=step.id,
                kind=ExecutionStepItemKind.LLM_INVOCATION,
                summary_payload={
                    "llm_invocation_id": f"llm-{step.step_index}",
                    "tool_call_names": ["exec"],
                    "tool_call_session_item_ids": [f"item-tool-call-{step.step_index}"],
                },
            ),
        ]
        for step in steps
    }
    query = _FakeLoopRegressionQuery(
        run=run,
        chains=[chain],
        steps_by_chain={"chain-1": steps},
        items_by_step=items_by_step,
    )

    baseline = build_loop_regression_baseline(query, run_id="run-tool-only")

    assert baseline["llm_tool_only_steps"] == 4
    assert baseline["max_consecutive_llm_tool_only_steps"] == 4
    assert baseline["current_consecutive_llm_tool_only_steps"] == 4
    assert baseline["tool_only_loop_suspected"] is True


class _FakeLoopRegressionQuery:
    def __init__(
        self,
        *,
        run: object,
        chains: list[object],
        steps_by_chain: dict[str, list[object]],
        items_by_step: dict[str, list[object]],
    ) -> None:
        self._run = run
        self._chains = chains
        self._steps_by_chain = steps_by_chain
        self._items_by_step = items_by_step

    def get_run(self, run_id: str) -> object:
        assert run_id == self._run.id
        return self._run

    def list_execution_chains(self, turn_id: str) -> list[object]:
        assert turn_id == self._run.id
        return self._chains

    def list_execution_steps(self, chain_id: str) -> list[object]:
        return self._steps_by_chain.get(chain_id, [])

    def list_execution_step_items(self, step_id: str) -> list[object]:
        return self._items_by_step.get(step_id, [])
