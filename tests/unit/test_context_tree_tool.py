from __future__ import annotations

import asyncio

from crxzipple.app.integration.context_workspace_tool import ToolContextNodeProvider
from crxzipple.app.integration.context_workspace_skills import SkillContextNodeProvider
from crxzipple.modules.artifacts.application.services import ArtifactBinary
from crxzipple.modules.artifacts.domain.entities import (
    Artifact,
    ArtifactKind,
    ArtifactVariant,
)
from crxzipple.modules.context_workspace.application import (
    ContextOwnerRegistry,
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
from crxzipple.modules.memory.application import (
    MemoryRecallItem,
    MemoryRecallRequest,
    MemoryRecallResult,
    MemoryResolvedScope,
)
from crxzipple.modules.memory.application.models import MemoryUseContext
from crxzipple.modules.skills.application import SkillPackage, SkillReadResult
from crxzipple.modules.skills.domain import SkillManifest
from crxzipple.modules.context_workspace.infrastructure import (
    InMemoryContextNodeRepository,
    InMemoryContextOperationRepository,
    InMemoryContextRenderSnapshotRepository,
    InMemoryContextWorkspaceRepository,
)
from crxzipple.modules.tool.domain import (
    Tool,
    ToolError,
    ToolExecutionContext,
    ToolParameter,
)
from tools.context_tree.local import (
    ContextTreeToolDeps,
    context_tree_disable_tool_schema,
    context_tree_enable_tool_schema,
    context_tree_estimate,
    context_tree_expand,
    context_tree_list,
    context_tree_open_artifact,
    context_tree_read_skill,
    context_tree_recall_memory,
)


def test_context_tree_tools_expand_and_control_tool_schema_mirror() -> None:
    deps = _deps()
    deps.workspace_service.ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:ctx",
            agent_id="assistant",
            metadata={"available_tool_names": ["fetch_weather"]},
        ),
    )
    execution_context = ToolExecutionContext(
        attrs={
            "session_key": "session:ctx",
            "agent_id": "assistant",
            "run_id": "run-ctx",
        },
    )

    expand_result = asyncio.run(
        context_tree_expand(deps.tool_deps)(
            {"node_id": "tools.available"},
            execution_context,
        ),
    )
    assert expand_result.metadata["tool"] == "context_tree.expand"
    assert expand_result.details["revision"] == 2
    assert "tools.tool.fetch_weather" in expand_result.details["included_node_ids"]

    estimate_result = asyncio.run(context_tree_estimate(deps.tool_deps)({}, execution_context))
    assert estimate_result.details["tool_schema_mirror_available"] is True
    assert estimate_result.details["mirrored_node_ids"] == ["tools.tool.fetch_weather"]

    disable_result = asyncio.run(
        context_tree_disable_tool_schema(deps.tool_deps)(
            {"node_id": "tools.tool.fetch_weather"},
            execution_context,
        ),
    )
    assert disable_result.details["node"]["state"]["schema_enabled"] is False
    assert disable_result.details["mirrored_node_ids"] == []

    enable_result = asyncio.run(
        context_tree_enable_tool_schema(deps.tool_deps)(
            {"node_id": "tools.tool.fetch_weather"},
            execution_context,
        ),
    )
    assert enable_result.details["node"]["state"]["schema_enabled"] is True
    assert enable_result.details["mirrored_node_ids"] == ["tools.tool.fetch_weather"]

    list_result = asyncio.run(context_tree_list(deps.tool_deps)({}, execution_context))
    node_ids = [node["id"] for node in list_result.details["nodes"]]
    assert "tools.available" in node_ids
    assert "tools.tool.fetch_weather" in node_ids


def test_context_tree_tool_requires_session_key() -> None:
    deps = _deps()
    handler = context_tree_list(deps.tool_deps)

    try:
        asyncio.run(handler({}, None))
    except ValueError as exc:
        assert "session_key" in str(exc)
    else:  # pragma: no cover - defensive assertion branch.
        raise AssertionError("context_tree.list should require session_key")


