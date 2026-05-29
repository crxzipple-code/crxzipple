from __future__ import annotations

from crxzipple.app.integration.context_workspace_orchestration import (
    ContextWorkspacePromptSnapshotAdapter,
)
from crxzipple.modules.artifacts.application.services import ArtifactBinary
from crxzipple.modules.artifacts.domain.entities import (
    Artifact,
    ArtifactKind,
    ArtifactVariant,
)
from crxzipple.modules.context_workspace.application import (
    ContextNodeUpsertInput,
    ContextRenderService,
    ContextTreeService,
    ContextWorkspaceService,
    EnsureContextWorkspaceInput,
)
from crxzipple.modules.context_workspace.domain import (
    ContextAction,
    ContextEstimate,
    ContextNodeSeed,
    ContextNodeState,
)
from crxzipple.modules.context_workspace.infrastructure import (
    InMemoryContextNodeRepository,
    InMemoryContextOperationRepository,
    InMemoryContextRenderSnapshotRepository,
    InMemoryContextWorkspaceRepository,
)
from crxzipple.modules.llm.domain import LlmMessage, LlmMessageRole, ToolSchema
from crxzipple.modules.orchestration.application.engine import OrchestrationEngine
from crxzipple.modules.orchestration.application.ports import (
    ContextRenderSnapshotRecord,
)
from crxzipple.modules.orchestration.application.prompt_surface import (
    PromptSurface,
)
from crxzipple.modules.orchestration.application.prompting import (
    PromptBlock,
    PromptMode,
    PromptReport,
)
from crxzipple.modules.orchestration.application.tool_resolver import (
    ResolvedTool,
    ResolvedToolSet,
)
from crxzipple.modules.orchestration.domain import (
    InboundInstruction,
    OrchestrationRun,
)
from crxzipple.modules.tool.domain import Tool, ToolExecutionTarget


def test_context_workspace_adapter_records_tree_snapshot_for_run_prompt() -> None:
    workspaces = InMemoryContextWorkspaceRepository()
    nodes = InMemoryContextNodeRepository()
    snapshots = InMemoryContextRenderSnapshotRepository()
    adapter = ContextWorkspacePromptSnapshotAdapter(
        workspace_service=ContextWorkspaceService(
            workspace_repository=workspaces,
            node_repository=nodes,
        ),
        render_service=ContextRenderService(
            workspace_repository=workspaces,
            node_repository=nodes,
            snapshot_repository=snapshots,
        ),
    )

    snapshot_record = adapter.record_run_prompt_snapshot(
        run=_run(),
        prompt=_prompt(
            tool_schemas=(ToolSchema(name="fetch_weather", description="Fetch weather."),),
        ),
    )
    snapshot = snapshots.get_by_run("run-context")
    workspace = workspaces.get_by_session("session:context")

    assert snapshot is not None
    assert workspace is not None
    assert snapshot_record is not None
    assert snapshot_record.snapshot_id == snapshot.id
    assert snapshot_record.prompt_body == snapshot.prompt_body
    assert snapshot_record.estimate == snapshot.estimate.to_payload()
    assert snapshot_record.included_node_ids == snapshot.included_node_ids
    assert snapshot_record.tool_schemas is None
    assert snapshot_record.tool_schema_mirror_available is False
    assert "<context_tree" in snapshot.prompt_body
    assert "run.flow" in snapshot.included_node_ids
    assert "run.runtime" in snapshot.included_node_ids
    assert "session.current" in snapshot.included_node_ids
    assert snapshot.provider_attachments["prompt_surface"]["message_count"] == 1
    assert workspace.metadata["available_tool_names"] == ["fetch_weather"]
    assert workspace.metadata["run_flow_node"]["mode"] == "normal_turn"
    assert snapshot.metadata["parallel_recording"] is True


