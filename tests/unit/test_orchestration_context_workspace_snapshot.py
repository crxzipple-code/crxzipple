from __future__ import annotations

import pytest

from crxzipple.app.integration.context_workspace_orchestration.adapter import (
    ContextWorkspaceRunSnapshotAdapter,
)
from crxzipple.modules.artifacts.application.services import ArtifactBinary
from crxzipple.modules.artifacts.domain.entities import (
    Artifact,
    ArtifactKind,
    ArtifactVariant,
)
from crxzipple.modules.context_workspace.application import (
    CONTEXT_TREE_SCHEMA_VERSION,
    ContextNodeUpsertInput,
    ContextControlSliceService,
    ContextSliceBuilderService,
    ContextObservationSnapshotService,
    ContextTreeService,
    ContextWorkspaceService,
    ContextObservationRenderInput,
    EnsureContextWorkspaceInput,
    RequestRenderSnapshotService,
)
from crxzipple.modules.context_workspace.domain import (
    ContextAction,
    ContextEstimate,
    ContextSnapshot,
    ContextWorkspace,
    ContextNodeSeed,
    ContextNodeState,
)
from crxzipple.modules.context_workspace.infrastructure import (
    InMemoryContextNodeRepository,
    InMemoryContextOperationRepository,
    InMemoryContextRequestRenderSnapshotRepository,
    InMemoryContextSnapshotRepository,
    InMemoryContextWorkspaceRepository,
)
from crxzipple.modules.llm.domain import (
    LlmCapability,
    LlmMessage,
    LlmMessageRole,
    ToolSchema,
)
from crxzipple.modules.orchestration.application.engine import OrchestrationEngine
from crxzipple.modules.orchestration.application.engine_session_recorder import (
    InboundSessionRecord,
)
from crxzipple.modules.orchestration.application.ports import (
    RequestRenderSnapshotRecord,
)
from crxzipple.modules.orchestration.domain.value_objects import ExecutionStepItemKind
from crxzipple.modules.orchestration.application.runtime_llm_request_draft import (
    RuntimeLlmRequestDraft,
)
from crxzipple.modules.orchestration.application.runtime_request_mode import RuntimeRequestMode
from crxzipple.modules.orchestration.application.runtime_request_report import RuntimeRequestReport
from crxzipple.modules.orchestration.application.tool_resolver import (
    ResolvedTool,
    ResolvedToolSet,
)
from crxzipple.modules.orchestration.domain import (
    InboundInstruction,
    OrchestrationRun,
    OrchestrationValidationError,
)
from crxzipple.modules.tool.application import (
    ToolRuntimeRequestBundle,
    ToolRuntimeRequestBundleGroup,
)
from crxzipple.modules.tool.domain import Tool, ToolExecutionTarget


def test_context_workspace_adapter_rejects_persisted_request_snapshot_without_context_slice() -> None:
    class _NoDebugRenderSnapshotService(ContextObservationSnapshotService):
        def render_observation(self, data):  # type: ignore[no-untyped-def]
            raise AssertionError("record hot path must not render full debug body")

    class _NoListForWorkspaceNodeRepository(InMemoryContextNodeRepository):
        def list_for_workspace(self, workspace_id: str):  # type: ignore[no-untyped-def]
            raise AssertionError("record hot path must not list full workspace nodes")

    workspaces = InMemoryContextWorkspaceRepository()
    nodes = _NoListForWorkspaceNodeRepository()
    snapshots = InMemoryContextSnapshotRepository()
    request_render_snapshots = InMemoryContextRequestRenderSnapshotRepository()
    adapter = ContextWorkspaceRunSnapshotAdapter(
        workspace_service=ContextWorkspaceService(
            workspace_repository=workspaces,
            node_repository=nodes,
        ),
        render_service=_NoDebugRenderSnapshotService(
            workspace_repository=workspaces,
            node_repository=nodes,
            snapshot_repository=snapshots,
        ),
        request_render_snapshot_service=RequestRenderSnapshotService(
            workspace_repository=workspaces,
            snapshot_repository=request_render_snapshots,
        ),
    )

    with pytest.raises(
        RuntimeError,
        match="Context Slice builder is required",
    ):
        adapter.record_run_request_render_snapshot(
            run=_run(),
            draft=_draft(
                tool_schemas=(
                    ToolSchema(name="fetch_weather", description="Fetch weather."),
                ),
            ),
        )

    assert snapshots.get_by_run("run-context") is None
    assert request_render_snapshots.get("run-context") is None


def test_request_render_tool_bootstrap_requires_context_slice_for_persisted_snapshot() -> None:
    class _NoDebugRenderSnapshotService(ContextObservationSnapshotService):
        def render_observation(self, data):  # type: ignore[no-untyped-def]
            raise AssertionError("record hot path must not render full debug body")

    class _NoListForWorkspaceNodeRepository(InMemoryContextNodeRepository):
        def list_for_workspace(self, workspace_id: str):  # type: ignore[no-untyped-def]
            raise AssertionError("request hot path must not scan full context tree")

    workspaces = InMemoryContextWorkspaceRepository()
    nodes = _NoListForWorkspaceNodeRepository()
    operations = InMemoryContextOperationRepository()
    snapshots = InMemoryContextSnapshotRepository()
    request_render_snapshots = InMemoryContextRequestRenderSnapshotRepository()
    adapter = ContextWorkspaceRunSnapshotAdapter(
        workspace_service=ContextWorkspaceService(
            workspace_repository=workspaces,
            node_repository=nodes,
        ),
        render_service=_NoDebugRenderSnapshotService(
            workspace_repository=workspaces,
            node_repository=nodes,
            snapshot_repository=snapshots,
        ),
        tree_service=ContextTreeService(
            workspace_repository=workspaces,
            node_repository=nodes,
            operation_repository=operations,
        ),
        request_render_snapshot_service=RequestRenderSnapshotService(
            workspace_repository=workspaces,
            snapshot_repository=request_render_snapshots,
        ),
    )

    with pytest.raises(
        RuntimeError,
        match="Context Slice builder is required",
    ):
        adapter.record_run_request_render_snapshot(
            run=_run(),
            draft=_draft(
                tool_schemas=(
                    ToolSchema(name="fetch_weather", description="Fetch weather."),
                ),
                flow_hint={
                    "default_tool_schema_ids": ["fetch_weather"],
                    "default_tool_schema_source": "test.default",
                },
            ),
        )

    assert snapshots.get_by_run("run-context") is None
    assert request_render_snapshots.get("run-context") is None


def test_context_workspace_snapshot_records_draft_input_session_item_refs() -> None:
    workspaces = InMemoryContextWorkspaceRepository()
    nodes = InMemoryContextNodeRepository()
    snapshots = InMemoryContextSnapshotRepository()
    adapter = ContextWorkspaceRunSnapshotAdapter(
        workspace_service=ContextWorkspaceService(
            workspace_repository=workspaces,
            node_repository=nodes,
        ),
        render_service=ContextObservationSnapshotService(
            workspace_repository=workspaces,
            node_repository=nodes,
            snapshot_repository=snapshots,
        ),
    )

    with pytest.raises(RuntimeError, match="Context Slice builder is required"):
        adapter.record_run_request_render_snapshot(
            run=_run(),
            draft=_draft(
                extra_messages=(
                    LlmMessage(
                        role=LlmMessageRole.ASSISTANT,
                        content={
                            "type": "function_call",
                            "call_id": "call-weather-1",
                            "name": "weather.lookup",
                            "arguments": {"city": "Kunming"},
                        },
                    ),
                ),
            ),
        )
    assert snapshots.get_by_run("run-context") is None


def test_context_workspace_preview_prefers_control_slice_selected_session_refs() -> None:
    workspaces = InMemoryContextWorkspaceRepository()
    nodes = InMemoryContextNodeRepository()
    operations = InMemoryContextOperationRepository()
    snapshots = InMemoryContextSnapshotRepository()
    request_render_snapshots = InMemoryContextRequestRenderSnapshotRepository()
    workspace_service = ContextWorkspaceService(
        workspace_repository=workspaces,
        node_repository=nodes,
    )
    tree_service = ContextTreeService(
        workspace_repository=workspaces,
        node_repository=nodes,
        operation_repository=operations,
    )
    workspace_service.ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:context",
            agent_id="assistant",
            refresh_expanded_children=False,
        ),
    )
    tree_service.upsert_nodes(
        ContextNodeUpsertInput(
            session_key="session:context",
            parent_node_id="session.current",
            action=ContextAction.EXPAND,
            nodes=(
                ContextNodeSeed(
                    node_id="session.step.item.control-selected",
                    parent_id="session.current",
                    owner="session",
                    kind="session_item",
                    title="Control selected user message",
                    state=ContextNodeState(included_in_next_slice=True),
                    owner_ref={
                        "session_item_id": "item-control-selected",
                        "session_id": "session-instance-1",
                        "sequence_no": 9,
                        "role": "user",
                    },
                ),
            ),
        ),
    )
    adapter = ContextWorkspaceRunSnapshotAdapter(
        workspace_service=workspace_service,
        render_service=ContextObservationSnapshotService(
            workspace_repository=workspaces,
            node_repository=nodes,
            snapshot_repository=snapshots,
        ),
        request_render_snapshot_service=RequestRenderSnapshotService(
            workspace_repository=workspaces,
            snapshot_repository=request_render_snapshots,
        ),
        tree_service=tree_service,
        control_slice_builder=ContextControlSliceService(
            workspace_repository=workspaces,
            node_repository=nodes,
        ),
    )

    snapshot_record = adapter.preview_run_request_render_snapshot(
        run=_run(),
        draft=_draft(),
    )
    snapshot = snapshots.get_by_run("run-context")

    assert snapshot is None
    assert snapshot_record is not None
    assert snapshot_record.included_refs == ()
    assert snapshot_record.metadata["request_context_source"] == "missing_context_slice"
    assert snapshot_record.metadata["control_slice_selected_ref_count"] >= 1


def test_context_workspace_snapshot_projects_context_slice_session_input_items() -> None:
    class _SessionItemResolver:
        def get_item(self, item_id: str):  # type: ignore[no-untyped-def]
            assert item_id == "item-user-1"
            return type(
                "SessionItem",
                (),
                {
                    "id": "item-user-1",
                    "session_id": "session-instance-1",
                    "sequence_no": 1,
                    "role": "user",
                    "content_payload": {
                        "blocks": [{"type": "text", "text": "live slice task"}],
                    },
                    "metadata": {},
                },
            )()

    workspaces = InMemoryContextWorkspaceRepository()
    nodes = InMemoryContextNodeRepository()
    operations = InMemoryContextOperationRepository()
    snapshots = InMemoryContextSnapshotRepository()
    request_render_snapshots = InMemoryContextRequestRenderSnapshotRepository()
    workspace_service = ContextWorkspaceService(
        workspace_repository=workspaces,
        node_repository=nodes,
    )
    tree_service = ContextTreeService(
        workspace_repository=workspaces,
        node_repository=nodes,
        operation_repository=operations,
    )
    workspace_service.ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:context",
            agent_id="assistant",
            refresh_expanded_children=False,
        ),
    )
    tree_service.upsert_nodes(
        ContextNodeUpsertInput(
            session_key="session:context",
            action=ContextAction.UPSERT,
            nodes=(
                ContextNodeSeed(
                    node_id="session.step.item.current-user",
                    parent_id="session.current",
                    owner="session",
                    kind="session_item",
                    title="User Message",
                    content="stale tree text must not project",
                    state=ContextNodeState(included_in_next_slice=True),
                    owner_ref={
                        "session_item_id": "item-user-1",
                        "role": "user",
                    },
                ),
                ContextNodeSeed(
                    node_id="session.step.item.old-user",
                    parent_id="session.current",
                    owner="session",
                    kind="session_item",
                    title="Old User Message",
                    content="old tree text must not project",
                    state=ContextNodeState(included_in_next_slice=True),
                    owner_ref={
                        "session_item_id": "item-old-user",
                        "role": "user",
                    },
                ),
                ContextNodeSeed(
                    node_id="tools.command.exec",
                    parent_id=None,
                    owner="tool",
                    kind="tool_function",
                    title="command.exec",
                    state=ContextNodeState(
                        included_in_next_tool_surface=True,
                        schema_enabled=True,
                    ),
                    owner_ref={
                        "source_id": "configured.command",
                        "tool_id": "command.exec",
                    },
                ),
                ContextNodeSeed(
                    node_id="external.debug.raw-1",
                    parent_id=None,
                    owner="external_debug",
                    kind="diagnostic_blob",
                    title="Raw Diagnostic",
                    summary="Diagnostic handle.",
                    content="raw diagnostic must not project",
                    state=ContextNodeState(included_in_next_slice=True),
                    owner_ref={"diagnostic_id": "raw-1"},
                ),
            ),
        ),
    )
    adapter = ContextWorkspaceRunSnapshotAdapter(
        workspace_service=workspace_service,
        render_service=ContextObservationSnapshotService(
            workspace_repository=workspaces,
            node_repository=nodes,
            snapshot_repository=snapshots,
        ),
        tree_service=tree_service,
        control_slice_builder=ContextControlSliceService(
            workspace_repository=workspaces,
            node_repository=nodes,
        ),
        slice_builder=ContextSliceBuilderService(
            workspace_repository=workspaces,
            node_repository=nodes,
            session_item_resolver=_SessionItemResolver(),
        ),
        request_render_snapshot_service=RequestRenderSnapshotService(
            workspace_repository=workspaces,
            snapshot_repository=request_render_snapshots,
        ),
    )

    snapshot_record = adapter.record_run_request_render_snapshot(
        run=_run(),
        draft=_draft(
            tool_schemas=(
                ToolSchema(
                    name="command.exec",
                    description="Run a shell command.",
                    input_schema={
                        "type": "object",
                        "properties": {"cmd": {"type": "string"}},
                    },
                ),
            ),
        ),
    )

    assert snapshot_record is not None
    assert snapshot_record.projected_input_items == (
        {
            "kind": "message",
            "payload": {
                "role": "user",
                "content": [{"type": "text", "text": "live slice task"}],
            },
            "source": "context_slice",
            "metadata": {
                "owner": "session",
                "kind": "session_item",
                "session_item_id": "item-user-1",
                "node_id": "session.step.item.current-user",
                "sequence_no": 1,
            },
        },
    )
    assert len(snapshot_record.input_item_refs) == 1
    input_item_ref = snapshot_record.input_item_refs[0]
    assert input_item_ref["node_id"] == "session.step.item.current-user"
    assert input_item_ref["session_item_id"] == "item-user-1"
    assert input_item_ref["owner_module"] == "session"
    assert input_item_ref["owner_kind"] == "session_item"
    assert input_item_ref["owner_id"] == "item-user-1"
    assert input_item_ref["sequence_no"] == 1
    assert snapshot_record.metadata["request_context_source"] == "context_slice"
    assert snapshot_record.metadata["context_slice_projected_input_item_count"] == 1
    request_render_cost = snapshot_record.metadata["request_render_cost"]
    assert request_render_cost["selected_node_count"] >= 1
    assert request_render_cost["context_selected_node_count"] >= 1
    assert request_render_cost["selected_session_item_count"] == 1
    assert request_render_cost["provider_visible_tool_count"] == 1
    assert request_render_cost["projected_input_item_count"] == 1
    assert request_render_cost["rendered_input_char_count"] > 0
    assert request_render_cost["elapsed_ms"] >= 0
    assert snapshot_record.metadata["request_render_snapshot"]["cost"] == request_render_cost
    assert snapshot_record.metadata["context_slice_omitted_node_count"] >= 0
    assert snapshot_record.metadata["context_slice_unresolved_ref_count"] == 0
    assert snapshot_record.metadata["context_slice_loss"]["unresolved_ref_count"] == 0
    assert "stale tree text must not project" not in str(
        snapshot_record.projected_input_items,
    )
    assert "old tree text must not project" not in str(
        snapshot_record.projected_input_items,
    )
    assert "item-old-user" not in str(snapshot_record.projected_input_items)
    assert "raw diagnostic must not project" not in str(
        snapshot_record.projected_input_items,
    )
    assert all(
        item["metadata"]["owner"] == "session"
        for item in snapshot_record.projected_input_items
    )
    persisted_request_snapshot = request_render_snapshots.get(
        snapshot_record.snapshot_id,
    )
    assert persisted_request_snapshot is not None
    assert persisted_request_snapshot.projected_input_items == (
        dict(snapshot_record.projected_input_items[0]),
    )
    assert persisted_request_snapshot.input_item_refs == snapshot_record.input_item_refs
    assert persisted_request_snapshot.tool_schema_refs[0]["source"] == "context_slice"
    assert persisted_request_snapshot.tool_schema_refs[0]["node_id"] == "tools.command.exec"
    assert persisted_request_snapshot.tool_schema_refs[0]["source_id"] == (
        "configured.command"
    )
    assert persisted_request_snapshot.tool_schema_refs[0]["schema"]["name"] == (
        "command.exec"
    )
    assert snapshot_record.tool_schema_refs == persisted_request_snapshot.tool_schema_refs
    assert persisted_request_snapshot.render_report["context_slice_loss"][
        "unresolved_ref_count"
    ] == 0
    assert persisted_request_snapshot.render_report["cost"] == request_render_cost
    loaded = adapter.get_recorded_run_request_render_snapshot(
        run=_run(),
        draft=_draft(),
    )
    assert loaded is not None
    assert loaded.input_item_refs == snapshot_record.input_item_refs
    assert loaded.projected_input_items == snapshot_record.projected_input_items
    assert loaded.tool_schema_refs == snapshot_record.tool_schema_refs


