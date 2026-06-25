from __future__ import annotations

from crxzipple.modules.operations.application.read_models.tool_run_error_diagnostics import (
    error_http_status,
    looks_like_access_failure,
    tool_error_classification,
    tool_run_error_facts,
)
from crxzipple.modules.tool.domain import (
    ToolEnvironment,
    ToolExecutionStrategy,
    ToolExecutionTarget,
    ToolMode,
    ToolRun,
)


def _run(run_id: str = "run-error-1") -> ToolRun:
    return ToolRun.create(
        run_id=run_id,
        tool_id="tool.flight",
        call_id=f"call-{run_id}",
        function_id="tool.flight",
        source_id="source.local",
        input_payload={},
        target=ToolExecutionTarget(
            mode=ToolMode.INLINE,
            strategy=ToolExecutionStrategy.ASYNC,
            environment=ToolEnvironment.LOCAL,
        ),
    )


def test_error_facts_are_empty_without_terminal_error() -> None:
    section = tool_run_error_facts(_run(), provider_label="eastern")

    assert section.id == "error_facts"
    assert section.items == ()


def test_error_facts_classify_access_failures_with_http_status() -> None:
    run = _run()
    run.start()
    run.fail("403 Provider Access missing")

    section = tool_run_error_facts(run, provider_label="eastern")
    values = {item.label: item for item in section.items}

    assert looks_like_access_failure(run)
    assert tool_error_classification(run) == ("access", "access_denied", "danger")
    assert error_http_status(run.error_message) == "403"
    assert values["Provider"].value == "eastern"
    assert values["HTTP Status"].value == "403"
    assert values["HTTP Status"].tone == "danger"
    assert values["Retryable"].value == "Yes"
    assert values["Root Cause"].value == "403 Provider Access missing"


def test_timeout_classification_uses_stable_root_cause() -> None:
    run = _run("run-timeout-1")
    run.timeout()

    section = tool_run_error_facts(run, provider_label="local")
    values = {item.label: item.value for item in section.items}

    assert values["Error Family"] == "timeout"
    assert values["Error Code"] == "tool_timeout"
    assert values["Root Cause"] == "tool run timed out"