def test_context_workspace_adapter_previews_tree_prompt_without_snapshot_write() -> None:
    workspaces = InMemoryContextWorkspaceRepository()
    nodes = InMemoryContextNodeRepository()
    snapshots = InMemoryContextRenderSnapshotRepository()
    adapter = ContextWorkspacePromptSnapshotAdapter(
        workspace_service=ContextWorkspaceService(
            workspace_repository=workspaces,
            node_repository=nodes,
        ),
        render_service=ContextRenderService(
            workspace_repository=workspaces,
            node_repository=nodes,
            snapshot_repository=snapshots,
        ),
    )

    snapshot_record = adapter.preview_run_prompt_snapshot(
        run=_run(),
        prompt=_prompt(
            tool_schemas=(ToolSchema(name="fetch_weather", description="Fetch weather."),),
        ),
    )

    assert snapshot_record is not None
    assert snapshot_record.snapshot_id == "ctxpreview_run-context"
    assert "<context_tree" in snapshot_record.prompt_body
    assert "tools.available" in snapshot_record.included_node_ids
    assert snapshots.get_by_run("run-context") is None


def test_context_workspace_adapter_records_agent_and_runtime_blocks_as_tree_content() -> None:
    workspaces = InMemoryContextWorkspaceRepository()
    nodes = InMemoryContextNodeRepository()
    snapshots = InMemoryContextRenderSnapshotRepository()
    adapter = ContextWorkspacePromptSnapshotAdapter(
        workspace_service=ContextWorkspaceService(
            workspace_repository=workspaces,
            node_repository=nodes,
        ),
        render_service=ContextRenderService(
            workspace_repository=workspaces,
            node_repository=nodes,
            snapshot_repository=snapshots,
        ),
    )

    snapshot_record = adapter.record_run_prompt_snapshot(
        run=_run(),
        prompt=_prompt(
            system_messages=(
                ("agent_instruction", "Be precise."),
                ("runtime_context", "# Runtime Context\n\n- Agent: assistant"),
            ),
        ),
    )

    assert snapshot_record is not None
    assert "agent.identity" in snapshot_record.prompt_body
    assert "Be precise." in snapshot_record.prompt_body
    assert "run.runtime" in snapshot_record.prompt_body
    assert "- Agent: assistant" in snapshot_record.prompt_body


def test_context_workspace_adapter_mirrors_opened_artifact_blocks(tmp_path) -> None:
    artifact_path = tmp_path / "image.png"
    artifact_path.write_bytes(b"png")
    workspaces = InMemoryContextWorkspaceRepository()
    nodes = InMemoryContextNodeRepository()
    operations = InMemoryContextOperationRepository()
    snapshots = InMemoryContextRenderSnapshotRepository()
    workspace_service = ContextWorkspaceService(
        workspace_repository=workspaces,
        node_repository=nodes,
    )
    tree_service = ContextTreeService(
        workspace_repository=workspaces,
        node_repository=nodes,
        operation_repository=operations,
    )
    render_service = ContextRenderService(
        workspace_repository=workspaces,
        node_repository=nodes,
        snapshot_repository=snapshots,
    )
    workspace_service.ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:context",
            agent_id="assistant",
        ),
    )
    tree_service.upsert_nodes(
        ContextNodeUpsertInput(
            session_key="session:context",
            parent_node_id="artifacts.session",
            action=ContextAction.OPEN_ARTIFACT,
            nodes=(
                ContextNodeSeed(
                    node_id="artifacts.artifact.image-1",
                    parent_id="artifacts.session",
                    owner="artifacts",
                    kind="artifact_image",
                    title="image.png",
                    summary="Image artifact.",
                    state=ContextNodeState(loaded=True, opened=True),
                    actions=(ContextAction.OPEN_ARTIFACT,),
                    owner_ref={
                        "artifact_id": "image-1",
                        "preferred_variant": "llm",
                    },
                    estimate=ContextEstimate(image_count=1),
                    metadata={"mime_type": "image/png", "name": "image.png"},
                ),
            ),
        ),
    )
    adapter = ContextWorkspacePromptSnapshotAdapter(
        workspace_service=workspace_service,
        render_service=render_service,
        artifact_service=_FakeArtifactService(artifact_path),
    )

    snapshot_record = adapter.record_run_prompt_snapshot(
        run=_run(),
        prompt=_prompt(),
    )

    assert snapshot_record is not None
    assert snapshot_record.artifact_content_blocks == (
        {
            "type": "image",
            "mime_type": "image/png",
            "data": "cG5n",
        },
    )
    snapshot = snapshots.get_by_run("run-context")
    assert snapshot is not None
    assert snapshot.provider_attachments["artifact_content_candidates"][0]["artifact_id"] == "image-1"