def test_request_render_preview_observation_slice_is_read_only() -> None:
    class _ExplodingOwnerRegistry:
        def get(self, owner):  # noqa: ANN001
            raise AssertionError(f"request render must not refresh owner '{owner}'")

    class _SessionItemResolver:
        def get_item(self, item_id: str):  # type: ignore[no-untyped-def]
            if item_id != "item-user-1":
                raise AssertionError(f"unexpected session item: {item_id}")
            return type(
                "SessionItem",
                (),
                {
                    "id": "item-user-1",
                    "session_id": "session-instance-1",
                    "sequence_no": 1,
                    "role": "user",
                    "content_payload": {
                        "blocks": [{"type": "text", "text": "hello tree"}],
                    },
                    "metadata": {},
                },
            )()

    workspaces = InMemoryContextWorkspaceRepository()
    nodes = InMemoryContextNodeRepository()
    snapshots = InMemoryContextSnapshotRepository()
    request_render_snapshots = InMemoryContextRequestRenderSnapshotRepository()
    exploding_registry = _ExplodingOwnerRegistry()
    adapter = ContextWorkspaceRunSnapshotAdapter(
        workspace_service=ContextWorkspaceService(
            workspace_repository=workspaces,
            node_repository=nodes,
            owner_registry=exploding_registry,
        ),
        render_service=ContextObservationSnapshotService(
            workspace_repository=workspaces,
            node_repository=nodes,
            snapshot_repository=snapshots,
        ),
        slice_builder=ContextSliceBuilderService(
            workspace_repository=workspaces,
            node_repository=nodes,
            owner_registry=exploding_registry,
            session_item_resolver=_SessionItemResolver(),
        ),
        request_render_snapshot_service=RequestRenderSnapshotService(
            workspace_repository=workspaces,
            snapshot_repository=request_render_snapshots,
        ),
    )

    snapshot_record = adapter.preview_run_request_render_snapshot(
        run=_run(),
        draft=_draft(),
    )

    assert snapshot_record is not None
    builder_timings = snapshot_record.metadata["context_slice_builder_timings"]
    assert builder_timings["refresh_owner_children_ms"] >= 0
    assert builder_timings["total_ms"] >= 0


def test_request_render_budget_stays_bounded_for_long_session_tree() -> None:
    large_history_text = "archived-history-body-" + ("x" * 400)

    class _SessionItemResolver:
        def __init__(self) -> None:
            self.resolved_ids: list[str] = []

        def get_item(self, item_id: str):  # type: ignore[no-untyped-def]
            self.resolved_ids.append(item_id)
            if item_id != "item-user-1":
                raise AssertionError(f"unexpected history resolution: {item_id}")
            return type(
                "SessionItem",
                (),
                {
                    "id": "item-user-1",
                    "session_id": "session-instance-1",
                    "sequence_no": 121,
                    "role": "user",
                    "content_payload": {
                        "blocks": [{"type": "text", "text": "frontier task only"}],
                    },
                    "metadata": {},
                },
            )()

    resolver = _SessionItemResolver()
    workspaces = InMemoryContextWorkspaceRepository()
    nodes = InMemoryContextNodeRepository()
    operations = InMemoryContextOperationRepository()
    snapshots = InMemoryContextSnapshotRepository()
    request_render_snapshots = InMemoryContextRequestRenderSnapshotRepository()
    workspace_service = ContextWorkspaceService(
        workspace_repository=workspaces,
        node_repository=nodes,
    )
    tree_service = ContextTreeService(
        workspace_repository=workspaces,
        node_repository=nodes,
        operation_repository=operations,
    )
    workspace_service.ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:context",
            agent_id="assistant",
            refresh_expanded_children=False,
        ),
    )
    tree_service.upsert_nodes(
        ContextNodeUpsertInput(
            session_key="session:context",
            action=ContextAction.UPSERT,
            nodes=(
                *(
                    ContextNodeSeed(
                        node_id=f"session.item.old-{index}",
                        parent_id="session.current",
                        owner="session",
                        kind="session_item",
                        title=f"Old Message {index}",
                        summary=large_history_text,
                        content=large_history_text,
                        state=ContextNodeState(included_in_next_slice=True),
                        owner_ref={
                            "session_item_id": f"item-old-{index}",
                            "role": "assistant",
                        },
                    )
                    for index in range(120)
                ),
                ContextNodeSeed(
                    node_id="session.item.frontier",
                    parent_id="session.current",
                    owner="session",
                    kind="session_item",
                    title="Current User Message",
                    summary="frontier task",
                    content="stale frontier tree content must not render",
                    state=ContextNodeState(included_in_next_slice=True),
                    owner_ref={
                        "session_item_id": "item-user-1",
                        "role": "user",
                    },
                ),
                ContextNodeSeed(
                    node_id="tools.capability.search",
                    parent_id="tools.available",
                    owner="tool",
                    kind="tool_function",
                    title="capability.search",
                    summary="Find available capabilities.",
                    state=ContextNodeState(loaded=True),
                    owner_ref={
                        "source_id": "configured.capability",
                        "tool_id": "capability.search",
                    },
                ),
            ),
        ),
    )
    adapter = ContextWorkspaceRunSnapshotAdapter(
        workspace_service=workspace_service,
        render_service=ContextObservationSnapshotService(
            workspace_repository=workspaces,
            node_repository=nodes,
            snapshot_repository=snapshots,
        ),
        tree_service=tree_service,
        control_slice_builder=ContextControlSliceService(
            workspace_repository=workspaces,
            node_repository=nodes,
        ),
        slice_builder=ContextSliceBuilderService(
            workspace_repository=workspaces,
            node_repository=nodes,
            session_item_resolver=resolver,
        ),
        request_render_snapshot_service=RequestRenderSnapshotService(
            workspace_repository=workspaces,
            snapshot_repository=request_render_snapshots,
        ),
    )

    snapshot_record = adapter.record_run_request_render_snapshot(
        run=_run(),
        draft=_draft(
            tool_schemas=(
                ToolSchema(
                    name="capability.search",
                    description="Find tools and capabilities.",
                ),
                *(
                    ToolSchema(
                        name=f"unused.tool_{index}",
                        description="Unused tool.",
                    )
                    for index in range(50)
                ),
            ),
        ),
    )

    assert snapshot_record is not None
    assert resolver.resolved_ids == ["item-user-1"]
    assert snapshot_record.projected_input_items == (
        {
            "kind": "message",
            "payload": {
                "role": "user",
                "content": [{"type": "text", "text": "frontier task only"}],
            },
            "source": "context_slice",
            "metadata": {
                "owner": "session",
                "kind": "session_item",
                "session_item_id": "item-user-1",
                "node_id": "session.item.frontier",
                "sequence_no": 121,
            },
        },
    )
    assert tuple(schema.name for schema in snapshot_record.tool_schemas) == (
        "capability.search",
    )
    rendered = str(snapshot_record.projected_input_items)
    assert "archived-history-body" not in rendered
    assert "stale frontier tree content" not in rendered
    cost = snapshot_record.metadata["request_render_cost"]
    assert cost["selected_session_item_count"] == 1
    assert cost["projected_input_item_count"] == 1
    assert cost["provider_visible_tool_count"] == 1
    assert cost["rendered_input_char_count"] < 600
    assert snapshot_record.metadata["context_slice_omitted_node_count"] >= 120
    persisted_request_snapshot = request_render_snapshots.get(
        snapshot_record.snapshot_id,
    )
    assert persisted_request_snapshot is not None
    assert persisted_request_snapshot.render_report["cost"] == cost


def test_context_workspace_snapshot_projects_only_model_history_session_items_once() -> None:
    class _SessionItemResolver:
        def get_item(self, item_id: str):  # type: ignore[no-untyped-def]
            items = {
                "item-user-1": {
                    "kind": "user_message",
                    "role": "user",
                    "sequence_no": 1,
                    "content_payload": {
                        "blocks": [{"type": "text", "text": "live user task"}],
                    },
                    "metadata": {},
                    "provider_item_type": None,
                },
                "item-reasoning": {
                    "kind": "reasoning",
                    "role": "assistant",
                    "sequence_no": 2,
                    "content_payload": {
                        "text": "**Internal plan**\n\nDo not replay as chat.",
                    },
                    "metadata": {"runtime_semantic_kind": "runtime.reasoning"},
                    "provider_item_type": "reasoning",
                },
                "item-progress": {
                    "kind": "agent_progress",
                    "role": "assistant",
                    "sequence_no": 3,
                    "content_payload": {
                        "text": "**Progress**\n\nDo not replay as chat.",
                    },
                    "metadata": {
                        "runtime_semantic_kind": "runtime.assistant_progress",
                    },
                    "provider_item_type": "reasoning",
                },
            }
            data = items[item_id]
            return type(
                "SessionItem",
                (),
                {
                    "id": item_id,
                    "session_id": "session-instance-1",
                    "sequence_no": data["sequence_no"],
                    "kind": data["kind"],
                    "role": data["role"],
                    "model_visible": True,
                    "source_kind": "llm_response_item",
                    "provider_item_type": data["provider_item_type"],
                    "content_payload": data["content_payload"],
                    "metadata": data["metadata"],
                },
            )()

    workspaces = InMemoryContextWorkspaceRepository()
    nodes = InMemoryContextNodeRepository()
    operations = InMemoryContextOperationRepository()
    snapshots = InMemoryContextSnapshotRepository()
    request_render_snapshots = InMemoryContextRequestRenderSnapshotRepository()
    workspace_service = ContextWorkspaceService(
        workspace_repository=workspaces,
        node_repository=nodes,
    )
    tree_service = ContextTreeService(
        workspace_repository=workspaces,
        node_repository=nodes,
        operation_repository=operations,
    )
    workspace_service.ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:context",
            agent_id="assistant",
            refresh_expanded_children=False,
        ),
    )
    tree_service.upsert_nodes(
        ContextNodeUpsertInput(
            session_key="session:context",
            action=ContextAction.UPSERT,
            nodes=(
                ContextNodeSeed(
                    node_id="session.item.user.a",
                    parent_id="session.current",
                    owner="session",
                    kind="session_item",
                    title="User Message",
                    state=ContextNodeState(included_in_next_slice=True),
                    owner_ref={"session_item_id": "item-user-1"},
                ),
                ContextNodeSeed(
                    node_id="session.item.user.b",
                    parent_id="session.current",
                    owner="session",
                    kind="session_item",
                    title="Duplicate User Message",
                    state=ContextNodeState(included_in_next_slice=True),
                    owner_ref={"session_item_id": "item-user-1"},
                ),
                ContextNodeSeed(
                    node_id="session.item.reasoning",
                    parent_id="session.current",
                    owner="session",
                    kind="session_item",
                    title="Reasoning Summary",
                    state=ContextNodeState(included_in_next_slice=True),
                    owner_ref={"session_item_id": "item-reasoning"},
                ),
                ContextNodeSeed(
                    node_id="session.item.progress",
                    parent_id="session.current",
                    owner="session",
                    kind="session_item",
                    title="Agent Progress",
                    state=ContextNodeState(included_in_next_slice=True),
                    owner_ref={"session_item_id": "item-progress"},
                ),
            ),
        ),
    )
    adapter = ContextWorkspaceRunSnapshotAdapter(
        workspace_service=workspace_service,
        render_service=ContextObservationSnapshotService(
            workspace_repository=workspaces,
            node_repository=nodes,
            snapshot_repository=snapshots,
        ),
        tree_service=tree_service,
        control_slice_builder=ContextControlSliceService(
            workspace_repository=workspaces,
            node_repository=nodes,
        ),
        slice_builder=ContextSliceBuilderService(
            workspace_repository=workspaces,
            node_repository=nodes,
            session_item_resolver=_SessionItemResolver(),
        ),
        request_render_snapshot_service=RequestRenderSnapshotService(
            workspace_repository=workspaces,
            snapshot_repository=request_render_snapshots,
        ),
    )

    snapshot_record = adapter.record_run_request_render_snapshot(
        run=_run(),
        draft=_draft(),
    )

    assert snapshot_record is not None
    assert snapshot_record.projected_input_items == (
        {
            "kind": "message",
            "payload": {
                "role": "user",
                "content": [{"type": "text", "text": "live user task"}],
            },
            "source": "context_slice",
            "metadata": {
                "owner": "session",
                "kind": "session_item",
                "session_item_id": "item-user-1",
                "node_id": "session.item.user.a",
                "sequence_no": 1,
            },
        },
    )
    rendered = str(snapshot_record.projected_input_items)
    assert "Internal plan" not in rendered
    assert "Progress" not in rendered


