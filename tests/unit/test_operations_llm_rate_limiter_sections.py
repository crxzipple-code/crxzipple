from __future__ import annotations

from datetime import datetime, timedelta, timezone

from crxzipple.modules.llm.domain import (
    LlmApiFamily,
    LlmInputItem,
    LlmInputItemKind,
    LlmInvocation,
    LlmInvocationStatus,
    LlmMessage,
    LlmMessageRole,
    LlmProfile,
    LlmProviderKind,
)
from crxzipple.modules.operations.application.read_models.llm_rate_limiter_sections import (
    execution_blocking_risk_section,
    rate_limiter_section,
)
from crxzipple.modules.operations.application.read_models.llm_limiter_queue_sections import (
    limiter_queue_section,
)
from crxzipple.modules.operations.application.read_models.llm_runtime_metrics import (
    LLM_LIMITER_ACTIVE,
    LLM_LIMITER_WAIT_SECONDS,
    LLM_LIMITER_WAITERS,
)


def _profile() -> LlmProfile:
    return LlmProfile(
        id="openai.gpt",
        provider=LlmProviderKind.OPENAI,
        api_family=LlmApiFamily.OPENAI_RESPONSES,
        model_name="gpt-5",
        context_window_tokens=4096,
        max_concurrency=2,
        concurrency_key="llm:openai",
        timeout_seconds=30,
    )


def _invocation(started_at: datetime) -> LlmInvocation:
    return LlmInvocation(
        id="invocation-running",
        llm_id="openai.gpt",
        status=LlmInvocationStatus.RUNNING,
        messages=(LlmMessage(role=LlmMessageRole.USER, content="hello"),),
        input_items=(
            LlmInputItem(
                kind=LlmInputItemKind.MESSAGE,
                payload={"role": "user", "content": "hello"},
            ),
        ),
        created_at=started_at,
        started_at=started_at,
    )


def _snapshot() -> dict[str, object]:
    return {
        "gauges": [
            {
                "name": LLM_LIMITER_ACTIVE,
                "value": 2,
                "labels": {"llm_id": "openai.gpt", "concurrency_key": "llm:openai"},
            },
            {
                "name": LLM_LIMITER_WAITERS,
                "value": 1,
                "labels": {"llm_id": "openai.gpt", "concurrency_key": "llm:openai"},
            },
        ],
        "timings": [
            {
                "name": LLM_LIMITER_WAIT_SECONDS,
                "count": 2,
                "total_seconds": 6,
                "max_seconds": 5,
                "labels": {"llm_id": "openai.gpt"},
            },
        ],
    }


def test_rate_limiter_sections_project_snapshot_metrics() -> None:
    profile = _profile()

    section = rate_limiter_section([profile], runtime_snapshot=_snapshot())
    queue = limiter_queue_section([profile], runtime_snapshot=_snapshot())

    values = {item.label: item.value for item in section.items}
    assert values["Active"] == "2"
    assert values["Waiting"] == "1"
    assert values["Configured Capacity"] == "2"
    assert values["Avg Wait"] == "3s"

    assert queue.id == "limiter_queue"
    assert queue.rows[0].cells["active"] == "2"
    assert queue.rows[0].cells["waiting"] == "1"
    assert queue.rows[0].cells["reason"] == "waiting for limiter slot"
    assert queue.rows[0].tone == "warning"


def test_execution_blocking_risk_reports_waiters_saturation_and_oldest_running() -> None:
    now = datetime(2026, 6, 21, 12, tzinfo=timezone.utc)
    profile = _profile()
    invocation = _invocation(now - timedelta(seconds=180))

    section = execution_blocking_risk_section(
        [profile],
        active_invocations=[invocation],
        runtime_snapshot=_snapshot(),
        now=now,
    )

    values = {item.label: item.value for item in section.items}
    assert values["Running Invocations"] == "1"
    assert values["Limiter Waiters"] == "1"
    assert values["Saturated Profiles"] == "1"
    assert values["Oldest Running"] == "3m 0s"
