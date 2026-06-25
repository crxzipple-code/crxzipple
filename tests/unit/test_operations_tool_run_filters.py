from __future__ import annotations

from datetime import datetime, timedelta, timezone

from crxzipple.modules.operations.application.read_models.tool_run_filters import (
    dedupe_tool_runs,
    filter_tool_runs,
)
from crxzipple.modules.operations.application.read_models.tool_run_query import (
    ToolOperationsQuery,
    normalize_tool_operations_query,
    paginate_tool_runs,
    tool_runs_empty_state,
)
from crxzipple.modules.operations.application.read_models.tool_run_time import (
    tool_run_duration_seconds,
    tool_run_time,
)
from crxzipple.modules.tool.domain import (
    ToolEnvironment,
    ToolExecutionStrategy,
    ToolExecutionTarget,
    ToolMode,
    ToolRun,
    ToolRunResult,
)


def _run(run_id: str, tool_id: str = "tool.weather") -> ToolRun:
    return ToolRun.create(
        run_id=run_id,
        tool_id=tool_id,
        call_id=f"call-{run_id}",
        function_id=tool_id,
        source_id="source.local",
        input_payload={},
        target=ToolExecutionTarget(
            mode=ToolMode.INLINE,
            strategy=ToolExecutionStrategy.ASYNC,
            environment=ToolEnvironment.LOCAL,
        ),
    )


def test_tool_operations_query_normalization_bounds_filters_and_paging() -> None:
    normalized = normalize_tool_operations_query(
        ToolOperationsQuery(
            status="unknown",
            time_window="week",
            search=f" {'x' * 140} ",
            provider=" Provider:OpenAI ",
            mode="missing",
            strategy="missing",
            environment="missing",
            has_artifact="maybe",
            retryable="maybe",
            limit=999,
            offset=-10,
        ),
    )

    assert normalized.status == "all"
    assert normalized.time_window == "all"
    assert normalized.provider == "provider:openai"
    assert normalized.mode == "all"
    assert normalized.strategy == "all"
    assert normalized.environment == "all"
    assert normalized.has_artifact == "all"
    assert normalized.retryable == "all"
    assert len(normalized.search) == 120
    assert normalized.search.endswith("...")
    assert normalized.limit == 200
    assert normalized.offset == 0


def test_tool_run_filters_apply_status_provider_search_artifact_and_retry_rules() -> None:
    now = datetime.now(timezone.utc)
    failed = _run("run-failed", tool_id="tool.flight")
    failed.start()
    failed.fail("provider timeout")
    succeeded = _run("run-succeeded")
    succeeded.start()
    succeeded.succeed(ToolRunResult.text("ok"))
    queued = _run("run-queued")

    runs = [failed, succeeded, queued]
    provider_keys = {
        "tool.flight": "provider:eastern",
        "tool.weather": "provider:weather",
    }
    search_text = {
        "run-failed": "run-failed tool.flight eastern provider timeout",
        "run-succeeded": "run-succeeded tool.weather weather",
        "run-queued": "run-queued tool.weather weather",
    }

    filtered = filter_tool_runs(
        runs,
        query=ToolOperationsQuery(
            status="failed",
            provider="provider:eastern",
            search="timeout",
            has_artifact="yes",
            retryable="yes",
        ),
        assignment_by_run={},
        provider_key_by_tool_id=provider_keys,
        artifact_run_ids={"run-failed"},
        search_text_by_run_id=search_text,
        now=now,
        long_running_seconds=300,
    )

    assert filtered == [failed]
    assert tool_run_time(failed) == failed.completed_at
    assert tool_run_duration_seconds(failed, now=now) >= 0


def test_tool_run_filters_support_time_window_pagination_dedupe_and_empty_state() -> None:
    now = datetime.now(timezone.utc)
    recent = _run("run-recent")
    recent.created_at = now - timedelta(hours=2)
    old = _run("run-old")
    old.created_at = now - timedelta(days=2)

    filtered = filter_tool_runs(
        [old, recent],
        query=ToolOperationsQuery(time_window="24h"),
        assignment_by_run={},
        provider_key_by_tool_id={"tool.weather": "provider:weather"},
        artifact_run_ids=set(),
        search_text_by_run_id={"run-old": "old", "run-recent": "recent"},
        now=now,
        long_running_seconds=300,
    )

    assert filtered == [recent]
    assert paginate_tool_runs([recent, old], query=ToolOperationsQuery(limit=1)) == [
        recent
    ]
    assert dedupe_tool_runs((recent, recent, old)) == [recent, old]
    assert tool_runs_empty_state(ToolOperationsQuery()) == "No tool runs recorded."
    assert (
        tool_runs_empty_state(ToolOperationsQuery(search="flight"))
        == "No tool runs match the current filters."
    )