def test_context_slice_does_not_fallback_to_draft_tool_schemas() -> None:
    class _SessionItemResolver:
        def get_item(self, item_id: str):  # type: ignore[no-untyped-def]
            assert item_id == "item-user-1"
            return type(
                "SessionItem",
                (),
                {
                    "id": "item-user-1",
                    "session_id": "session-instance-1",
                    "sequence_no": 1,
                    "role": "user",
                    "content_payload": {
                        "blocks": [{"type": "text", "text": "live slice task"}],
                    },
                    "metadata": {},
                },
            )()

    workspaces = InMemoryContextWorkspaceRepository()
    nodes = InMemoryContextNodeRepository()
    operations = InMemoryContextOperationRepository()
    snapshots = InMemoryContextSnapshotRepository()
    request_render_snapshots = InMemoryContextRequestRenderSnapshotRepository()
    workspace_service = ContextWorkspaceService(
        workspace_repository=workspaces,
        node_repository=nodes,
    )
    tree_service = ContextTreeService(
        workspace_repository=workspaces,
        node_repository=nodes,
        operation_repository=operations,
    )
    workspace_service.ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:context",
            agent_id="assistant",
            refresh_expanded_children=False,
        ),
    )
    tree_service.upsert_nodes(
        ContextNodeUpsertInput(
            session_key="session:context",
            action=ContextAction.UPSERT,
            nodes=(
                ContextNodeSeed(
                    node_id="session.step.item.current-user",
                    parent_id="session.current",
                    owner="session",
                    kind="session_item",
                    title="User Message",
                    state=ContextNodeState(included_in_next_slice=True),
                    owner_ref={
                        "session_item_id": "item-user-1",
                        "role": "user",
                    },
                ),
            ),
        ),
    )
    adapter = ContextWorkspaceRunSnapshotAdapter(
        workspace_service=workspace_service,
        render_service=ContextObservationSnapshotService(
            workspace_repository=workspaces,
            node_repository=nodes,
            snapshot_repository=snapshots,
        ),
        tree_service=tree_service,
        control_slice_builder=ContextControlSliceService(
            workspace_repository=workspaces,
            node_repository=nodes,
        ),
        slice_builder=ContextSliceBuilderService(
            workspace_repository=workspaces,
            node_repository=nodes,
            session_item_resolver=_SessionItemResolver(),
        ),
        request_render_snapshot_service=RequestRenderSnapshotService(
            workspace_repository=workspaces,
            snapshot_repository=request_render_snapshots,
        ),
    )

    snapshot_record = adapter.record_run_request_render_snapshot(
        run=_run(),
        draft=_draft(tool_schemas=(ToolSchema(name="command.exec"),)),
    )

    assert snapshot_record is not None
    assert snapshot_record.metadata["request_context_source"] == "context_slice"
    assert snapshot_record.projected_input_items
    assert snapshot_record.tool_schemas == ()
    assert snapshot_record.tool_schema_refs == ()


def test_context_workspace_snapshot_merges_execution_chain_protocol_refs() -> None:
    workspaces = InMemoryContextWorkspaceRepository()
    nodes = InMemoryContextNodeRepository()
    snapshots = InMemoryContextSnapshotRepository()
    adapter = ContextWorkspaceRunSnapshotAdapter(
        workspace_service=ContextWorkspaceService(
            workspace_repository=workspaces,
            node_repository=nodes,
        ),
        render_service=ContextObservationSnapshotService(
            workspace_repository=workspaces,
            node_repository=nodes,
            snapshot_repository=snapshots,
        ),
    )

    execution_ref = {
        "owner_module": "session",
        "owner_kind": "session_item",
        "owner_id": "item-result-1",
        "item_id": "item-result-1",
        "session_item_id": "item-result-1",
        "execution_step_item_id": "item-exec-result-1",
        "execution_step_id": "step-tools",
        "execution_chain_id": "chain-run-context",
        "turn_id": "run-context",
        "kind": "tool_result",
        "tool_call_id": "call-weather-1",
        "tool_name": "weather.lookup",
        "tool_run_id": "tool-run-1",
        "result_session_item_id": "item-result-1",
        "protocol_required": True,
        "budget_class": "protocol_required",
        "render_mode": "ref",
        "render_scope": "provider_replay",
    }
    with pytest.raises(RuntimeError, match="Context Slice builder is required"):
        adapter.record_run_request_render_snapshot(
            run=_run(),
            draft=_draft(
                transcript_budget={
                    "source": "session_items",
                    "protocol_required_refs": [execution_ref],
                    "execution_chain_protocol_required_refs": [execution_ref],
                    "execution_chain_protocol_required_ref_count": 1,
                    "protocol_required_preserved": True,
                },
            ),
        )
    assert snapshots.get_by_run("run-context") is None


def test_context_workspace_snapshot_projects_execution_protocol_refs_from_session_items() -> None:
    class _SessionItemResolver:
        def get_item(self, item_id: str):  # type: ignore[no-untyped-def]
            items = {
                "item-call-1": {
                    "kind": "tool_call",
                    "role": "assistant",
                    "sequence_no": 2,
                    "content_payload": {
                        "call_id": "call-weather-1",
                        "name": "weather.lookup",
                        "arguments": {"city": "Kunming"},
                    },
                    "metadata": {},
                    "call_id": "call-weather-1",
                    "tool_name": "weather.lookup",
                },
                "item-result-1": {
                    "kind": "tool_result",
                    "role": "tool",
                    "sequence_no": 3,
                    "content_payload": {
                        "tool_call_id": "call-weather-1",
                        "tool_name": "weather.lookup",
                        "content": [{"type": "text", "text": "sunny"}],
                    },
                    "metadata": {"tool_call_id": "call-weather-1"},
                    "call_id": "call-weather-1",
                    "tool_name": "weather.lookup",
                },
                "item-result-orphan": {
                    "kind": "tool_result",
                    "role": "tool",
                    "sequence_no": 4,
                    "content_payload": {
                        "tool_call_id": "call-orphan",
                        "tool_name": "weather.lookup",
                        "content": [{"type": "text", "text": "orphan"}],
                    },
                    "metadata": {"tool_call_id": "call-orphan"},
                    "call_id": "call-orphan",
                    "tool_name": "weather.lookup",
                },
            }
            data = items[item_id]
            return type(
                "SessionItem",
                (),
                {
                    "id": item_id,
                    "session_id": "session-instance-1",
                    "sequence_no": data["sequence_no"],
                    "kind": data["kind"],
                    "role": data["role"],
                    "model_visible": True,
                    "source_kind": "llm_response_item",
                    "provider_item_type": None,
                    "call_id": data["call_id"],
                    "tool_name": data["tool_name"],
                    "content_payload": data["content_payload"],
                    "metadata": data["metadata"],
                },
            )()

    workspaces = InMemoryContextWorkspaceRepository()
    nodes = InMemoryContextNodeRepository()
    operations = InMemoryContextOperationRepository()
    snapshots = InMemoryContextSnapshotRepository()
    request_render_snapshots = InMemoryContextRequestRenderSnapshotRepository()
    workspace_service = ContextWorkspaceService(
        workspace_repository=workspaces,
        node_repository=nodes,
    )
    tree_service = ContextTreeService(
        workspace_repository=workspaces,
        node_repository=nodes,
        operation_repository=operations,
    )
    workspace_service.ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:context",
            agent_id="assistant",
            refresh_expanded_children=False,
        ),
    )
    protocol_refs = [
        {
            "owner_module": "session",
            "owner_kind": "session_item",
            "owner_id": "item-call-1",
            "item_id": "item-call-1",
            "session_item_id": "item-call-1",
            "execution_step_item_id": "item-exec-call-1",
            "kind": "tool_call",
            "tool_call_id": "call-weather-1",
            "tool_name": "weather.lookup",
            "call_session_item_id": "item-call-1",
            "protocol_required": True,
        },
        {
            "owner_module": "session",
            "owner_kind": "session_item",
            "owner_id": "item-result-1",
            "item_id": "item-result-1",
            "session_item_id": "item-result-1",
            "execution_step_item_id": "item-exec-result-1",
            "kind": "tool_result",
            "tool_call_id": "call-weather-1",
            "tool_name": "weather.lookup",
            "result_session_item_id": "item-result-1",
            "protocol_required": True,
        },
        {
            "owner_module": "session",
            "owner_kind": "session_item",
            "owner_id": "item-result-orphan",
            "item_id": "item-result-orphan",
            "session_item_id": "item-result-orphan",
            "execution_step_item_id": "item-exec-result-orphan",
            "kind": "tool_result",
            "tool_call_id": "call-orphan",
            "tool_name": "weather.lookup",
            "result_session_item_id": "item-result-orphan",
            "protocol_required": True,
        },
    ]
    adapter = ContextWorkspaceRunSnapshotAdapter(
        workspace_service=workspace_service,
        render_service=ContextObservationSnapshotService(
            workspace_repository=workspaces,
            node_repository=nodes,
            snapshot_repository=snapshots,
        ),
        tree_service=tree_service,
        control_slice_builder=ContextControlSliceService(
            workspace_repository=workspaces,
            node_repository=nodes,
        ),
        slice_builder=ContextSliceBuilderService(
            workspace_repository=workspaces,
            node_repository=nodes,
            session_item_resolver=_SessionItemResolver(),
        ),
        request_render_snapshot_service=RequestRenderSnapshotService(
            workspace_repository=workspaces,
            snapshot_repository=request_render_snapshots,
        ),
    )

    snapshot_record = adapter.record_run_request_render_snapshot(
        run=_run(),
        draft=_draft(
            transcript_budget={
                "source": "session_items",
                "protocol_required_refs": protocol_refs,
                "execution_chain_protocol_required_refs": protocol_refs,
                "execution_chain_protocol_required_ref_count": 2,
                "protocol_required_preserved": True,
            },
        ),
    )

    assert snapshot_record is not None
    assert snapshot_record.projected_input_items == (
        {
            "kind": "function_call",
            "payload": {
                "type": "function_call",
                "call_id": "call-weather-1",
                "name": "weather.lookup",
                "arguments": {"city": "Kunming"},
            },
            "source": "context_slice",
            "metadata": {
                "owner": "session",
                "kind": "runtime_assistant_tool_call",
                "session_item_id": "item-call-1",
                "node_id": "protocol.session_item.item-call-1",
                "sequence_no": 2,
                "tool_call_id": "call-weather-1",
                "tool_name": "weather.lookup",
            },
        },
        {
            "kind": "function_call_output",
            "payload": {
                "type": "function_call_output",
                "call_id": "call-weather-1",
                "output": [{"type": "text", "text": "sunny"}],
            },
            "source": "context_slice",
            "metadata": {
                "owner": "session",
                "kind": "runtime_tool_result",
                "session_item_id": "item-result-1",
                "node_id": "protocol.session_item.item-result-1",
                "sequence_no": 3,
                "tool_call_id": "call-weather-1",
                "tool_name": "weather.lookup",
            },
        },
    )
    assert "orphan" not in str(snapshot_record.projected_input_items)