def test_engine_preview_uses_context_tree_without_recording_snapshot() -> None:
    snapshot_port = _FakeContextSnapshotPort(
        prompt_body="<context_tree><node id=\"session.current\" /></context_tree>",
        tool_schemas=(ToolSchema(name="fetch_weather", description="Fetch weather."),),
    )
    engine = OrchestrationEngine(
        prompt_surface=_FakePromptSurfaceBuilder(
            tool_schemas=(
                ToolSchema(name="fetch_weather", description="Fetch weather."),
                ToolSchema(name="web_search", description="Search the web."),
            ),
        ),
        session_recorder=_FakeSessionRecorder(),
        llm_port=object(),
        tool_resolver=_FakeToolResolver(),
        tool_execution_port=object(),
        context_snapshot_port=snapshot_port,
    )

    preview = engine.preview_prompt(_run())

    assert preview.llm_id == "test-llm"
    assert preview.messages[0].metadata == {
        "prompt_block_kind": "context_workspace",
        "context_render_snapshot_id": "preview-run-context",
    }
    assert "session.current" in preview.messages[0].content
    assert [schema.name for schema in preview.tool_schemas] == ["fetch_weather"]
    assert preview.prompt_report is not None
    assert preview.prompt_report.context_render is not None
    assert preview.prompt_report.context_render.snapshot_id == "preview-run-context"
    assert snapshot_port.preview_calls == [("run-context", "session:context")]
    assert snapshot_port.calls == []

    context = engine._build_advance_context(_run())  # noqa: SLF001

    assert context.context_render_snapshot_id == "snapshot-run-context"
    assert context.prompt.report is not None
    assert context.prompt.report.context_render is not None
    assert context.prompt.report.context_render.snapshot_id == "snapshot-run-context"
    assert snapshot_port.calls == [("run-context", "session:context")]


def test_engine_adds_context_workspace_body_to_real_prompt() -> None:
    snapshot_port = _FakeContextSnapshotPort(
        prompt_body="<context_tree><node id=\"session.current\" /></context_tree>",
    )
    engine = OrchestrationEngine(
        prompt_surface=_FakePromptSurfaceBuilder(),
        session_recorder=_FakeSessionRecorder(),
        llm_port=object(),
        tool_resolver=_FakeToolResolver(),
        tool_execution_port=object(),
        context_snapshot_port=snapshot_port,
    )

    context = engine._build_advance_context(_run())  # noqa: SLF001

    first_message = context.prompt.messages[0]
    assert first_message.role is LlmMessageRole.SYSTEM
    assert first_message.metadata == {
        "prompt_block_kind": "context_workspace",
        "context_render_snapshot_id": "snapshot-run-context",
    }
    assert "session.current" in first_message.content


def test_engine_uses_context_mirror_as_real_tool_schema_surface() -> None:
    snapshot_port = _FakeContextSnapshotPort(
        tool_schemas=(ToolSchema(name="fetch_weather", description="Fetch weather."),),
    )
    engine = OrchestrationEngine(
        prompt_surface=_FakePromptSurfaceBuilder(
            tool_schemas=(
                ToolSchema(name="fetch_weather", description="Fetch weather."),
                ToolSchema(name="web_search", description="Search the web."),
            ),
        ),
        session_recorder=_FakeSessionRecorder(),
        llm_port=object(),
        tool_resolver=_FakeToolResolver(
            tools=(
                _resolved_tool("fetch_weather"),
                _resolved_tool("web_search"),
            ),
        ),
        tool_execution_port=object(),
        context_snapshot_port=snapshot_port,
    )

    context = engine._build_advance_context(_run())  # noqa: SLF001

    assert [schema.name for schema in context.prompt.tool_schemas] == ["fetch_weather"]
    assert [item.tool.id for item in context.resolved_tools.tools] == ["fetch_weather"]


