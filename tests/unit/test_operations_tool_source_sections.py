from __future__ import annotations

from types import SimpleNamespace

from crxzipple.modules.operations.application.read_models.tool_source_catalog_sections import (
    source_health_section,
)
from crxzipple.modules.operations.application.read_models.tool_source_catalog_rows import (
    source_tab_tone,
)
from crxzipple.modules.operations.application.read_models.tool_source_provider_sections import (
    provider_backend_health_section,
)
from crxzipple.modules.tool.domain import (
    ToolEnvironment,
    ToolExecutionStrategy,
    ToolExecutionTarget,
    ToolMode,
    ToolRun,
)


def _target() -> ToolExecutionTarget:
    return ToolExecutionTarget(
        mode=ToolMode.INLINE,
        strategy=ToolExecutionStrategy.ASYNC,
        environment=ToolEnvironment.LOCAL,
    )


def test_source_health_section_projects_browser_runtime_context() -> None:
    source = SimpleNamespace(
        source_id="bundled.local_package.browser",
        kind="local_package",
        config={"namespace": "browser", "package_kind": "local_package"},
        runtime_requirements=("browser-profile-runtime",),
        status="active",
        last_discovery_status=None,
        revision=1,
        updated_at=None,
    )
    function = SimpleNamespace(
        function_id="browser.navigate",
        source_id="bundled.local_package.browser",
        runtime_kind="local",
        status="active",
        enabled=True,
        revision=1,
        schema_hash="sha256:browser",
    )

    section = source_health_section(
        (source,),
        functions=(function,),
        discovery_runs_by_source={},
    )

    assert section.id == "source_health"
    assert section.total == 1
    row = section.rows[0]
    assert row.id == "bundled.local_package.browser"
    assert row.tone == "success"
    assert row.cells["runtime"] == "Browser profile context"
    assert row.cells["functions"] == "1/1"
    assert source_tab_tone((source,), (function,)) == "neutral"


def test_provider_backend_health_projects_readiness_and_recent_run_counts() -> None:
    backend = SimpleNamespace(
        backend_id="openai.responses",
        display_name="OpenAI Responses",
        capability="llm",
        credential_requirements=(
            {
                "requirements": (
                    {
                        "slot": {
                            "binding_id": "openai.api_key",
                            "expected_kind": "api_key",
                        },
                    },
                ),
            },
        ),
        runtime_ref={"runtime_kind": "http", "ref": "openai"},
        status="active",
        enabled=True,
    )
    run = ToolRun.create(
        run_id="tool-run-1",
        tool_id="openai.responses",
        call_id="tool-call-1",
        input_payload={"prompt": "hello"},
        metadata={"provider_backend": {"backend_id": "openai.responses"}},
        target=_target(),
    )
    run.start()
    run.fail("rate limited")

    section = provider_backend_health_section(
        (backend,),
        runs=[run],
        readiness_by_backend_id={
            "openai.responses": {
                "ready": False,
                "status": "degraded",
                "checks": [{"ready": True}, {"ready": False}],
            },
        },
        now=run.created_at,
    )

    assert section.id == "provider_backend_health"
    assert section.total == 1
    row = section.rows[0]
    assert row.id == "openai.responses"
    assert row.tone == "warning"
    assert row.cells["credential"] == "openai.api_key"
    assert row.cells["readiness"] == "Degraded (1/2)"
    assert row.cells["calls_24h"] == "1"
    assert row.cells["failures_24h"] == "1"
    assert row.cells["runtime"] == "http:openai"