def test_context_workspace_adapter_forwards_runtime_request_flow_default_tool_schemas() -> None:
    workspaces = InMemoryContextWorkspaceRepository()
    nodes = InMemoryContextNodeRepository()
    snapshots = InMemoryContextSnapshotRepository()
    workspace_service = ContextWorkspaceService(
        workspace_repository=workspaces,
        node_repository=nodes,
    )
    tree_service = ContextTreeService(
        workspace_repository=workspaces,
        node_repository=nodes,
        operation_repository=InMemoryContextOperationRepository(),
    )
    adapter = ContextWorkspaceRunSnapshotAdapter(
        workspace_service=workspace_service,
        render_service=ContextObservationSnapshotService(
            workspace_repository=workspaces,
            node_repository=nodes,
            snapshot_repository=snapshots,
        ),
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
            parent_node_id="tools.available",
            action=ContextAction.EXPAND,
            nodes=(
                ContextNodeSeed(
                    node_id="tools.tool.fetch_weather",
                    parent_id="tools.available",
                    owner="tool",
                    kind="tool_function",
                    title="Fetch Weather",
                    summary="Fetch current weather for a location.",
                    state=ContextNodeState(collapsed=False, loaded=True),
                    owner_ref={"tool_id": "fetch_weather"},
                ),
            ),
        ),
    )

    with pytest.raises(RuntimeError, match="Context Slice builder is required"):
        adapter.record_run_request_render_snapshot(
            run=_run(),
            draft=_draft(
                tool_schemas=(
                    ToolSchema(name="fetch_weather", description="Fetch weather."),
                ),
                flow_hint={
                    "default_tool_schema_ids": ["fetch_weather"],
                    "default_tool_schema_source": "runtime_policy.browser_bootstrap",
                },
            ),
        )
    snapshot = snapshots.get_by_run("run-context")
    tree = tree_service.list_tree("session:context")
    tool_node = next(node for node in tree.nodes if node.id == "tools.tool.fetch_weather")

    assert snapshot is None
    assert tool_node.state.schema_enabled is False


def test_context_workspace_adapter_expands_runtime_request_flow_tool_schema_groups() -> None:
    workspaces = InMemoryContextWorkspaceRepository()
    nodes = InMemoryContextNodeRepository()
    snapshots = InMemoryContextSnapshotRepository()
    workspace_service = ContextWorkspaceService(
        workspace_repository=workspaces,
        node_repository=nodes,
    )
    tree_service = ContextTreeService(
        workspace_repository=workspaces,
        node_repository=nodes,
        operation_repository=InMemoryContextOperationRepository(),
    )
    adapter = ContextWorkspaceRunSnapshotAdapter(
        workspace_service=workspace_service,
        render_service=ContextObservationSnapshotService(
            workspace_repository=workspaces,
            node_repository=nodes,
            snapshot_repository=snapshots,
        ),
        tree_service=tree_service,
    )
    workspace_service.ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:context",
            agent_id="assistant",
        ),
    )
    common_actions = (ContextAction.EXPAND, ContextAction.COLLAPSE)
    tree_service.upsert_nodes(
        ContextNodeUpsertInput(
            session_key="session:context",
            parent_node_id="tools.available",
            action=ContextAction.EXPAND,
            nodes=(
                ContextNodeSeed(
                    node_id="tools.bundle.bundled.local_package.browser",
                    parent_id="tools.available",
                    owner="tool",
                    kind="tool_bundle",
                    title="Browser",
                    summary="Browser tools.",
                    state=ContextNodeState(collapsed=True, loaded=True),
                    actions=common_actions,
                    owner_ref={"source_id": "bundled.local_package.browser"},
                    metadata={"source_id": "bundled.local_package.browser"},
                ),
                ContextNodeSeed(
                    node_id="tools.bundle.bundled.local_package.browser.group.observation",
                    parent_id="tools.bundle.bundled.local_package.browser",
                    owner="tool",
                    kind="tool_bundle_group",
                    title="Browser Observation",
                    summary="Observe browser state.",
                    state=ContextNodeState(collapsed=True, loaded=True),
                    actions=common_actions,
                    owner_ref={
                        "source_id": "bundled.local_package.browser",
                        "group_key": "observation",
                    },
                    metadata={
                        "default_tool_schema_ids": ["browser.observe"],
                        "default_tool_schema_source": (
                            "bundled.local_package.browser.runtime_request_group.observation"
                        ),
                        "default_tool_schema_max_count": 1,
                    },
                ),
                ContextNodeSeed(
                    node_id="tools.tool.browser.observe",
                    parent_id="tools.bundle.bundled.local_package.browser.group.observation",
                    owner="tool",
                    kind="tool_function",
                    title="browser.observe",
                    summary="Inspect page state.",
                    state=ContextNodeState(collapsed=False, loaded=True),
                    owner_ref={"tool_id": "browser.observe"},
                ),
            ),
        ),
    )

    with pytest.raises(RuntimeError, match="Context Slice builder is required"):
        adapter.record_run_request_render_snapshot(
            run=_run(),
            draft=_draft(
                tool_schemas=(
                    ToolSchema(
                        name="browser.observe",
                        description="Inspect browser page state.",
                    ),
                ),
                flow_hint={
                    "default_tool_schema_group_refs": [
                        {
                            "source_id": "bundled.local_package.browser",
                            "group_key": "observation",
                        },
                    ],
                },
            ),
        )
    snapshot = snapshots.get_by_run("run-context")
    tree = tree_service.list_tree("session:context")
    group_node = next(
        node
        for node in tree.nodes
        if node.id == "tools.bundle.bundled.local_package.browser.group.observation"
    )
    tool_node = next(node for node in tree.nodes if node.id == "tools.tool.browser.observe")

    assert snapshot is None
    assert group_node.state.collapsed is False
    assert tool_node.state.schema_enabled is False


def test_context_workspace_adapter_uses_tool_catalog_for_default_schema_groups_without_tree_expand() -> None:
    class _RuntimeRequestCatalog:
        def list_runtime_request_bundles(self, function_ids):  # type: ignore[no-untyped-def]
            return (
                ToolRuntimeRequestBundle(
                    source_id="bundled.local_package.browser",
                    title="Browser",
                    summary="Browser tools.",
                    source_kind="local_package",
                    function_ids=("browser.observe",),
                    function_count=1,
                    groups=(
                        ToolRuntimeRequestBundleGroup(
                            group_key="observation",
                            title="Browser Observation",
                            summary="Observe browser state.",
                            function_ids=("browser.observe",),
                            function_count=1,
                            metadata={
                                "default_tool_schema_ids": ["browser.observe"],
                                "default_tool_schema_source": (
                                    "bundled.local_package.browser.runtime_request_group.observation"
                                ),
                                "default_tool_schema_max_count": 1,
                                "order": 20,
                            },
                        ),
                    ),
                    metadata={
                        "runtime_request": {
                            "default_tool_schema_policy": {"priority": 20},
                            "default_tool_schema_group_refs": [
                                {
                                    "source_id": "bundled.local_package.browser",
                                    "group_key": "observation",
                                },
                            ],
                        },
                    },
                ),
            )

    workspaces = InMemoryContextWorkspaceRepository()
    nodes = InMemoryContextNodeRepository()
    snapshots = InMemoryContextSnapshotRepository()
    workspace_service = ContextWorkspaceService(
        workspace_repository=workspaces,
        node_repository=nodes,
    )
    tree_service = ContextTreeService(
        workspace_repository=workspaces,
        node_repository=nodes,
        operation_repository=InMemoryContextOperationRepository(),
    )
    adapter = ContextWorkspaceRunSnapshotAdapter(
        workspace_service=workspace_service,
        render_service=ContextObservationSnapshotService(
            workspace_repository=workspaces,
            node_repository=nodes,
            snapshot_repository=snapshots,
        ),
        tree_service=tree_service,
        runtime_request_catalog=_RuntimeRequestCatalog(),
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
            parent_node_id="tools.available",
            action=ContextAction.EXPAND,
            nodes=(
                ContextNodeSeed(
                    node_id="tools.bundle.bundled.local_package.browser",
                    parent_id="tools.available",
                    owner="tool",
                    kind="tool_bundle",
                    title="Browser",
                    summary="Browser tools.",
                    state=ContextNodeState(collapsed=True, loaded=True),
                    actions=(ContextAction.EXPAND, ContextAction.COLLAPSE),
                    owner_ref={"source_id": "bundled.local_package.browser"},
                    metadata={"source_id": "bundled.local_package.browser"},
                ),
                ContextNodeSeed(
                    node_id="tools.bundle.bundled.local_package.browser.group.observation",
                    parent_id="tools.bundle.bundled.local_package.browser",
                    owner="tool",
                    kind="tool_bundle_group",
                    title="Browser Observation",
                    summary="Observe browser state.",
                    state=ContextNodeState(collapsed=True, loaded=True),
                    actions=(ContextAction.EXPAND, ContextAction.COLLAPSE),
                    owner_ref={
                        "source_id": "bundled.local_package.browser",
                        "group_key": "observation",
                    },
                    metadata={
                        "default_tool_schema_ids": ["browser.observe"],
                    },
                ),
            ),
        ),
    )

    with pytest.raises(RuntimeError, match="Context Slice builder is required"):
        adapter.record_run_request_render_snapshot(
            run=_run(),
            draft=_draft(
                tool_schemas=(
                    ToolSchema(
                        name="browser.observe",
                        description="Inspect browser page state.",
                    ),
                ),
                flow_hint={
                    "default_tool_schema_group_refs": [
                        {
                            "source_id": "bundled.local_package.browser",
                            "group_key": "observation",
                        },
                    ],
                },
            ),
        )
    tree = tree_service.list_tree("session:context")
    group_node = next(
        node
        for node in tree.nodes
        if node.id == "tools.bundle.bundled.local_package.browser.group.observation"
    )

    assert group_node.state.collapsed is True


def test_context_workspace_adapter_does_not_bootstrap_browser_schemas_from_source_policy() -> None:
    workspaces = InMemoryContextWorkspaceRepository()
    nodes = InMemoryContextNodeRepository()
    snapshots = InMemoryContextSnapshotRepository()
    workspace_service = ContextWorkspaceService(
        workspace_repository=workspaces,
        node_repository=nodes,
    )
    tree_service = ContextTreeService(
        workspace_repository=workspaces,
        node_repository=nodes,
        operation_repository=InMemoryContextOperationRepository(),
    )
    adapter = ContextWorkspaceRunSnapshotAdapter(
        workspace_service=workspace_service,
        render_service=ContextObservationSnapshotService(
            workspace_repository=workspaces,
            node_repository=nodes,
            snapshot_repository=snapshots,
        ),
        tree_service=tree_service,
    )
    workspace_service.ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:context",
            agent_id="assistant",
        ),
    )
    group_defaults = {
        "navigation": ("browser.navigate", "browser.tabs.list"),
        "observation": ("browser.observe",),
        "network": ("browser.network.inspect",),
        "code_insight": ("browser.runtime.inspect", "browser.script.find_request"),
        "action_trace": ("browser.action.trace",),
    }
    common_actions = (ContextAction.EXPAND, ContextAction.COLLAPSE)
    tree_service.upsert_nodes(
        ContextNodeUpsertInput(
            session_key="session:context",
            parent_node_id="tools.available",
            action=ContextAction.EXPAND,
            nodes=(
                ContextNodeSeed(
                    node_id="tools.bundle.bundled.local_package.browser",
                    parent_id="tools.available",
                    owner="tool",
                    kind="tool_bundle",
                    title="Browser",
                    summary="Browser tools.",
                    state=ContextNodeState(collapsed=True, loaded=True),
                    actions=common_actions,
                    owner_ref={"source_id": "bundled.local_package.browser"},
                    metadata={
                        "source_id": "bundled.local_package.browser",
                        "runtime_request": {
                            "default_tool_schema_group_refs": [
                                {
                                    "source_id": "bundled.local_package.browser",
                                    "group_key": group_key,
                                    "reason": f"browser_starter_{group_key}",
                                }
                                for group_key in group_defaults
                            ],
                        },
                    },
                ),
                *(
                    seed
                    for index, (group_key, tool_ids) in enumerate(
                        group_defaults.items(),
                        start=1,
                    )
                    for seed in (
                        _browser_group_seed(
                            group_key=group_key,
                            tool_ids=tool_ids,
                            display_order=index * 10,
                        ),
                        *(
                            _browser_tool_seed(
                                tool_id=tool_id,
                                parent_id=(
                                    "tools.bundle.bundled.local_package.browser"
                                    f".group.{group_key}"
                                ),
                                display_order=tool_index * 10,
                            )
                            for tool_index, tool_id in enumerate(tool_ids, start=1)
                        ),
                    )
                ),
            ),
        ),
    )

    with pytest.raises(RuntimeError, match="Context Slice builder is required"):
        adapter.record_run_request_render_snapshot(
            run=_run(),
            draft=_draft(
                tool_schemas=tuple(
                    ToolSchema(name=tool_id, description=f"{tool_id} tool.")
                    for tool_ids in group_defaults.values()
                    for tool_id in tool_ids
                ),
            ),
        )
    snapshot = snapshots.get_by_run("run-context")

    assert snapshot is None


def test_preview_request_render_snapshot_does_not_mutate_existing_workspace() -> None:
    class _NoDebugRenderSnapshotService(ContextObservationSnapshotService):
        def render_observation(self, data):  # type: ignore[no-untyped-def]
            raise AssertionError("preview hot path must not render full debug body")

    class _ReadOnlyNodeRepository(InMemoryContextNodeRepository):
        def save(self, node):  # type: ignore[no-untyped-def]
            raise AssertionError("preview hot path must not save context nodes")

        def save_many(self, nodes):  # type: ignore[no-untyped-def]
            raise AssertionError("preview hot path must not save context nodes")

    workspaces = InMemoryContextWorkspaceRepository()
    nodes = _ReadOnlyNodeRepository()
    snapshots = InMemoryContextSnapshotRepository()
    workspace = ContextWorkspace.new(
        session_key="session:context",
        agent_id="assistant",
        metadata={"existing": True},
    )
    workspaces.add(workspace)
    adapter = ContextWorkspaceRunSnapshotAdapter(
        workspace_service=ContextWorkspaceService(
            workspace_repository=workspaces,
            node_repository=nodes,
        ),
        render_service=_NoDebugRenderSnapshotService(
            workspace_repository=workspaces,
            node_repository=nodes,
            snapshot_repository=snapshots,
        ),
        tree_service=ContextTreeService(
            workspace_repository=workspaces,
            node_repository=nodes,
            operation_repository=InMemoryContextOperationRepository(),
        ),
        control_slice_builder=ContextControlSliceService(
            workspace_repository=workspaces,
            node_repository=nodes,
        ),
    )

    snapshot_record = adapter.preview_run_request_render_snapshot(
        run=_run(),
        draft=_draft(tool_schemas=(ToolSchema(name="fetch_weather"),)),
    )

    assert snapshot_record is not None
    assert snapshot_record.snapshot_id == "ctxpreview_run-context"
    assert workspaces.get_by_session("session:context") is workspace
    assert workspace.metadata == {"existing": True}
    assert snapshot_record.metadata["control_slice_id"].startswith("ctxctrl_")
    assert snapshot_record.metadata["control_slice_selected_ref_count"] == 0
    assert snapshot_record.metadata["request_render_snapshot"]["timings"][
        "build_control_slice_ms"
    ] >= 0
    request_render_cost = snapshot_record.metadata["request_render_cost"]
    assert request_render_cost["selected_session_item_count"] == 0
    assert request_render_cost["provider_visible_tool_count"] == 0
    assert request_render_cost["projected_input_item_count"] == 0
    assert request_render_cost["rendered_input_char_count"] > 0
    assert request_render_cost["elapsed_ms"] >= 0
    assert snapshot_record.metadata["request_render_snapshot"]["cost"] == request_render_cost