def test_engine_drops_provider_tool_surface_when_context_mirror_not_ready() -> None:
    snapshot_port = _FakeContextSnapshotPort(tool_schemas=None)
    engine = OrchestrationEngine(
        prompt_surface=_FakePromptSurfaceBuilder(
            tool_schemas=(ToolSchema(name="web_search", description="Search the web."),),
        ),
        session_recorder=_FakeSessionRecorder(),
        llm_port=object(),
        tool_resolver=_FakeToolResolver(tools=(_resolved_tool("web_search"),)),
        tool_execution_port=object(),
        context_snapshot_port=snapshot_port,
    )

    context = engine._build_advance_context(_run())  # noqa: SLF001

    assert context.prompt.tool_schemas == ()
    assert context.resolved_tools.tools == ()


def test_engine_allows_context_mirror_to_disable_all_tool_schemas() -> None:
    snapshot_port = _FakeContextSnapshotPort(tool_schemas=())
    engine = OrchestrationEngine(
        prompt_surface=_FakePromptSurfaceBuilder(
            tool_schemas=(ToolSchema(name="web_search", description="Search the web."),),
        ),
        session_recorder=_FakeSessionRecorder(),
        llm_port=object(),
        tool_resolver=_FakeToolResolver(tools=(_resolved_tool("web_search"),)),
        tool_execution_port=object(),
        context_snapshot_port=snapshot_port,
    )

    context = engine._build_advance_context(_run())  # noqa: SLF001

    assert context.prompt.tool_schemas == ()
    assert context.resolved_tools.tools == ()


def test_engine_appends_context_artifact_blocks_to_real_prompt() -> None:
    snapshot_port = _FakeContextSnapshotPort(
        artifact_content_blocks=(
            {
                "type": "image",
                "mime_type": "image/png",
                "data": "cG5n",
            },
        ),
    )
    engine = OrchestrationEngine(
        prompt_surface=_FakePromptSurfaceBuilder(),
        session_recorder=_FakeSessionRecorder(),
        llm_port=object(),
        tool_resolver=_FakeToolResolver(),
        tool_execution_port=object(),
        context_snapshot_port=snapshot_port,
    )

    context = engine._build_advance_context(_run())  # noqa: SLF001

    artifact_message = context.prompt.messages[-1]
    assert artifact_message.role is LlmMessageRole.USER
    assert artifact_message.metadata["prompt_block_kind"] == "context_artifacts"
    assert artifact_message.content[1]["type"] == "image"
    assert artifact_message.content[1]["data"] == "cG5n"


def _run() -> OrchestrationRun:
    return OrchestrationRun(
        id="run-context",
        inbound_instruction=InboundInstruction(
            source="unit-test",
            content="hello tree",
        ),
        active_session_id="session-instance-1",
        agent_id="assistant",
        metadata={"session_key": "session:context"},
    )


def _prompt(
    *,
    tool_schemas: tuple[ToolSchema, ...] = (),
    system_messages: tuple[tuple[str, str], ...] = (),
) -> PromptSurface:
    return PromptSurface(
        llm_id="test-llm",
        session_key="session:context",
        active_session_id="session-instance-1",
        messages=(
            LlmMessage(
                role=LlmMessageRole.USER,
                content="hello tree",
            ),
        ),
        tool_schemas=tool_schemas,
        context_blocks=tuple(
            PromptBlock(kind=kind, content=content)
            for kind, content in system_messages
        ),
        report=PromptReport(
            mode=PromptMode.NORMAL_TURN,
            context_blocks=(),
            context_budget_source="fixed",
            context_budget_chars=0,
            context_budget_estimated_tokens=0,
            llm_context_window_tokens=None,
            context_chars=0,
            context_estimated_tokens=0,
            transcript_message_count=1,
            transcript_chars=10,
            transcript_estimated_tokens=3,
        ),
    )


