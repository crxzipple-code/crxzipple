from __future__ import annotations

from datetime import datetime, timezone

from crxzipple.modules.operations.application.read_models.tool_readiness_sections import (
    auth_missing_section,
)
from crxzipple.modules.tool.domain import (
    Tool,
    ToolEnvironment,
    ToolExecutionStrategy,
    ToolExecutionTarget,
    ToolMode,
    ToolRun,
)


class _CombinedReadinessToolService:
    def check_readiness(self, tool_id: str) -> dict[str, object] | None:
        if tool_id != "browser.snapshot":
            return None
        return {
            "ready": False,
            "status": "degraded",
            "reason": "Browser profile runtime is not ready",
            "setup_available": False,
            "checks": [
                {
                    "category": "runtime",
                    "requirement": "browser-profile-runtime",
                    "ready": False,
                },
            ],
        }

    def check_access_readiness(self, _tool_id: str) -> None:
        return None


def _target() -> ToolExecutionTarget:
    return ToolExecutionTarget(
        mode=ToolMode.INLINE,
        strategy=ToolExecutionStrategy.ASYNC,
        environment=ToolEnvironment.LOCAL,
    )


def _tool(
    tool_id: str,
    *,
    access_requirement_sets: tuple[tuple[str, ...], ...] = (),
    runtime_requirement_sets: tuple[tuple[str, ...], ...] = (),
) -> Tool:
    return Tool(
        id=tool_id,
        name=tool_id,
        description=f"{tool_id} test tool.",
        access_requirement_sets=access_requirement_sets,
        runtime_requirement_sets=runtime_requirement_sets,
    )


def _failed_run(tool_id: str) -> ToolRun:
    run = ToolRun.create(
        run_id=f"{tool_id}-run",
        tool_id=tool_id,
        call_id=f"{tool_id}-call",
        input_payload={},
        target=_target(),
    )
    run.fail("401 auth credential missing")
    return run


def test_auth_missing_section_reports_declared_access_without_service() -> None:
    section = auth_missing_section(
        [
            _tool(
                "weather.lookup",
                access_requirement_sets=(("env:WEATHER_API_KEY",),),
            ),
        ],
        [],
        access_service=None,
        now=datetime.now(timezone.utc),
    )

    assert section.id == "auth_missing"
    assert section.total == 1
    row = section.rows[0]
    assert row.id == "weather.lookup"
    assert row.tone == "danger"
    assert row.cells["category"] == "Access"
    assert row.cells["status"] == "unknown"
    assert row.cells["missing_access"] == "env:WEATHER_API_KEY"
    assert row.cells["action"] == "Open Access"
    assert row.cells["route"] == "/operations/access"


def test_auth_missing_section_uses_combined_runtime_readiness_payload() -> None:
    section = auth_missing_section(
        [
            _tool(
                "browser.snapshot",
                runtime_requirement_sets=(("browser-profile-runtime",),),
            ),
        ],
        [],
        tool_service=_CombinedReadinessToolService(),  # type: ignore[arg-type]
        access_service=None,
        now=datetime.now(timezone.utc),
    )

    assert section.total == 1
    row = section.rows[0]
    assert row.id == "browser.snapshot"
    assert row.tone == "warning"
    assert row.cells["category"] == "Runtime"
    assert row.cells["status"] == "degraded"
    assert row.cells["missing_access"] == "browser-profile-runtime"
    assert row.cells["action"] == "Open Daemon"
    assert row.cells["route"] == "/operations/daemon"


def test_auth_missing_section_preserves_observed_access_failures() -> None:
    section = auth_missing_section(
        [],
        [_failed_run("private.http")],
        access_service=None,
        now=datetime.now(timezone.utc),
    )

    assert section.total == 1
    row = section.rows[0]
    assert row.id == "failed-access:private.http"
    assert row.tone == "danger"
    assert row.status == "blocked"
    assert row.cells["tool"] == "private.http"
    assert row.cells["status"] == "observed_failure"
    assert row.cells["affected_24h"] == "1"
    assert row.cells["access_failures"] == "1"
    assert row.cells["action"] == "Open Trace"