def test_context_workspace_snapshot_metadata_locates_session_item_nodes() -> None:
    workspaces = InMemoryContextWorkspaceRepository()
    nodes = InMemoryContextNodeRepository()
    snapshots = InMemoryContextSnapshotRepository()
    workspace_service = ContextWorkspaceService(
        workspace_repository=workspaces,
        node_repository=nodes,
    )
    tree_service = ContextTreeService(
        workspace_repository=workspaces,
        node_repository=nodes,
        operation_repository=InMemoryContextOperationRepository(),
    )
    adapter = ContextWorkspaceRunSnapshotAdapter(
        workspace_service=workspace_service,
        render_service=ContextObservationSnapshotService(
            workspace_repository=workspaces,
            node_repository=nodes,
            snapshot_repository=snapshots,
        ),
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
            parent_node_id="session.current",
            action=ContextAction.EXPAND,
            nodes=(
                ContextNodeSeed(
                    node_id="session.items.current",
                    parent_id="session.current",
                    owner="session",
                    kind="session_item_range",
                    title="Current Items",
                    summary="Current active messages.",
                    state=ContextNodeState(collapsed=False, loaded=True),
                ),
                ContextNodeSeed(
                    node_id="session.item.session-instance-1.1",
                    parent_id="session.items.current",
                    owner="session",
                    kind="session_item",
                    title="1. user",
                    summary="Delivered as provider user message for this turn.",
                    state=ContextNodeState(collapsed=False, loaded=True),
                    owner_ref={
                        "session_id": "session-instance-1",
                        "message_id": "message-user-1",
                        "sequence_no": 1,
                    },
                ),
                ContextNodeSeed(
                    node_id="session.evidence.current",
                    parent_id="session.current",
                    owner="session",
                    kind="evidence_ledger",
                    title="Current Evidence Ledger",
                    summary="One compact evidence item.",
                    state=ContextNodeState(collapsed=False, loaded=True),
                ),
                ContextNodeSeed(
                    node_id="session.evidence.session-instance-1.call-weather",
                    parent_id="session.evidence.current",
                    owner="session",
                    kind="session_evidence",
                    title="observation: browser.network.replay_request",
                    summary="browser.network.replay_request succeeded.",
                    state=ContextNodeState(collapsed=False, loaded=True),
                    metadata={
                        "tool_name": "browser.network.replay_request",
                        "verified": True,
                        "facts": {"evidence_ref": "network-request"},
                    },
                    owner_ref={"evidence_lifecycle_status": "verified"},
                ),
            ),
        ),
    )

    snapshot_record = adapter.preview_run_request_render_snapshot(run=_run(), draft=_draft())

    assert snapshot_record is not None
    assert "tree_session_item_count" not in snapshot_record.metadata
    assert "session_item_node_refs" not in snapshot_record.metadata
    assert "tree_evidence_item_count" not in snapshot_record.metadata
    assert "evidence_node_refs" not in snapshot_record.metadata
    assert "node_estimate_breakdown" not in snapshot_record.metadata
    assert snapshot_record.metadata["draft_input_session_item_count"] == 0
    assert snapshot_record.metadata["request_context_source"] == "missing_context_slice"


def test_context_workspace_adapter_previews_context_snapshot_without_snapshot_write() -> None:
    workspaces = InMemoryContextWorkspaceRepository()
    nodes = InMemoryContextNodeRepository()
    snapshots = InMemoryContextSnapshotRepository()
    adapter = ContextWorkspaceRunSnapshotAdapter(
        workspace_service=ContextWorkspaceService(
            workspace_repository=workspaces,
            node_repository=nodes,
        ),
        render_service=ContextObservationSnapshotService(
            workspace_repository=workspaces,
            node_repository=nodes,
            snapshot_repository=snapshots,
        ),
    )

    snapshot_record = adapter.preview_run_request_render_snapshot(
        run=_run(),
        draft=_draft(
            tool_schemas=(ToolSchema(name="fetch_weather", description="Fetch weather."),),
        ),
    )

    assert snapshot_record is not None
    assert snapshot_record.snapshot_id == "ctxpreview_run-context"
    assert "context_slice" not in snapshot_record.metadata
    assert snapshot_record.tool_schemas == ()
    assert snapshot_record.included_node_ids == ()
    assert snapshot_record.metadata["request_context_source"] == "missing_context_slice"
    assert snapshot_record.metadata["request_render_snapshot"]["full_tree_rendered"] is False
    assert snapshots.get_by_run("run-context") is None


def test_context_workspace_adapter_returns_recorded_run_snapshot_when_available() -> None:
    workspaces = InMemoryContextWorkspaceRepository()
    nodes = InMemoryContextNodeRepository()
    snapshots = InMemoryContextSnapshotRepository()
    request_render_snapshots = InMemoryContextRequestRenderSnapshotRepository()
    adapter = ContextWorkspaceRunSnapshotAdapter(
        workspace_service=ContextWorkspaceService(
            workspace_repository=workspaces,
            node_repository=nodes,
        ),
        render_service=ContextObservationSnapshotService(
            workspace_repository=workspaces,
            node_repository=nodes,
            snapshot_repository=snapshots,
        ),
        slice_builder=ContextSliceBuilderService(
            workspace_repository=workspaces,
            node_repository=nodes,
        ),
        request_render_snapshot_service=RequestRenderSnapshotService(
            workspace_repository=workspaces,
            snapshot_repository=request_render_snapshots,
        ),
    )
    recorded = adapter.record_run_request_render_snapshot(
        run=_run(),
        draft=_draft(
            tool_schemas=(ToolSchema(name="fetch_weather", description="Fetch weather."),),
        ),
    )

    loaded = adapter.get_recorded_run_request_render_snapshot(
        run=_run(),
        draft=_draft(
            tool_schemas=(ToolSchema(name="fetch_weather", description="Fetch weather."),),
        ),
    )

    assert loaded is not None
    assert recorded is not None
    assert loaded.snapshot_id == recorded.snapshot_id
    assert loaded.metadata["snapshot_kind"] == "request_render"
    assert request_render_snapshots.get(recorded.snapshot_id) is not None
    assert loaded.metadata["request_context_source"] == "context_slice"


def test_context_workspace_adapter_does_not_read_full_snapshot_as_runtime_request() -> None:
    workspaces = InMemoryContextWorkspaceRepository()
    nodes = InMemoryContextNodeRepository()
    snapshots = InMemoryContextSnapshotRepository()
    workspace_service = ContextWorkspaceService(
        workspace_repository=workspaces,
        node_repository=nodes,
    )
    workspace = workspace_service.ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:context",
            agent_id="assistant",
        ),
    )
    snapshots.add(
        ContextSnapshot(
            id="ctx_full_legacy",
            workspace_id=workspace.id,
            session_key="session:context",
            run_id="run-context",
            tree_revision=workspace.active_revision,
            debug_body="<context_tree />",
            metadata={"snapshot_kind": "full_context"},
        ),
    )
    adapter = ContextWorkspaceRunSnapshotAdapter(
        workspace_service=workspace_service,
        render_service=ContextObservationSnapshotService(
            workspace_repository=workspaces,
            node_repository=nodes,
            snapshot_repository=snapshots,
        ),
    )

    loaded = adapter.get_recorded_run_request_render_snapshot(
        run=_run(),
        draft=_draft(),
    )

    assert loaded is None


def test_recorded_request_snapshot_requires_formal_request_render_snapshot() -> None:
    workspaces = InMemoryContextWorkspaceRepository()
    nodes = InMemoryContextNodeRepository()
    snapshots = InMemoryContextSnapshotRepository()
    workspace_service = ContextWorkspaceService(
        workspace_repository=workspaces,
        node_repository=nodes,
    )
    workspace = workspace_service.ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:context",
            agent_id="assistant",
        ),
    )
    snapshots.add(
        ContextSnapshot(
            id="ctx_request_legacy_mirror",
            workspace_id=workspace.id,
            session_key="session:context",
            run_id="run-context",
            tree_revision=workspace.active_revision,
            debug_body="",
            metadata={
                "snapshot_kind": "request_render",
                "mirrored_tool_schema_count": 1,
            },
            provider_attachments={
                "tool_schemas": [
                    ToolSchema(
                        name="legacy.mirror",
                        description="Legacy mirror schema.",
                    ).to_payload(),
                ],
            },
            included_refs=(
                {
                    "node_id": "legacy.node",
                    "owner_module": "session",
                    "owner_kind": "session_item",
                    "item_id": "legacy-item",
                },
            ),
        ),
    )
    adapter = ContextWorkspaceRunSnapshotAdapter(
        workspace_service=workspace_service,
        render_service=ContextObservationSnapshotService(
            workspace_repository=workspaces,
            node_repository=nodes,
            snapshot_repository=snapshots,
        ),
    )

    loaded = adapter.get_recorded_run_request_render_snapshot(
        run=_run(),
        draft=_draft(),
    )

    assert loaded is None


def test_context_workspace_adapter_records_parent_snapshot_reference() -> None:
    workspaces = InMemoryContextWorkspaceRepository()
    nodes = InMemoryContextNodeRepository()
    snapshots = InMemoryContextSnapshotRepository()
    adapter = ContextWorkspaceRunSnapshotAdapter(
        workspace_service=ContextWorkspaceService(
            workspace_repository=workspaces,
            node_repository=nodes,
        ),
        render_service=ContextObservationSnapshotService(
            workspace_repository=workspaces,
            node_repository=nodes,
            snapshot_repository=snapshots,
        ),
        slice_builder=ContextSliceBuilderService(
            workspace_repository=workspaces,
            node_repository=nodes,
        ),
    )
    first = adapter.record_run_request_render_snapshot(run=_run(), draft=_draft())
    assert first is not None
    first_stored = snapshots.get(first.snapshot_id)
    assert first_stored is not None
    run = _run()
    run.metadata["request_render_snapshot_id"] = first.snapshot_id

    second = adapter.record_run_request_render_snapshot(run=run, draft=_draft())

    assert second is not None
    assert second.parent_snapshot_id is None
    assert second.parent_tree_revision is None
    stored = snapshots.get(second.snapshot_id)
    assert stored is not None
    assert stored.parent_snapshot_id is None
    assert stored.parent_tree_revision is None


def test_context_workspace_adapter_records_agent_and_runtime_blocks_as_handle_nodes() -> None:
    workspaces = InMemoryContextWorkspaceRepository()
    nodes = InMemoryContextNodeRepository()
    snapshots = InMemoryContextSnapshotRepository()
    adapter = ContextWorkspaceRunSnapshotAdapter(
        workspace_service=ContextWorkspaceService(
            workspace_repository=workspaces,
            node_repository=nodes,
        ),
        render_service=ContextObservationSnapshotService(
            workspace_repository=workspaces,
            node_repository=nodes,
            snapshot_repository=snapshots,
        ),
    )

    snapshot_record = adapter.preview_run_request_render_snapshot(
        run=_run(),
        draft=_draft(
            system_messages=(
                ("agent_instruction", "Be precise."),
                ("runtime_context", "# Runtime Context\n\n- Agent: assistant"),
            ),
        ),
    )

    assert snapshot_record is not None
    rendered = adapter._render_service.render_observation(  # noqa: SLF001
        ContextObservationRenderInput(session_key="session:context", run_id="run-context"),
    )
    assert "agent.identity" in rendered.debug_body
    assert "run.environment" in rendered.debug_body
    assert "Be precise." not in rendered.debug_body


def test_context_workspace_adapter_renders_step_budget_in_runtime_context() -> None:
    workspaces = InMemoryContextWorkspaceRepository()
    nodes = InMemoryContextNodeRepository()
    snapshots = InMemoryContextSnapshotRepository()
    adapter = ContextWorkspaceRunSnapshotAdapter(
        workspace_service=ContextWorkspaceService(
            workspace_repository=workspaces,
            node_repository=nodes,
        ),
        render_service=ContextObservationSnapshotService(
            workspace_repository=workspaces,
            node_repository=nodes,
            snapshot_repository=snapshots,
        ),
    )

    snapshot_record = adapter.preview_run_request_render_snapshot(
        run=_run(),
        draft=_draft(
            runtime_context_overrides={
                "current_step": 29,
                "max_steps": 30,
                "remaining_steps": 1,
                "step_budget_status": "finalize_now",
            },
        ),
    )

    assert snapshot_record is not None
    rendered = adapter._render_service.render_observation(  # noqa: SLF001
        ContextObservationRenderInput(session_key="session:context", run_id="run-context"),
    )
    assert "- Step budget: 29/30 used; 1 remaining; status=finalize_now" in (
        rendered.debug_body
    )
    assert "finish with the best supported answer now" in rendered.debug_body