class _FakePromptSurfaceBuilder:
    detailed_phase_metrics_enabled = False
    metrics = None

    def __init__(
        self,
        *,
        tool_schemas: tuple[ToolSchema, ...] = (),
        system_messages: tuple[tuple[str, str], ...] = (),
    ) -> None:
        self._tool_schemas = tool_schemas
        self._system_messages = system_messages

    def build(self, run, *, resolved_tools):  # noqa: ANN001, ANN201
        del run, resolved_tools
        return _prompt(
            tool_schemas=self._tool_schemas,
            system_messages=self._system_messages,
        )


class _FakeSessionRecorder:
    def ensure_inbound_message(self, run, *, session_key):  # noqa: ANN001, ANN201
        assert run.id == "run-context"
        assert session_key == "session:context"
        return "message-user-1"


class _FakeToolResolver:
    def __init__(self, *, tools: tuple[ResolvedTool, ...] = ()) -> None:
        self._tools = tools

    def resolve(self, run):  # noqa: ANN001, ANN201
        assert run.id == "run-context"
        return ResolvedToolSet(tools=self._tools)


class _FakeContextSnapshotPort:
    def __init__(
        self,
        *,
        tool_schemas: tuple[ToolSchema, ...] | None = None,
        prompt_body: str | None = None,
        tool_schema_mirror_available: bool | None = None,
        artifact_content_blocks: tuple[dict[str, object], ...] = (),
    ) -> None:
        self._tool_schemas = tool_schemas
        self._prompt_body = prompt_body
        self._artifact_content_blocks = artifact_content_blocks
        self._tool_schema_mirror_available = (
            tool_schemas is not None
            if tool_schema_mirror_available is None
            else tool_schema_mirror_available
        )
        self.calls: list[tuple[str, str]] = []
        self.preview_calls: list[tuple[str, str]] = []

    def preview_run_prompt_snapshot(
        self,
        *,
        run: OrchestrationRun,
        prompt: PromptSurface,
    ) -> ContextRenderSnapshotRecord:
        self.preview_calls.append((run.id, prompt.session_key))
        return self._snapshot_record(snapshot_id=f"preview-{run.id}")

    def record_run_prompt_snapshot(
        self,
        *,
        run: OrchestrationRun,
        prompt: PromptSurface,
    ) -> ContextRenderSnapshotRecord:
        self.calls.append((run.id, prompt.session_key))
        return self._snapshot_record(snapshot_id=f"snapshot-{run.id}")

    def _snapshot_record(self, *, snapshot_id: str) -> ContextRenderSnapshotRecord:
        return ContextRenderSnapshotRecord(
            snapshot_id=snapshot_id,
            prompt_body=self._prompt_body,
            tool_schemas=self._tool_schemas,
            tool_schema_mirror_available=self._tool_schema_mirror_available,
            artifact_content_blocks=self._artifact_content_blocks,
        )


def _resolved_tool(tool_id: str) -> ResolvedTool:
    return ResolvedTool(
        tool=Tool(
            id=tool_id,
            name=tool_id,
            description=f"{tool_id} description.",
        ),
        schema=ToolSchema(name=tool_id, description=f"{tool_id} description."),
        target=ToolExecutionTarget(),
    )


class _FakeArtifactService:
    def __init__(self, path) -> None:
        self.path = path
        self.artifact = Artifact(
            id="image-1",
            kind=ArtifactKind.IMAGE,
            mime_type="image/png",
            storage_key="image-1/original.png",
            llm_storage_key="image-1/llm.png",
            name="image.png",
        )

    def resolve_variant(
        self,
        artifact_id: str,
        *,
        variant: ArtifactVariant,
    ) -> ArtifactBinary:
        assert artifact_id == "image-1"
        assert variant is ArtifactVariant.LLM
        return ArtifactBinary(
            artifact=self.artifact,
            path=self.path,
            variant=variant,
        )
