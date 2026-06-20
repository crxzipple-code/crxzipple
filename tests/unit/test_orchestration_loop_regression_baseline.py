from __future__ import annotations

from types import SimpleNamespace

from crxzipple.modules.operations.application.read_models.diagnostics import (
    build_loop_regression_baseline,
)
from crxzipple.modules.llm.domain.value_objects import (
    LlmResponseItem,
    LlmResponseItemKind,
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
                    "llm_request_input": {
                        "input_mode": "runtime_transcript",
                        "input_item_count": 4,
                    },
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
                    "llm_request_input": {
                        "input_mode": "runtime_transcript",
                        "input_item_count": 2,
                    },
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
        "loop_health": {
            "tool_only_loop_suspected": False,
            "tool_only_streak_warning_threshold": 3,
            "max_tool_only_streak": 1,
            "current_tool_only_streak": 1,
            "tool_only_streak_segments": [
                {
                    "start_step_index": 3,
                    "end_step_index": 3,
                    "start_llm_item_id": "",
                    "end_llm_item_id": "",
                    "length": 1,
                },
            ],
            "validation_delta": 1,
            "validation_delta_warning_threshold": 8,
            "validation_lag_suspected": False,
            "warnings": [],
        },
        "llm_response_item_count": 0,
        "llm_reasoning_response_item_count": 0,
        "llm_reasoning_text_item_count": 0,
        "llm_assistant_message_response_item_count": 0,
        "llm_tool_call_response_item_count": 0,
        "llm_response_item_missing_count": 0,
        "llm_request_input_mode_counts": {
            "runtime_transcript": 2,
        },
        "llm_request_input_missing_count": 0,
        "llm_request_input_item_count": 6,
        "llm_runtime_transcript_steps": 2,
        "llm_runtime_transcript_item_count": 6,
        "assistant_progress_item_count": 1,
        "tool_call_session_item_count": 1,
        "assistant_progress_item_ids": ["item-progress-1"],
        "tool_call_session_item_ids": ["item-tool-call-1"],
        "progress_without_tool_call_items": False,
        "tool_result_items": 0,
        "tool_result_summary_count": 0,
        "tool_result_exit_code_count": 0,
        "tool_result_read_handle_count": 0,
        "tool_result_truncated_count": 0,
        "repeated_target_count": 2,
        "first_endpoint_discovery_step": 2,
        "first_candidate_validation_step": 3,
        "candidate_discovery_to_validation_delta": 1,
        "completed_cancelled_failed": "completed",
        "final_answer_has_verified_facts": True,
        "final_answer_has_gaps": True,
        "final_answer_has_unavailable_evidence": False,
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
    assert baseline["loop_health"]["warnings"] == [
        "tool_only_streak",
    ]
    assert baseline["loop_health"]["tool_only_streak_segments"] == [
        {
            "start_step_index": 1,
            "end_step_index": 4,
            "start_llm_item_id": "",
            "end_llm_item_id": "",
            "length": 4,
        },
    ]


def test_loop_regression_baseline_flags_candidate_validation_lag() -> None:
    run = SimpleNamespace(
        id="run-validation-lag",
        status=OrchestrationRunStatus.RUNNING,
        metadata={},
        result_payload=None,
    )
    chain = SimpleNamespace(id="chain-1")
    steps = [
        SimpleNamespace(id=f"step-{index}", step_index=index)
        for index in range(1, 14)
    ]
    items_by_step = {
        "step-2": [
            SimpleNamespace(
                step_id="step-2",
                kind=ExecutionStepItemKind.TOOL_RESULT,
                summary_payload={
                    "tool_name": "exec",
                    "endpoint": "/m-base/sale/shoppingv2",
                },
            ),
        ],
        "step-13": [
            SimpleNamespace(
                step_id="step-13",
                kind=ExecutionStepItemKind.TOOL_RESULT,
                summary_payload={
                    "tool_name": "exec",
                    "validation_result": {"status": "blocked"},
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
        run_id="run-validation-lag",
    )

    assert baseline["candidate_discovery_to_validation_delta"] == 11
    assert baseline["loop_health"]["validation_lag_suspected"] is True
    assert baseline["loop_health"]["warnings"] == ["validation_lag"]


def test_loop_regression_baseline_tracks_codex_like_long_chain_tool_results() -> None:
    run = SimpleNamespace(
        id="run-codex-like",
        status=OrchestrationRunStatus.FAILED,
        metadata={},
        result_payload={
            "verified_facts": ["Endpoint and encrypted request shape reproduced."],
            "remaining_gaps": ["Live fare is unavailable behind WAF."],
        },
    )
    chain = SimpleNamespace(id="chain-1")
    steps = [
        SimpleNamespace(id=f"step-{index}", step_index=index)
        for index in range(1, 6)
    ]
    items_by_step = {
        "step-1": [
            SimpleNamespace(
                step_id="step-1",
                kind=ExecutionStepItemKind.LLM_INVOCATION,
                summary_payload={
                    "llm_invocation_id": "llm-1",
                    "assistant_progress_item_ids": ["progress-1"],
                    "assistant_progress_text": "I will inspect the mobile site bundle.",
                    "tool_call_session_item_ids": ["call-1"],
                    "tool_call_names": ["exec"],
                },
            ),
        ],
        "step-2": [
            SimpleNamespace(
                step_id="step-2",
                kind=ExecutionStepItemKind.TOOL_CALL,
                summary_payload={
                    "tool_id": "exec",
                    "tool_name": "exec",
                    "command": "python inspect_bundle.py",
                },
            ),
            SimpleNamespace(
                step_id="step-2",
                kind=ExecutionStepItemKind.TOOL_RESULT,
                summary_payload={
                    "tool_id": "exec",
                    "tool_name": "exec",
                    "result_summary": "exit 0: found shoppingv2 endpoint",
                    "exit_code": 0,
                    "output_truncated": True,
                    "read_handles": [
                        {
                            "kind": "raw_output_block",
                            "name": "stdout",
                        },
                    ],
                },
            ),
        ],
        "step-3": [
            SimpleNamespace(
                step_id="step-3",
                kind=ExecutionStepItemKind.LLM_INVOCATION,
                summary_payload={
                    "llm_invocation_id": "llm-2",
                    "assistant_progress_item_ids": ["progress-2"],
                    "assistant_progress_text": "The endpoint is found; next I will replay it.",
                    "tool_call_session_item_ids": ["call-2"],
                    "tool_call_names": ["exec"],
                },
            ),
        ],
        "step-4": [
            SimpleNamespace(
                step_id="step-4",
                kind=ExecutionStepItemKind.TOOL_CALL,
                summary_payload={
                    "tool_id": "exec",
                    "tool_name": "exec",
                    "validation_result": {"status": "blocked"},
                },
            ),
            SimpleNamespace(
                step_id="step-4",
                kind=ExecutionStepItemKind.TOOL_RESULT,
                summary_payload={
                    "tool_id": "exec",
                    "tool_name": "exec",
                    "result_summary": "exit 0: WAF challenge response observed",
                    "exit_code": 0,
                    "read_handles": [
                        {
                            "kind": "raw_output_block",
                            "name": "stdout",
                        },
                    ],
                },
            ),
        ],
        "step-5": [
            SimpleNamespace(
                step_id="step-5",
                kind=ExecutionStepItemKind.LLM_INVOCATION,
                summary_payload={
                    "llm_invocation_id": "llm-3",
                    "assistant_progress_item_ids": ["progress-3"],
                    "assistant_progress_text": "I will stop without inventing fare data.",
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
        run_id="run-codex-like",
        task_label="codex-like flight smoke",
    )

    assert baseline["status"] == "failed"
    assert baseline["llm_calls"] == 3
    assert baseline["tool_calls"] == 2
    assert baseline["llm_text_tool_call_steps"] == 2
    assert baseline["llm_tool_only_steps"] == 0
    assert baseline["tool_only_loop_suspected"] is False
    assert baseline["assistant_progress_item_count"] == 3
    assert baseline["tool_result_items"] == 2
    assert baseline["tool_result_summary_count"] == 2
    assert baseline["tool_result_exit_code_count"] == 2
    assert baseline["tool_result_read_handle_count"] == 2
    assert baseline["tool_result_truncated_count"] == 1
    assert baseline["first_endpoint_discovery_step"] == 2
    assert baseline["first_candidate_validation_step"] == 4
    assert baseline["candidate_discovery_to_validation_delta"] == 2
    assert baseline["loop_health"]["warnings"] == []
    assert baseline["final_answer_has_verified_facts"] is True
    assert baseline["final_answer_has_gaps"] is True
    assert baseline["final_answer_has_unavailable_evidence"] is True
    assert baseline["metrics_missing"] == []


def test_loop_regression_baseline_uses_response_items_for_tool_only_detection() -> None:
    run = SimpleNamespace(
        id="run-response-items",
        status=OrchestrationRunStatus.RUNNING,
        metadata={},
        result_payload=None,
    )
    chain = SimpleNamespace(id="chain-1")
    steps = [
        SimpleNamespace(id="step-1", step_index=1),
        SimpleNamespace(id="step-2", step_index=2),
    ]
    items_by_step = {
        "step-1": [
            SimpleNamespace(
                id="llm-item-1",
                step_id="step-1",
                kind=ExecutionStepItemKind.LLM_INVOCATION,
                summary_payload={
                    "llm_invocation_id": "llm-1",
                    "llm_response_item_ids": ["reasoning-1", "tool-call-1"],
                    "tool_call_names": ["exec"],
                    "tool_call_session_item_ids": ["call-1"],
                },
            ),
        ],
        "step-2": [
            SimpleNamespace(
                id="llm-item-2",
                step_id="step-2",
                kind=ExecutionStepItemKind.LLM_INVOCATION,
                summary_payload={
                    "llm_invocation_id": "llm-2",
                    "llm_response_item_ids": ["reasoning-empty", "tool-call-2"],
                    "tool_call_names": ["exec"],
                    "tool_call_session_item_ids": ["call-2"],
                },
            ),
        ],
    }
    response_items = {
        "reasoning-1": LlmResponseItem(
            id="reasoning-1",
            invocation_id="llm-1",
            sequence_no=1,
            kind=LlmResponseItemKind.REASONING,
            content_payload={
                "summary": [
                    {
                        "type": "summary_text",
                        "text": "I found a candidate endpoint; next I will replay it.",
                    },
                ],
                "text": "I found a candidate endpoint; next I will replay it.",
            },
        ),
        "tool-call-1": LlmResponseItem(
            id="tool-call-1",
            invocation_id="llm-1",
            sequence_no=2,
            kind=LlmResponseItemKind.TOOL_CALL,
            tool_name="exec",
            content_payload={"arguments": {"command": "python inspect.py"}},
        ),
        "reasoning-empty": LlmResponseItem(
            id="reasoning-empty",
            invocation_id="llm-2",
            sequence_no=1,
            kind=LlmResponseItemKind.REASONING,
            content_payload={"summary": [], "text": None},
        ),
        "tool-call-2": LlmResponseItem(
            id="tool-call-2",
            invocation_id="llm-2",
            sequence_no=2,
            kind=LlmResponseItemKind.TOOL_CALL,
            tool_name="exec",
            content_payload={"arguments": {"command": "python retry.py"}},
        ),
    }
    query = _FakeLoopRegressionQuery(
        run=run,
        chains=[chain],
        steps_by_chain={"chain-1": steps},
        items_by_step=items_by_step,
    )

    baseline = build_loop_regression_baseline(
        query,
        run_id="run-response-items",
        response_item_resolver=response_items.get,
    )

    assert baseline["llm_response_item_count"] == 4
    assert baseline["llm_reasoning_response_item_count"] == 2
    assert baseline["llm_reasoning_text_item_count"] == 1
    assert baseline["llm_tool_call_response_item_count"] == 2
    assert baseline["llm_text_tool_call_steps"] == 1
    assert baseline["llm_tool_only_steps"] == 1
    assert baseline["max_consecutive_llm_tool_only_steps"] == 1
    assert baseline["tool_only_loop_suspected"] is False
    assert baseline["loop_health"]["tool_only_streak_segments"] == [
        {
            "start_step_index": 2,
            "end_step_index": 2,
            "start_llm_item_id": "llm-item-2",
            "end_llm_item_id": "llm-item-2",
            "length": 1,
        },
    ]


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