def test_context_workspace_adapter_mirrors_pinned_artifact_blocks(tmp_path) -> None:
    artifact_path = tmp_path / "image.png"
    artifact_path.write_bytes(b"png")
    workspaces = InMemoryContextWorkspaceRepository()
    nodes = InMemoryContextNodeRepository()
    operations = InMemoryContextOperationRepository()
    snapshots = InMemoryContextSnapshotRepository()
    workspace_service = ContextWorkspaceService(
        workspace_repository=workspaces,
        node_repository=nodes,
    )
    tree_service = ContextTreeService(
        workspace_repository=workspaces,
        node_repository=nodes,
        operation_repository=operations,
    )
    render_service = ContextObservationSnapshotService(
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
            action=ContextAction.PIN,
            nodes=(
                ContextNodeSeed(
                    node_id="artifacts.artifact.image-1",
                    parent_id="artifacts.session",
                    owner="artifacts",
                    kind="artifact_image",
                    title="image.png",
                    summary="Image artifact.",
                    state=ContextNodeState(loaded=True, pinned=True),
                    actions=(ContextAction.PIN, ContextAction.UNPIN),
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
    adapter = ContextWorkspaceRunSnapshotAdapter(
        workspace_service=workspace_service,
        render_service=render_service,
        artifact_service=_FakeArtifactService(artifact_path),
    )

    snapshot_record = adapter.preview_run_request_render_snapshot(
        run=_run(),
        draft=_draft(llm_capabilities=(LlmCapability.VISION_INPUT,)),
    )

    assert snapshot_record is not None
    assert snapshot_record.artifact_content_blocks == ()
    assert snapshots.get_by_run("run-context") is None
    assert "artifact_content_block_count" not in snapshot_record.metadata
    assert "artifact_content_candidate_count" not in snapshot_record.metadata


def test_context_workspace_adapter_downgrades_opened_image_for_non_vision_model(
    tmp_path,
) -> None:
    artifact_path = tmp_path / "image.png"
    artifact_path.write_bytes(b"png")
    workspace_service, tree_service, render_service, snapshots = (
        _context_workspace_services()
    )
    workspace_service.ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:context",
            agent_id="assistant",
        ),
    )
    _upsert_opened_artifact(
        tree_service,
        kind="artifact_image",
        artifact_id="image-1",
        title="image.png",
        mime_type="image/png",
        preferred_variant="llm",
    )
    adapter = ContextWorkspaceRunSnapshotAdapter(
        workspace_service=workspace_service,
        render_service=render_service,
        artifact_service=_FakeArtifactService(artifact_path),
    )

    snapshot_record = adapter.preview_run_request_render_snapshot(
        run=_run(),
        draft=_draft(llm_capabilities=()),
    )

    assert snapshot_record is not None
    assert snapshot_record.artifact_content_blocks == ()
    assert snapshots.get_by_run("run-context") is None
    assert "llm_capabilities" not in snapshot_record.metadata
    assert "artifact_content_omitted_count" not in snapshot_record.metadata
    assert "artifact_content_budget" not in snapshot_record.metadata


def test_context_workspace_adapter_reports_large_opened_artifact_budget(
    tmp_path,
) -> None:
    artifact_path = tmp_path / "image.png"
    artifact_path.write_bytes(b"x" * 1_500_001)
    workspace_service, tree_service, render_service, snapshots = (
        _context_workspace_services()
    )
    workspace_service.ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:context",
            agent_id="assistant",
        ),
    )
    _upsert_opened_artifact(
        tree_service,
        kind="artifact_image",
        artifact_id="image-1",
        title="image.png",
        mime_type="image/png",
        preferred_variant="llm",
    )
    adapter = ContextWorkspaceRunSnapshotAdapter(
        workspace_service=workspace_service,
        render_service=render_service,
        artifact_service=_FakeArtifactService(artifact_path),
    )

    snapshot_record = adapter.preview_run_request_render_snapshot(
        run=_run(),
        draft=_draft(llm_capabilities=(LlmCapability.VISION_INPUT,)),
    )

    assert snapshot_record is not None
    assert snapshot_record.artifact_content_blocks == ()


def test_context_workspace_adapter_decodes_opened_text_file_artifact(tmp_path) -> None:
    artifact_path = tmp_path / "result.json"
    artifact_path.write_text('{"answer": 42}', encoding="utf-8")
    workspace_service, tree_service, render_service, snapshots = (
        _context_workspace_services()
    )
    workspace_service.ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:context",
            agent_id="assistant",
        ),
    )
    _upsert_opened_artifact(
        tree_service,
        kind="artifact_file",
        artifact_id="file-1",
        title="result.json",
        mime_type="application/json",
        preferred_variant="original",
    )
    adapter = ContextWorkspaceRunSnapshotAdapter(
        workspace_service=workspace_service,
        render_service=render_service,
        artifact_service=_FakeArtifactService(
            artifact_path,
            artifact_id="file-1",
            kind=ArtifactKind.FILE,
            mime_type="application/json",
            name="result.json",
        ),
    )

    snapshot_record = adapter.preview_run_request_render_snapshot(
        run=_run(),
        draft=_draft(),
    )

    assert snapshot_record is not None
    assert snapshot_record.artifact_content_blocks == ()
    assert snapshots.get_by_run("run-context") is None
    assert "artifact_content_block_count" not in snapshot_record.metadata
    assert "artifact_content_text_block_count" not in snapshot_record.metadata
    assert "artifact_content_estimated_tokens" not in snapshot_record.metadata


def test_engine_preview_uses_context_tree_without_recording_snapshot() -> None:
    snapshot_port = _FakeRequestRenderSnapshotPort(
        tool_schemas=(ToolSchema(name="fetch_weather", description="Fetch weather."),),
        metadata={
            "runtime_contract_hash": "preview-hash",
            "request_context_source": "context_slice",
            "context_slice_id": "ctxslice-preview",
            "context_slice_projected_input_item_count": 1,
        },
        projected_input_items=(
            {
                "kind": "message",
                "payload": {
                    "role": "user",
                    "content": "slice projected preview input",
                },
                "source": "context_slice",
                "metadata": {
                    "session_item_id": "session-item-preview",
                    "node_id": "session.item.preview",
                },
            },
        ),
    )
    tool_resolver = _FakeToolResolver()
    draft_collector = _FakeRuntimeLlmRequestDraftCollector(
        tool_schemas=(
            ToolSchema(name="fetch_weather", description="Fetch weather."),
            ToolSchema(name="web_search", description="Search the web."),
        ),
    )
    engine = OrchestrationEngine(
        runtime_request_drafts=draft_collector,
        session_recorder=_FakeSessionRecorder(),
        llm_port=object(),
        tool_resolver=tool_resolver,
        tool_execution_port=object(),
        request_render_snapshot_port=snapshot_port,
    )

    preview = engine.preview_runtime_llm_request(_run())

    assert tool_resolver.resolve_schema_candidates_calls == 1
    assert tool_resolver.resolve_calls == 0
    assert tool_resolver.resolve_for_schema_names_calls == 0
    assert preview.llm_id == "test-llm"
    assert "<context_tree" not in str([message.content for message in preview.messages])
    assert [schema.name for schema in preview.tool_schemas] == ["fetch_weather"]
    assert preview.runtime_request_report is not None
    assert preview.runtime_request_report.request_render_snapshot is not None
    assert preview.runtime_request_report.request_render_snapshot.snapshot_id == "preview-run-context"
    assert preview.request_render_snapshot_id == "preview-run-context"
    assert preview.request_render_snapshot_metadata["runtime_contract_hash"] == "preview-hash"
    assert preview.input_items == (
        {
            "kind": "message",
            "payload": {
                "role": "user",
                "content": "slice projected preview input",
            },
            "source": "runtime_transcript",
            "metadata": {
                "session_item_id": "session-item-preview",
                "node_id": "session.item.preview",
            },
        },
    )
    assert preview.runtime_context["request_context_source"] == "context_slice"
    assert preview.runtime_context["context_slice_id"] == "ctxslice-preview"
    assert preview.runtime_context["context_slice_projected_input_item_count"] == 1
    assert preview.runtime_context["request_render_snapshot_id"] == "preview-run-context"
    assert preview.request_render_snapshot["snapshot_id"] == "preview-run-context"
    assert "raw_tree_body" not in preview.request_render_snapshot
    assert "provider_attachment_mirror" not in preview.request_render_snapshot
    assert "context_slice_summary" not in preview.provider_request_options[
        "request_metadata"
    ]
    assert preview.tool_surface["id"] == "tool_surface:preview-run-context"
    assert preview.tool_surface["mirrored_schema_names"] == ["fetch_weather"]
    assert snapshot_port.preview_calls == [("run-context", "session:context")]
    assert snapshot_port.calls == []
    assert draft_collector.validate_llm_access_calls == [False]

    context = engine._build_advance_context(_run())  # noqa: SLF001

    assert tool_resolver.resolve_calls == 1
    assert tool_resolver.resolve_for_schema_names_calls == 1
    assert context.request_render_snapshot_id == "snapshot-run-context"
    assert context.draft.report is not None
    assert context.draft.report.request_render_snapshot is not None
    assert context.draft.report.request_render_snapshot.snapshot_id == "snapshot-run-context"
    assert snapshot_port.calls == [("run-context", "session:context")]
    assert draft_collector.validate_llm_access_calls == [False, True]


def test_engine_preview_replays_recorded_context_tree_when_snapshot_exists() -> None:
    snapshot_port = _FakeRequestRenderSnapshotPort(
        metadata={
            "history_delivery": "context_tree",
            "runtime_contract_hash": "live-hash",
        },
    )
    snapshot_port.recorded_snapshot = snapshot_port._snapshot_record(  # noqa: SLF001
        snapshot_id="snapshot-run-context",
        metadata={
            "history_delivery": "context_tree",
            "runtime_contract_hash": "recorded-hash",
        },
    )
    engine = OrchestrationEngine(
        runtime_request_drafts=_FakeRuntimeLlmRequestDraftCollector(),
        session_recorder=_FakeSessionRecorder(),
        llm_port=object(),
        tool_resolver=_FakeToolResolver(),
        tool_execution_port=object(),
        request_render_snapshot_port=snapshot_port,
    )

    preview = engine.preview_runtime_llm_request(_run())

    assert preview.request_render_snapshot_id == "snapshot-run-context"
    assert preview.request_render_snapshot_metadata["runtime_contract_hash"] == "recorded-hash"
    assert preview.provider_request_options["request_metadata"][
        "request_render_snapshot_id"
    ] == "snapshot-run-context"
    assert (
        "context_snapshot_id"
        not in preview.provider_request_options["request_metadata"]
    )
    assert preview.request_render_snapshot["snapshot_id"] == "snapshot-run-context"
    assert preview.tool_surface["id"] == "tool_surface:snapshot-run-context"
    assert snapshot_port.preview_calls == []


def test_engine_preview_does_not_include_post_run_transcript_messages() -> None:
    snapshot_port = _FakeRequestRenderSnapshotPort(
        metadata={"draft_input_message_count": 1},
        projected_input_items=_projected_user_message("hello tree"),
    )
    snapshot_port.recorded_snapshot = snapshot_port._snapshot_record(  # noqa: SLF001
        snapshot_id="snapshot-run-context",
    )
    engine = OrchestrationEngine(
        runtime_request_drafts=_FakeRuntimeLlmRequestDraftCollector(
            extra_messages=(
                LlmMessage(
                    role=LlmMessageRole.ASSISTANT,
                    content="post-run answer",
                ),
            ),
        ),
        session_recorder=_FakeSessionRecorder(),
        llm_port=object(),
        tool_resolver=_FakeToolResolver(),
        tool_execution_port=object(),
        request_render_snapshot_port=snapshot_port,
    )

    preview = engine.preview_runtime_llm_request(_run())

    assert len(preview.messages) == 1
    assert preview.messages[0].content == [
        {"type": "text", "text": "hello tree"},
    ]
    assert "<context_tree" not in str([message.content for message in preview.messages])


def test_engine_keeps_context_workspace_body_out_of_provider_messages() -> None:
    snapshot_port = _FakeRequestRenderSnapshotPort(
    )
    engine = OrchestrationEngine(
        runtime_request_drafts=_FakeRuntimeLlmRequestDraftCollector(),
        session_recorder=_FakeSessionRecorder(),
        llm_port=object(),
        tool_resolver=_FakeToolResolver(),
        tool_execution_port=object(),
        request_render_snapshot_port=snapshot_port,
    )

    context = engine._build_advance_context(_run())  # noqa: SLF001

    first_message = context.draft.messages[0]
    assert first_message.role is LlmMessageRole.USER
    assert "session.current" not in str([message.content for message in context.draft.messages])
    assert context.request_envelope.request_render_snapshot.snapshot_id == "snapshot-run-context"
    assert "raw_tree_body" not in context.request_envelope.request_render_snapshot.to_payload()