def test_context_tree_read_skill_action_loads_skill_content_node() -> None:
    deps = _deps(include_skill_provider=True)
    deps.workspace_service.ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:skills",
            agent_id="assistant",
            metadata={"available_skill_names": ["review"], "workspace_dir": "/tmp/ws"},
        ),
    )
    execution_context = ToolExecutionContext(
        attrs={"session_key": "session:skills", "agent_id": "assistant"},
    )

    asyncio.run(
        context_tree_expand(deps.tool_deps)(
            {"node_id": "skills.available"},
            execution_context,
        ),
    )
    read_result = asyncio.run(
        context_tree_read_skill(deps.tool_deps)(
            {"node_id": "skills.skill.review"},
            execution_context,
        ),
    )

    assert read_result.metadata["tool"] == "context_tree.read_skill"
    assert "skills.skill.review.instructions" in read_result.details["included_node_ids"]
    tree = deps.tree_service.list_tree("session:skills")
    assert any(node.id == "skills.skill.review.instructions" for node in tree.nodes)


def test_context_tree_recall_memory_attaches_recall_result_nodes() -> None:
    memory_runtime = _FakeMemoryRuntime()
    deps = _deps(memory_runtime_service=memory_runtime)
    deps.workspace_service.ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:memory",
            agent_id="assistant",
            metadata={},
        ),
    )
    execution_context = ToolExecutionContext(
        attrs={
            "session_key": "session:memory",
            "agent_id": "assistant",
            "run_id": "run-memory",
        },
    )

    recall_result = asyncio.run(
        context_tree_recall_memory(deps.tool_deps)(
            {"query": "birthday", "limit": 2},
            execution_context,
        ),
    )

    assert recall_result.metadata["tool"] == "context_tree.recall_memory"
    assert recall_result.metadata["result_count"] == 1
    assert memory_runtime.requests[0].query == "birthday"
    tree = deps.tree_service.list_tree("session:memory")
    recall_nodes = [node for node in tree.nodes if node.kind == "memory_recall_item"]
    assert len(recall_nodes) == 1
    assert "birthday is May 1" in recall_nodes[0].summary


def test_context_tree_open_artifact_resolves_artifact_variant(tmp_path) -> None:
    image_path = tmp_path / "image.png"
    image_path.write_bytes(b"png")
    artifact_service = _FakeArtifactService(image_path)
    deps = _deps(artifact_service=artifact_service)
    deps.workspace_service.ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:artifact",
            agent_id="assistant",
            metadata={},
        ),
    )
    deps.tree_service.upsert_nodes(
        ContextNodeUpsertInput(
            session_key="session:artifact",
            parent_node_id="artifacts.session",
            action=ContextAction.EXPAND,
            nodes=(
                ContextNodeSeed(
                    node_id="artifacts.artifact.image-1",
                    parent_id="artifacts.session",
                    owner="artifacts",
                    kind="artifact_image",
                    title="image.png",
                    summary="Image artifact.",
                    state=ContextNodeState(loaded=True),
                    actions=(ContextAction.OPEN_ARTIFACT,),
                    owner_ref={
                        "artifact_id": "image-1",
                        "preferred_variant": "llm",
                    },
                    estimate=ContextEstimate(image_count=1),
                ),
            ),
        ),
    )
    execution_context = ToolExecutionContext(
        attrs={
            "session_key": "session:artifact",
            "agent_id": "assistant",
            "run_id": "run-artifact",
        },
    )

    open_result = asyncio.run(
        context_tree_open_artifact(deps.tool_deps)(
            {"node_id": "artifacts.artifact.image-1"},
            execution_context,
        ),
    )

    assert open_result.metadata["tool"] == "context_tree.open_artifact"
    assert open_result.metadata["variant"] == "llm"
    assert artifact_service.requests == [("image-1", ArtifactVariant.LLM)]
    assert open_result.details["artifact"]["path"] == str(image_path)
    assert open_result.details["node"]["state"]["loaded"] is True
    assert open_result.details["node"]["state"]["opened"] is True


