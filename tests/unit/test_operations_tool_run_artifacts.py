from __future__ import annotations

from types import SimpleNamespace

from crxzipple.modules.operations.application.read_models.tool_run_artifacts import (
    ToolArtifactRunContext,
    recent_artifacts_section,
    tool_run_artifacts_section,
)
from crxzipple.modules.operations.application.read_models.tool_run_artifact_refs import (
    tool_run_artifact_refs,
)
from crxzipple.modules.operations.application.read_models.tool_run_result_payloads import (
    tool_run_result_summary,
)
from crxzipple.modules.tool.domain import (
    ToolEnvironment,
    ToolExecutionStrategy,
    ToolExecutionTarget,
    ToolMode,
    ToolRun,
    ToolRunResult,
)


def _run(run_id: str = "run-artifact-1") -> ToolRun:
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


class _ArtifactService:
    def get_artifact(self, artifact_id: str):
        assert artifact_id == "artifact-1"
        return SimpleNamespace(
            kind="image",
            name="boarding-pass.png",
            mime_type="image/png",
            size_bytes=2048,
            width=640,
            height=480,
        )


def test_artifact_refs_are_extracted_and_enriched_from_result_metadata() -> None:
    run = _run()
    run.start()
    run.succeed(
        ToolRunResult.text(
            "captured",
            metadata={"artifact_id": "artifact-1"},
        ),
    )

    refs = tool_run_artifact_refs(run, artifact_service=_ArtifactService())

    assert refs == [
        {
            "artifact_id": "artifact-1",
            "name": "boarding-pass.png",
            "kind": "image",
            "mime_type": "image/png",
            "size": "2.0 KiB",
            "dimensions": "640x480",
            "preview_url": "/artifacts/artifact-1/preview",
            "download_url": "/artifacts/artifact-1/download",
        },
    ]
    assert "captured" in tool_run_result_summary(run)


def test_recent_and_run_artifact_sections_project_routes_and_context() -> None:
    run = _run()
    run.start()
    run.succeed(
        ToolRunResult.text(
            "captured",
            metadata={"artifact_id": "artifact-1"},
        ),
    )
    context = ToolArtifactRunContext(
        tool_label="Flight Search",
        trace="trace-1",
        trace_route="/workbench/traces/trace-1",
    )

    recent = recent_artifacts_section(
        [run],
        run_contexts={run.id: context},
        artifact_service=_ArtifactService(),
    )
    detail = tool_run_artifacts_section(
        run,
        context=context,
        artifact_service=_ArtifactService(),
    )

    assert recent.id == "recent_artifacts"
    assert recent.rows[0].cells["tool"] == "Flight Search"
    assert recent.rows[0].cells["trace_route"] == "/workbench/traces/trace-1"
    assert recent.rows[0].cells["route"] == "/artifacts/artifact-1/preview"
    assert detail.id == "run_artifacts"
    assert detail.rows[0].cells["actions"] == "Open"