def test_engine_carries_context_contract_metadata_for_llm_invocation() -> None:
    snapshot_port = _FakeRequestRenderSnapshotPort(
        tool_schemas=(ToolSchema(name="fetch_weather", description="Fetch weather."),),
        metadata={
            "history_delivery": "context_tree",
            "runtime_contract_version": "2026-06-09",
            "runtime_contract_hash": "abc123",
            "runtime_contract": {
                "node_id": "runtime.contract",
                "contract_version": "2026-06-09",
                "content_hash": "abc123",
            },
            "tree_schema_version": CONTEXT_TREE_SCHEMA_VERSION,
            "mirrored_tool_schema_count": 1,
            "mirrored_tool_schema_estimated_tokens": 18,
            "tool_schema_mirror_budget_status": "ok",
            "tool_schema_mirror_skipped_count": 0,
            "tool_schema_mirror_default_schema_source": "source_runtime_request.default",
            "tool_schema_mirror_available_count": 4,
            "tool_schema_mirror_enabled_candidate_count": 2,
            "tool_schema_mirror_default_requested_count": 1,
            "tool_schema_mirror_default_candidate_count": 1,
            "tool_schema_mirror_default_mirrored_count": 1,
            "tool_schema_mirror_duplicate_count": 0,
            "tool_schema_mirror_groups": [
                {
                    "node_id": "tools.bundle.bundled.local_package.browser.group.network",
                    "kind": "tool_bundle_group",
                    "source_id": "bundled.local_package.browser",
                    "group_key": "network",
                    "title": "Network Capture & Replay",
                    "state": "collapsed",
                    "visibility": "visible_collapsed",
                    "function_count": 10,
                    "default_group": True,
                    "default_schema_count": 6,
                },
            ],
            "tool_schema_mirror_group_count": 12,
            "tool_schema_mirror_visible_group_count": 12,
            "tool_schema_mirror_collapsed_group_count": 12,
            "tool_schema_mirror_default_group_count": 5,
            "tool_schema_mirror_default_group_refs": [
                {
                    "source_id": "bundled.local_package.browser",
                    "group_key": "network",
                    "reason": "browser_starter_network",
                },
            ],
            "tool_schema_mirror_default_group_ref_count": 1,
            "tool_schema_mirror_default_group_matches": [
                {
                    "node_id": "tools.bundle.bundled.local_package.browser.group.network",
                    "source_id": "bundled.local_package.browser",
                    "group_key": "network",
                    "priority": "200",
                    "reason": "browser_starter_network",
                },
            ],
            "tool_schema_mirror_default_group_match_count": 1,
            "tool_schema_mirror_default_schema_reasons": {
                "browser.network.inspect": "browser_starter_network",
            },
            "tool_schema_mirror_default_mirrored": [
                {
                    "node_id": "tools.tool.browser.network.inspect",
                    "name": "browser.network.inspect",
                    "priority": 200,
                    "bootstrap_reason": "browser_starter_network",
                },
            ],
            "tool_schema_mirror_skipped": [],
            "tool_schema_mirror_skipped_by_reason": {},
            "tool_schema_mirror_max_count": 32,
            "tool_schema_mirror_max_estimated_tokens": 24000,
            "visible_input_summary": {
                "debug_body_included": False,
                "full_tree_rendered": False,
                "owner_children_refreshed": False,
                "input_item_ref_count": 3,
                "protocol_required_ref_count": 2,
                "collapsed_ref_count": 1,
                "tool_schema_count": 1,
                "tool_schema_names": ["fetch_weather"],
                "input_ref_owner_counts": {"session": 3},
                "input_ref_kind_counts": {"session_item": 3},
            },
            "draft_input_estimated_tokens": 30,
            "artifact_content_estimated_tokens": 6,
            "artifact_content_block_count": 1,
            "artifact_content_candidate_count": 1,
            "artifact_content_image_count": 0,
            "artifact_content_file_count": 0,
            "artifact_content_omitted_count": 0,
            "estimated_provider_input_tokens": 154,
            "duplicate_tool_delivery_risk": False,
            "session_budget_status": "ok",
            "mirrored_node_count": 2,
            "current_inbound_session_item_id": "item-user-1",
        },
    )
    engine = OrchestrationEngine(
        runtime_request_drafts=_FakeRuntimeLlmRequestDraftCollector(
            tool_schemas=(ToolSchema(name="fetch_weather", description="Fetch weather."),),
            extra_messages=(
                LlmMessage(
                    role=LlmMessageRole.ASSISTANT,
                    content={
                        "type": "function_call",
                        "call_id": "call-weather-1",
                        "name": "fetch_weather",
                        "arguments": {"location": "Kunming"},
                    },
                    tool_call_id="call-weather-1",
                    metadata={
                        "session_item_id": "item-assistant-tool-1",
                        "session_id": "session-instance-1",
                        "sequence_no": 2,
                        "kind": "message",
                        "source_kind": "llm_invocation",
                        "source_id": "llm-1",
                        "tool_call_id": "call-weather-1",
                        "tool_name": "fetch_weather",
                    },
                ),
                LlmMessage(
                    role=LlmMessageRole.TOOL,
                    content="weather result",
                    name="fetch_weather",
                    tool_call_id="call-weather-1",
                    metadata={
                        "session_item_id": "item-tool-result-1",
                        "session_id": "session-instance-1",
                        "sequence_no": 3,
                        "kind": "tool_result",
                        "source_kind": "tool_run",
                        "source_id": "tool-run-1",
                        "tool_call_id": "call-weather-1",
                        "tool_name": "fetch_weather",
                        "tool_status": "succeeded",
                    },
                ),
            ),
        ),
        session_recorder=_FakeSessionRecorder(),
        llm_port=object(),
        tool_resolver=_FakeToolResolver(tools=(_resolved_tool("fetch_weather"),)),
        tool_execution_port=object(),
        request_render_snapshot_port=snapshot_port,
    )

    context = engine._build_advance_context(_run())  # noqa: SLF001

    assert context.request_render_snapshot_metadata["runtime_contract_hash"] == "abc123"
    from crxzipple.modules.orchestration.application.engine_runtime_helpers import (
        llm_request_metadata,
    )

    request_metadata = llm_request_metadata(context)
    assert request_metadata["runtime_request_mode"] == "normal_turn"
    assert request_metadata["tree_schema_version"] == CONTEXT_TREE_SCHEMA_VERSION
    assert request_metadata["request_render_snapshot_id"] == "snapshot-run-context"
    assert "context_snapshot_id" not in request_metadata
    assert request_metadata["request_render_snapshot_kind"] == "request_render"
    assert request_metadata["runtime_contract_version"] == "2026-06-09"
    assert request_metadata["runtime_contract_hash"] == "abc123"
    assert request_metadata["mirrored_tool_schema_count"] == 1
    assert request_metadata["mirrored_tool_schema_estimated_tokens"] == 18
    assert request_metadata["tool_schema_mirror_budget_status"] == "ok"
    assert request_metadata["tool_schema_mirror_skipped_count"] == 0
    assert request_metadata["tool_schema_mirror_default_schema_source"] == (
        "source_runtime_request.default"
    )
    assert request_metadata["tool_schema_mirror_available_count"] == 4
    assert request_metadata["tool_schema_mirror_enabled_candidate_count"] == 2
    assert request_metadata["tool_schema_mirror_default_requested_count"] == 1
    assert request_metadata["tool_schema_mirror_default_candidate_count"] == 1
    assert request_metadata["tool_schema_mirror_default_mirrored_count"] == 1
    assert request_metadata["tool_schema_mirror_duplicate_count"] == 0
    assert request_metadata["tool_schema_mirror_group_count"] == 12
    assert request_metadata["tool_schema_mirror_visible_group_count"] == 12
    assert request_metadata["tool_schema_mirror_collapsed_group_count"] == 12
    assert request_metadata["tool_schema_mirror_default_group_count"] == 5
    assert request_metadata["tool_schema_mirror_default_group_ref_count"] == 1
    assert request_metadata["tool_schema_mirror_default_group_match_count"] == 1
    assert "tool_schema_mirror_groups" not in request_metadata
    assert "tool_schema_mirror_default_group_refs" not in request_metadata
    assert "tool_schema_mirror_default_group_matches" not in request_metadata
    assert "tool_schema_mirror_default_schema_reasons" not in request_metadata
    assert "tool_schema_mirror_default_mirrored" not in request_metadata
    assert request_metadata["tool_surface_id"] == "tool_surface:snapshot-run-context"
    assert request_metadata["tool_surface_mirrored_schema_names"] == ["fetch_weather"]
    assert request_metadata["tool_surface_mirrored_schema_count"] == 1
    assert request_metadata["tool_surface_always_visible_count"] == 1
    assert request_metadata["tool_surface_context_selected_count"] == 0
    assert request_metadata["tool_surface_function_refs"] == [
            {
                "tool_id": "fetch_weather",
                "name": "fetch_weather",
                "enabled": True,
                "always_visible": True,
                "source": "context_slice",
                "function_name": "fetch_weather",
            },
        ]
    assert "tool_surface_source_refs" not in request_metadata
    assert "tool_surface_group_refs" not in request_metadata
    assert "tool_schema_mirror_skipped" not in request_metadata
    assert "tool_schema_mirror_skipped_by_reason" not in request_metadata
    assert request_metadata["tool_schema_mirror_max_count"] == 32
    assert request_metadata["tool_schema_mirror_max_estimated_tokens"] == 24000
    assert request_metadata["visible_input_summary"] == {
        "debug_body_included": False,
        "full_tree_rendered": False,
        "owner_children_refreshed": False,
        "input_item_ref_count": 3,
        "protocol_required_ref_count": 2,
        "collapsed_ref_count": 1,
        "tool_schema_count": 1,
        "tool_schema_names": ["fetch_weather"],
        "input_ref_owner_counts": {"session": 3},
        "input_ref_kind_counts": {"session_item": 3},
    }
    assert "debug_body_estimated_tokens" not in request_metadata
    assert request_metadata["draft_input_estimated_tokens"] == 30
    assert request_metadata["artifact_content_estimated_tokens"] == 6
    assert request_metadata["artifact_content_block_count"] == 1
    assert request_metadata["artifact_content_candidate_count"] == 1
    assert request_metadata["artifact_content_image_count"] == 0
    assert request_metadata["artifact_content_file_count"] == 0
    assert request_metadata["artifact_content_omitted_count"] == 0
    assert request_metadata["estimated_provider_input_tokens"] == 154
    assert request_metadata["duplicate_tool_delivery_risk"] is False
    assert request_metadata["session_budget_status"] == "ok"
    assert request_metadata["runtime_contract"]["node_id"] == "runtime.contract"
    assert "direct_transcript_session_item_count" not in request_metadata
    assert "direct_transcript_sequence_range" not in request_metadata
    assert "current_inbound_ref" not in request_metadata
    assert "direct_tool_protocol_call_ids" not in request_metadata
    assert "direct_tool_protocol_refs" not in request_metadata