class _Deps:
    def __init__(
        self,
        *,
        include_skill_provider: bool = False,
        memory_runtime_service=None,
        artifact_service=None,
    ) -> None:
        self.workspaces = InMemoryContextWorkspaceRepository()
        self.nodes = InMemoryContextNodeRepository()
        self.operations = InMemoryContextOperationRepository()
        self.snapshots = InMemoryContextRenderSnapshotRepository()
        self.registry = ContextOwnerRegistry()
        self.registry.register(ToolContextNodeProvider(_ToolService()))
        if include_skill_provider:
            self.registry.register(SkillContextNodeProvider(_SkillService()))
        self.workspace_service = ContextWorkspaceService(
            workspace_repository=self.workspaces,
            node_repository=self.nodes,
            owner_registry=self.registry,
        )
        self.tree_service = ContextTreeService(
            workspace_repository=self.workspaces,
            node_repository=self.nodes,
            operation_repository=self.operations,
            owner_registry=self.registry,
        )
        self.render_service = ContextRenderService(
            workspace_repository=self.workspaces,
            node_repository=self.nodes,
            snapshot_repository=self.snapshots,
        )
        self.tool_deps = ContextTreeToolDeps(
            context_tree_service=self.tree_service,
            context_render_service=self.render_service,
            memory_runtime_service=memory_runtime_service,
            artifact_service=artifact_service,
        )


class _ToolService:
    def get_tool(self, tool_id: str) -> Tool:
        if tool_id != "fetch_weather":
            raise ToolError(tool_id)
        return Tool(
            id="fetch_weather",
            name="Fetch Weather",
            description="Fetch weather for a city.",
            parameters=(
                ToolParameter(
                    name="city",
                    data_type="string",
                    description="City name.",
                ),
            ),
        )


class _SkillService:
    def __init__(self) -> None:
        self.package = SkillPackage(
            manifest=SkillManifest(
                api_version="v1",
                kind="Skill",
                name="review",
                description="Review code.",
                when_to_use="Use for code review.",
            ),
            root_path="/tmp/ws/.skills/review",
            manifest_path="/tmp/ws/.skills/review/skill.yaml",
            instructions_path="/tmp/ws/.skills/review/SKILL.md",
            source="workspace",
        )

    def list_available(self, **_kwargs):
        return (self.package,)

    def get(self, **_kwargs):
        return self.package

    def read(self, **_kwargs):
        return SkillReadResult(
            package=self.package,
            requested_path="SKILL.md",
            resolved_path="/tmp/ws/.skills/review/SKILL.md",
            content="# Review\n\nRead diffs and prioritize bugs.",
        )


class _FakeMemoryRuntime:
    def __init__(self) -> None:
        self.requests: list[MemoryRecallRequest] = []

    def recall(self, request: MemoryRecallRequest) -> MemoryRecallResult:
        self.requests.append(request)
        return MemoryRecallResult(
            scope=MemoryResolvedScope(
                context=MemoryUseContext(
                    space_id="memory:assistant",
                    storage_root="/tmp/memory",
                ),
                scope_ref="assistant",
                engine_id="fake",
            ),
            query=request.query,
            items=(
                MemoryRecallItem(
                    path="memory/2026-05-29.md",
                    kind="daily",
                    citation="memory/2026-05-29.md:1-2",
                    text="User birthday is May 1.",
                    start_line=1,
                    end_line=2,
                    score=0.9,
                    source_scope_ref="assistant",
                    source_layer_kind="private",
                ),
            ),
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
            size_bytes=3,
            width=8,
            height=8,
        )
        self.requests: list[tuple[str, ArtifactVariant]] = []

    def resolve_variant(
        self,
        artifact_id: str,
        *,
        variant: ArtifactVariant = ArtifactVariant.ORIGINAL,
    ) -> ArtifactBinary:
        self.requests.append((artifact_id, variant))
        return ArtifactBinary(
            artifact=self.artifact,
            path=self.path,
            variant=variant,
        )


def _deps(
    *,
    include_skill_provider: bool = False,
    memory_runtime_service=None,
    artifact_service=None,
) -> _Deps:
    return _Deps(
        include_skill_provider=include_skill_provider,
        memory_runtime_service=memory_runtime_service,
        artifact_service=artifact_service,
    )