def test_engine_uses_context_mirror_as_real_tool_schema_surface() -> None:
    snapshot_port = _FakeRequestRenderSnapshotPort(
        tool_schemas=(ToolSchema(name="fetch_weather", description="Fetch weather."),),
    )
    engine = OrchestrationEngine(
        runtime_request_drafts=_FakeRuntimeLlmRequestDraftCollector(
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
        request_render_snapshot_port=snapshot_port,
    )

    context = engine._build_advance_context(_run())  # noqa: SLF001

    assert [schema.name for schema in context.request_envelope.tool_schemas] == [
        "fetch_weather",
    ]
    assert [item.tool.id for item in context.resolved_tools.tools] == ["fetch_weather"]


def test_engine_drops_provider_tool_surface_when_context_mirror_not_ready() -> None:
    snapshot_port = _FakeRequestRenderSnapshotPort(tool_schemas=None)
    engine = OrchestrationEngine(
        runtime_request_drafts=_FakeRuntimeLlmRequestDraftCollector(
            tool_schemas=(ToolSchema(name="web_search", description="Search the web."),),
        ),
        session_recorder=_FakeSessionRecorder(),
        llm_port=object(),
        tool_resolver=_FakeToolResolver(tools=(_resolved_tool("web_search"),)),
        tool_execution_port=object(),
        request_render_snapshot_port=snapshot_port,
    )

    context = engine._build_advance_context(_run())  # noqa: SLF001

    assert [schema.name for schema in context.request_envelope.tool_schemas] == []
    assert context.resolved_tools.tools == ()


def test_engine_allows_context_mirror_to_disable_all_tool_schemas() -> None:
    snapshot_port = _FakeRequestRenderSnapshotPort(tool_schemas=())
    engine = OrchestrationEngine(
        runtime_request_drafts=_FakeRuntimeLlmRequestDraftCollector(
            tool_schemas=(ToolSchema(name="web_search", description="Search the web."),),
        ),
        session_recorder=_FakeSessionRecorder(),
        llm_port=object(),
        tool_resolver=_FakeToolResolver(tools=(_resolved_tool("web_search"),)),
        tool_execution_port=object(),
        request_render_snapshot_port=snapshot_port,
    )

    context = engine._build_advance_context(_run())  # noqa: SLF001

    assert [schema.name for schema in context.request_envelope.tool_schemas] == []
    assert context.resolved_tools.tools == ()


def test_engine_keeps_context_artifact_blocks_out_of_provider_messages() -> None:
    snapshot_port = _FakeRequestRenderSnapshotPort(
        artifact_content_blocks=(
            {
                "type": "image",
                "mime_type": "image/png",
                "data": "cG5n",
            },
        ),
    )
    engine = OrchestrationEngine(
        runtime_request_drafts=_FakeRuntimeLlmRequestDraftCollector(),
        session_recorder=_FakeSessionRecorder(),
        llm_port=object(),
        tool_resolver=_FakeToolResolver(),
        tool_execution_port=object(),
        request_render_snapshot_port=snapshot_port,
    )

    context = engine._build_advance_context(_run())  # noqa: SLF001

    assert len(context.draft.messages) == 1
    assert all(
        message.metadata.get("runtime_request_block_kind") != "context_artifacts"
        for message in context.draft.messages
    )
    assert (
        context.request_envelope.request_render_snapshot.diagnostics.get(
            "artifact_content_block_count",
        )
        is None
    )


def test_engine_fails_when_request_render_snapshot_record_is_missing() -> None:
    engine = OrchestrationEngine(
        runtime_request_drafts=_FakeRuntimeLlmRequestDraftCollector(
            tool_schemas=(ToolSchema(name="web_search", description="Search the web."),),
        ),
        session_recorder=_FakeSessionRecorder(),
        llm_port=object(),
        tool_resolver=_FakeToolResolver(tools=(_resolved_tool("web_search"),)),
        tool_execution_port=object(),
        request_render_snapshot_port=_MissingRequestRenderSnapshotPort(),
    )

    with pytest.raises(
        OrchestrationValidationError,
        match="Context Workspace request render snapshot did not return a snapshot",
    ):
        engine._build_advance_context(_run())  # noqa: SLF001

    with pytest.raises(
        OrchestrationValidationError,
        match="Context Workspace request render snapshot preview did not return a snapshot",
    ):
        engine.preview_runtime_llm_request(_run())


def _context_workspace_services():
    workspaces = InMemoryContextWorkspaceRepository()
    nodes = InMemoryContextNodeRepository()
    operations = InMemoryContextOperationRepository()
    snapshots = InMemoryContextSnapshotRepository()
    workspace_service = ContextWorkspaceService(
        workspace_repository=workspaces,
        node_repository=nodes,
    )
    tree_service = ContextTreeService(
        workspace_repository=workspaces,
        node_repository=nodes,
        operation_repository=operations,
    )
    render_service = ContextObservationSnapshotService(
        workspace_repository=workspaces,
        node_repository=nodes,
        snapshot_repository=snapshots,
    )
    return workspace_service, tree_service, render_service, snapshots


def _upsert_opened_artifact(
    tree_service: ContextTreeService,
    *,
    kind: str,
    artifact_id: str,
    title: str,
    mime_type: str,
    preferred_variant: str,
) -> None:
    tree_service.upsert_nodes(
        ContextNodeUpsertInput(
            session_key="session:context",
            parent_node_id="artifacts.session",
            action=ContextAction.PIN,
            nodes=(
                ContextNodeSeed(
                    node_id=f"artifacts.artifact.{artifact_id}",
                    parent_id="artifacts.session",
                    owner="artifacts",
                    kind=kind,
                    title=title,
                    summary=f"{title} artifact.",
                    state=ContextNodeState(loaded=True, pinned=True),
                    actions=(ContextAction.PIN, ContextAction.UNPIN),
                    owner_ref={
                        "artifact_id": artifact_id,
                        "preferred_variant": preferred_variant,
                    },
                    estimate=ContextEstimate(
                        image_count=1 if kind == "artifact_image" else 0,
                        file_count=1 if kind == "artifact_file" else 0,
                    ),
                    metadata={"mime_type": mime_type, "name": title},
                ),
            ),
        ),
    )


def _browser_group_seed(
    *,
    group_key: str,
    tool_ids: tuple[str, ...],
    display_order: int,
) -> ContextNodeSeed:
    return ContextNodeSeed(
        node_id=f"tools.bundle.bundled.local_package.browser.group.{group_key}",
        parent_id="tools.bundle.bundled.local_package.browser",
        owner="tool",
        kind="tool_bundle_group",
        title=group_key.replace("_", " ").title(),
        summary=f"Browser {group_key} tools.",
        state=ContextNodeState(collapsed=True, loaded=True),
        actions=(ContextAction.EXPAND, ContextAction.COLLAPSE),
        owner_ref={
            "source_id": "bundled.local_package.browser",
            "group_key": group_key,
        },
        metadata={
            "source_id": "bundled.local_package.browser",
            "group_key": group_key,
            "default_tool_schema_ids": list(tool_ids),
            "default_tool_schema_source": f"bundled.local_package.browser.runtime_request_group.{group_key}",
            "default_tool_schema_max_count": len(tool_ids),
        },
        display_order=display_order,
    )


def _browser_tool_seed(
    *,
    tool_id: str,
    parent_id: str,
    display_order: int,
) -> ContextNodeSeed:
    return ContextNodeSeed(
        node_id=f"tools.tool.{tool_id}",
        parent_id=parent_id,
        owner="tool",
        kind="tool_function",
        title=tool_id,
        summary=f"{tool_id} tool.",
        state=ContextNodeState(collapsed=False, loaded=True),
        owner_ref={"tool_id": tool_id, "source_id": "bundled.local_package.browser"},
        display_order=display_order,
    )


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


def _draft(
    *,
    tool_schemas: tuple[ToolSchema, ...] = (),
    system_messages: tuple[tuple[str, str], ...] = (),
    llm_capabilities: tuple[LlmCapability, ...] = (),
    extra_messages: tuple[LlmMessage, ...] = (),
    flow_hint: dict[str, object] | None = None,
    transcript_budget: dict[str, object] | None = None,
    runtime_context_overrides: dict[str, object] | None = None,
) -> RuntimeLlmRequestDraft:
    runtime_context = {
        "agent_id": "assistant",
        "llm_id": "test-llm",
        "agent_home_dir": None,
        "workspace_dir": None,
        "available_tool_ids": (),
    }
    runtime_context.update(runtime_context_overrides or {})
    return RuntimeLlmRequestDraft(
        llm_id="test-llm",
        session_key="session:context",
        active_session_id="session-instance-1",
        messages=(
            LlmMessage(
                role=LlmMessageRole.USER,
                content="hello tree",
                metadata={
                    "session_item_id": "item-user-1",
                    "session_id": "session-instance-1",
                    "sequence_no": 1,
                    "source_kind": "orchestration_run",
                    "source_id": "run-context",
                },
            ),
            *extra_messages,
        ),
        llm_capabilities=llm_capabilities,
        tool_schemas=tool_schemas,
        flow_hint=dict(flow_hint or {}),
        agent_instruction=next(
            (
                content
                for kind, content in system_messages
                if kind == "agent_instruction"
            ),
            None,
        ),
        runtime_context=runtime_context,
        report=RuntimeRequestReport(
            mode=RuntimeRequestMode.NORMAL_TURN,
            context_budget_source="fixed",
            context_budget_chars=0,
            context_budget_estimated_tokens=0,
            llm_context_window_tokens=None,
            context_chars=0,
            context_estimated_tokens=0,
            transcript_message_count=1,
            transcript_chars=10,
            transcript_estimated_tokens=3,
            transcript_budget=dict(transcript_budget or {}),
        ),
    )


class _FakeRuntimeLlmRequestDraftCollector:
    detailed_phase_metrics_enabled = False
    metrics = None

    def __init__(
        self,
        *,
        tool_schemas: tuple[ToolSchema, ...] = (),
        system_messages: tuple[tuple[str, str], ...] = (),
        extra_messages: tuple[LlmMessage, ...] = (),
        execution_query: "_FakeExecutionQuery | None" = None,
    ) -> None:
        self._tool_schemas = tool_schemas
        self._system_messages = system_messages
        self._extra_messages = extra_messages
        self.execution_query = execution_query

        self.validate_llm_access_calls: list[bool] = []

    def build(  # noqa: ANN201
        self,
        run,  # noqa: ANN001
        *,
        resolved_tools,  # noqa: ANN001
        validate_llm_access: bool = True,
    ):
        del run, resolved_tools
        self.validate_llm_access_calls.append(validate_llm_access)
        return _draft(
            tool_schemas=self._tool_schemas,
            system_messages=self._system_messages,
            extra_messages=self._extra_messages,
        )


class _FakeExecutionQuery:
    def __init__(self, *, llm_step_count: int, include_progress: bool) -> None:
        self._llm_step_count = llm_step_count
        self._include_progress = include_progress

    def list_execution_chains(self, turn_id: str) -> list[object]:
        assert turn_id == "run-context"
        return [_Simple(id="chain-1")]

    def list_execution_steps(self, chain_id: str) -> list[object]:
        assert chain_id == "chain-1"
        return [
            _Simple(id=f"step-{index}", step_index=index)
            for index in range(1, self._llm_step_count + 1)
        ]

    def list_execution_step_items(self, step_id: str) -> list[object]:
        index = int(step_id.rsplit("-", 1)[-1])
        payload: dict[str, object] = {
            "tool_call_names": ["command.exec"],
        }
        if self._include_progress:
            payload["assistant_progress_item_ids"] = [f"progress-{index}"]
        return [
            _Simple(
                id=f"llm-item-{index}",
                step_id=step_id,
                kind=ExecutionStepItemKind.LLM_INVOCATION,
                summary_payload=payload,
            ),
        ]


class _Simple:
    def __init__(self, **kwargs: object) -> None:
        self.__dict__.update(kwargs)


class _FakeSessionRecorder:
    def ensure_inbound_message(self, run, *, session_key):  # noqa: ANN001, ANN201
        assert run.id == "run-context"
        assert session_key == "session:context"
        return InboundSessionRecord(
            user_session_item_id="item-user-1",
        )


class _FakeToolResolver:
    def __init__(self, *, tools: tuple[ResolvedTool, ...] = ()) -> None:
        self._tools = tools
        self.resolve_calls = 0
        self.resolve_for_schema_names_calls = 0
        self.resolve_schema_candidates_calls = 0

    def resolve(self, run):  # noqa: ANN001, ANN201
        assert run.id == "run-context"
        self.resolve_calls += 1
        return ResolvedToolSet(tools=self._tools)

    def resolve_schema_candidates(self, run):  # noqa: ANN001, ANN201
        assert run.id == "run-context"
        self.resolve_schema_candidates_calls += 1
        return ResolvedToolSet(tools=self._tools)

    def resolve_for_schema_names(self, run, schema_names):  # noqa: ANN001, ANN201
        assert run.id == "run-context"
        self.resolve_for_schema_names_calls += 1
        visible = {name for name in schema_names if name}
        return ResolvedToolSet(
            tools=tuple(
                tool
                for tool in self._tools
                if tool.schema.name in visible or tool.tool.id in visible
            ),
        )


class _FakeRequestRenderSnapshotPort:
    def __init__(
        self,
        *,
        tool_schemas: tuple[ToolSchema, ...] | None = None,
        tool_schema_mirror_available: bool | None = None,
        artifact_content_blocks: tuple[dict[str, object], ...] = (),
        metadata: dict[str, object] | None = None,
        projected_input_items: tuple[dict[str, object], ...] | None = None,
    ) -> None:
        self._tool_schemas = tool_schemas
        self._artifact_content_blocks = artifact_content_blocks
        self._metadata = dict(metadata or {})
        self._projected_input_items = (
            _projected_user_message()
            if projected_input_items is None
            else projected_input_items
        )
        self._tool_schema_mirror_available = (
            tool_schemas is not None
            if tool_schema_mirror_available is None
            else tool_schema_mirror_available
        )
        self.calls: list[tuple[str, str]] = []
        self.preview_calls: list[tuple[str, str]] = []
        self.recorded_snapshot: RequestRenderSnapshotRecord | None = None

    def get_recorded_run_request_render_snapshot(
        self,
        *,
        run: OrchestrationRun,
        draft: RuntimeLlmRequestDraft,
    ) -> RequestRenderSnapshotRecord | None:
        del run, draft
        return self.recorded_snapshot

    def preview_run_request_render_snapshot(
        self,
        *,
        run: OrchestrationRun,
        draft: RuntimeLlmRequestDraft,
    ) -> RequestRenderSnapshotRecord:
        self.preview_calls.append((run.id, draft.session_key))
        return self._snapshot_record(snapshot_id=f"preview-{run.id}")

    def record_run_request_render_snapshot(
        self,
        *,
        run: OrchestrationRun,
        draft: RuntimeLlmRequestDraft,
    ) -> RequestRenderSnapshotRecord:
        self.calls.append((run.id, draft.session_key))
        return self._snapshot_record(snapshot_id=f"snapshot-{run.id}")

    def _snapshot_record(
        self,
        *,
        snapshot_id: str,
        metadata: dict[str, object] | None = None,
    ) -> RequestRenderSnapshotRecord:
        return RequestRenderSnapshotRecord(
            snapshot_id=snapshot_id,
            tool_schemas=self._tool_schemas,
            tool_schema_refs=tuple(
                _tool_schema_ref(schema) for schema in self._tool_schemas or ()
            ),
            tool_schema_mirror_available=self._tool_schema_mirror_available,
            artifact_content_blocks=self._artifact_content_blocks,
            projected_input_items=self._projected_input_items,
            metadata=dict(self._metadata if metadata is None else metadata),
        )


class _MissingRequestRenderSnapshotPort:
    def get_recorded_run_request_render_snapshot(
        self,
        *,
        run: OrchestrationRun,
        draft: RuntimeLlmRequestDraft,
    ) -> None:
        del run, draft
        return None

    def preview_run_request_render_snapshot(
        self,
        *,
        run: OrchestrationRun,
        draft: RuntimeLlmRequestDraft,
    ) -> None:
        del run, draft
        return None

    def record_run_request_render_snapshot(
        self,
        *,
        run: OrchestrationRun,
        draft: RuntimeLlmRequestDraft,
    ) -> None:
        del run, draft
        return None


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


def _projected_user_message(text: str = "hello") -> tuple[dict[str, object], ...]:
    return (
        {
            "kind": "message",
            "payload": {
                "role": "user",
                "content": [{"type": "text", "text": text}],
            },
            "source": "context_slice",
            "metadata": {
                "owner": "session",
                "kind": "session_item",
                "session_item_id": "item-user-1",
                "node_id": "session.step.item.user-1",
            },
        },
    )


def _tool_schema_ref(schema: ToolSchema) -> dict[str, object]:
    return {
        "name": schema.name,
        "source": "context_slice",
        "schema": schema.to_payload(),
    }


class _FakeArtifactService:
    def __init__(
        self,
        path,
        *,
        artifact_id: str = "image-1",
        kind: ArtifactKind = ArtifactKind.IMAGE,
        mime_type: str = "image/png",
        name: str = "image.png",
    ) -> None:
        self.path = path
        self.variant = (
            ArtifactVariant.LLM if kind is ArtifactKind.IMAGE else ArtifactVariant.ORIGINAL
        )
        self.artifact = Artifact(
            id=artifact_id,
            kind=kind,
            mime_type=mime_type,
            storage_key=f"{artifact_id}/original",
            llm_storage_key=f"{artifact_id}/llm" if kind is ArtifactKind.IMAGE else None,
            name=name,
        )

    def resolve_variant(
        self,
        artifact_id: str,
        *,
        variant: ArtifactVariant,
    ) -> ArtifactBinary:
        assert artifact_id == self.artifact.id
        assert variant is self.variant
        return ArtifactBinary(
            artifact=self.artifact,
            path=self.path,
            variant=variant,
        )
