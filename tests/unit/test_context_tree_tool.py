from __future__ import annotations

import asyncio
from pathlib import Path

from crxzipple.app.integration.context_workspace_tool import ToolContextNodeProvider
from crxzipple.app.integration.context_workspace_skills import SkillContextNodeProvider
from crxzipple.modules.context_workspace.application import (
    ContextOwnerRegistry,
    ContextNodeUpsertInput,
    ContextRenderService,
    ContextTreeService,
    ContextWorkspaceService,
    EnsureContextWorkspaceInput,
    RecordContextRenderSnapshotInput,
    RenderContextPromptInput,
)
from crxzipple.modules.skills.application import SkillPackage, SkillReadResult
from crxzipple.modules.skills.domain import SkillManifest
from crxzipple.modules.context_workspace.domain import (
    ContextAction,
    ContextNodeSeed,
    ContextNodeState,
)
from crxzipple.modules.context_workspace.infrastructure import (
    InMemoryContextNodeRepository,
    InMemoryContextOperationRepository,
    InMemoryContextRenderSnapshotRepository,
    InMemoryContextWorkspaceRepository,
)
from crxzipple.modules.tool.application import ToolPromptBundle
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
    context_tree_diff_since,
    context_tree_list,
    context_tree_read_snapshot,
    context_tree_render_current,
    context_tree_update_plan,
)


def test_context_tree_tool_manifest_does_not_reintroduce_owner_resource_actions() -> None:
    manifest_text = (
        Path(__file__).resolve().parents[2] / "tools" / "context_tree" / "tool.yaml"
    ).read_text(encoding="utf-8")

    assert "context_tree.read_skill" not in manifest_text
    assert "context_tree.open_artifact" not in manifest_text
    assert "context_tree.recall_memory" not in manifest_text
    assert "read_skill" not in manifest_text
    assert "open_artifact" not in manifest_text
    assert "recall_memory" not in manifest_text
    assert "context_tree.render_current" in manifest_text
    assert "context_tree.read_snapshot" in manifest_text
    assert "context_tree.diff_since" in manifest_text


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
    assert "tools.bundle.bundled.openapi.weather" in expand_result.details["included_node_ids"]
    assert expand_result.details["loaded_child_handles"] == [
        {
            "id": "tools.bundle.bundled.openapi.weather",
            "title": "Weather",
            "kind": "tool_bundle",
            "state": "collapsed",
        },
    ]
    assert "Loaded child handles:" in expand_result.blocks[0]["text"]
    assert "tools.bundle.bundled.openapi.weather" in expand_result.blocks[0]["text"]

    expand_group_result = asyncio.run(
        context_tree_expand(deps.tool_deps)(
            {"node_id": "tools.bundle.bundled.openapi.weather"},
            execution_context,
        ),
    )
    assert "tools.tool.fetch_weather" in expand_group_result.details["included_node_ids"]
    assert expand_group_result.details["tool_schema_mirror_available"] is True
    assert expand_group_result.details["mirrored_tool_schema_names"] == []
    assert "Mirrored tool schemas now callable" not in expand_group_result.blocks[0]["text"]

    estimate_result = asyncio.run(context_tree_estimate(deps.tool_deps)({}, execution_context))
    assert estimate_result.details["tool_schema_mirror_available"] is True
    assert estimate_result.details["mirrored_node_ids"] == []

    enable_result = asyncio.run(
        context_tree_enable_tool_schema(deps.tool_deps)(
            {"node_id": "tools.tool.fetch_weather"},
            execution_context,
        ),
    )
    assert enable_result.details["node"]["state"]["schema_enabled"] is True
    assert enable_result.details["mirrored_node_ids"] == ["tools.tool.fetch_weather"]

    disable_result = asyncio.run(
        context_tree_disable_tool_schema(deps.tool_deps)(
            {"node_id": "tools.tool.fetch_weather"},
            execution_context,
        ),
    )
    assert disable_result.details["node"]["state"]["schema_enabled"] is False
    assert disable_result.details["mirrored_node_ids"] == []

    list_result = asyncio.run(context_tree_list(deps.tool_deps)({}, execution_context))
    node_ids = [node["id"] for node in list_result.details["nodes"]]
    assert "tools.available" in node_ids
    assert "tools.tool.fetch_weather" in node_ids
    assert "metadata" not in list_result.details["nodes"][0]


def test_context_tree_tool_requires_session_key() -> None:
    deps = _deps()
    handler = context_tree_list(deps.tool_deps)

    try:
        asyncio.run(handler({}, None))
    except ValueError as exc:
        assert "session_key" in str(exc)
    else:  # pragma: no cover - defensive assertion branch.
        raise AssertionError("context_tree.list should require session_key")


def test_context_tree_replay_tools_render_read_snapshot_and_diff() -> None:
    deps = _deps()
    deps.workspace_service.ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:replay",
            agent_id="assistant",
            metadata={"available_tool_names": ["fetch_weather"]},
        ),
    )
    execution_context = ToolExecutionContext(
        attrs={
            "session_key": "session:replay",
            "agent_id": "assistant",
            "run_id": "run-replay",
        },
    )

    current_result = asyncio.run(
        context_tree_render_current(deps.tool_deps)(
            {"max_chars": 8000},
            execution_context,
        ),
    )
    assert current_result.metadata["tool"] == "context_tree.render_current"
    assert current_result.details["revision"] == 1
    assert "session.current" in current_result.details["included_node_ids"]
    assert "<context_tree" in current_result.blocks[0]["text"]
    assert current_result.details["prompt_body"] == deps.render_service.render_prompt_body(
        RenderContextPromptInput(session_key="session:replay"),
    ).prompt_body

    rendered = deps.render_service.render_prompt_body(
        RenderContextPromptInput(session_key="session:replay"),
    )
    snapshot = deps.render_service.record_render_snapshot(
        RecordContextRenderSnapshotInput(
            session_key="session:replay",
            run_id="run-replay",
            prompt_body=rendered.prompt_body,
            estimate=rendered.estimate,
            included_node_ids=rendered.included_node_ids,
            mirrored_node_ids=rendered.mirrored_node_ids,
            snapshot_id="ctxsnap_replay",
        ),
    )

    read_result = asyncio.run(
        context_tree_read_snapshot(deps.tool_deps)(
            {"snapshot_id": snapshot.id, "max_chars": 8000},
            execution_context,
        ),
    )
    assert read_result.metadata["tool"] == "context_tree.read_snapshot"
    assert read_result.metadata["snapshot_id"] == "ctxsnap_replay"
    assert read_result.details["prompt_body"] == rendered.prompt_body
    assert "<context_tree" in read_result.blocks[0]["text"]

    deps.tree_service.upsert_nodes(
        ContextNodeUpsertInput(
            session_key="session:replay",
            nodes=(
                ContextNodeSeed(
                    node_id="custom.replay",
                    parent_id="execution.current",
                    owner="context_workspace",
                    kind="test_context",
                    title="Replay Evidence",
                    summary="Replay diff evidence.",
                    content="replay_diff: true",
                    state=ContextNodeState(collapsed=False, loaded=True),
                ),
            ),
            action=ContextAction.UPSERT,
            parent_node_id="execution.current",
        ),
    )
    diff_result = asyncio.run(
        context_tree_diff_since(deps.tool_deps)(
            {"snapshot_id": snapshot.id},
            execution_context,
        ),
    )
    assert diff_result.metadata["tool"] == "context_tree.diff_since"
    assert diff_result.details["baseline_snapshot_id"] == "ctxsnap_replay"
    assert diff_result.details["changed_revision"] is True
    assert "custom.replay" in diff_result.details["added_node_ids"]
    assert "Added rendered node ids:" in diff_result.blocks[0]["text"]


def test_context_tree_expand_skill_exposes_skill_read_handle() -> None:
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
    expand_result = asyncio.run(
        context_tree_expand(deps.tool_deps)(
            {"node_id": "skills.skill.review"},
            execution_context,
        ),
    )

    assert expand_result.metadata["tool"] == "context_tree.expand"
    assert "skills.skill.review.instructions" in expand_result.details["included_node_ids"]
    tree = deps.tree_service.list_tree("session:skills")
    instruction_nodes = [
        node for node in tree.nodes if node.id == "skills.skill.review.instructions"
    ]
    assert len(instruction_nodes) == 1
    assert instruction_nodes[0].metadata["content_available_via"] == "skill_read"
    assert "skill_read" in instruction_nodes[0].summary
    assert "Read diffs" not in instruction_nodes[0].summary


def test_context_tree_update_plan_records_visible_working_plan() -> None:
    deps = _deps()
    deps.workspace_service.ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:plan",
            agent_id="assistant",
        ),
    )
    execution_context = ToolExecutionContext(
        attrs={
            "session_key": "session:plan",
            "agent_id": "assistant",
            "run_id": "run-plan",
        },
    )

    result = asyncio.run(
        context_tree_update_plan(deps.tool_deps)(
            {
                "objective": "Make browser research behave like an engineering agent.",
                "status": "in_progress",
                "current_step": "Wire public plan affordance.",
                "completed_steps": ["Added work.plan default root."],
                "verified_facts": ["Context Tree render includes loaded root nodes."],
                "assumptions": ["Agent will update this node as progress changes."],
                "next_steps": ["Run focused tests."],
            },
            execution_context,
        ),
    )

    assert result.metadata["tool"] == "context_tree.update_plan"
    assert result.metadata["node_id"] == "work.plan"
    assert result.metadata["no_op"] is False
    assert result.metadata["plan_phase"] == (
        "in_progress:Wire public plan affordance."
    )
    assert result.metadata["phase_changed"] is True
    assert result.metadata["plan_update_count"] == 1
    assert result.details["node"]["id"] == "work.plan"
    assert result.details["node"]["parent_id"] == "execution.current"
    assert result.details["node"]["state"]["pinned"] is True
    assert result.details["node"]["metadata"]["plan_phase"] == (
        "in_progress:Wire public plan affordance."
    )
    assert result.details["node"]["metadata"]["plan_update_count"] == 1
    assert "Updated visible working plan" in result.blocks[0]["text"]
    rendered = deps.render_service.render_prompt_body(
        RenderContextPromptInput(session_key="session:plan"),
    )
    assert "work.plan" in rendered.included_node_ids
    assert "<node id=\"work.plan\"" in rendered.prompt_body
    assert "working_plan:" in rendered.prompt_body
    assert "Context Tree render includes loaded root nodes." in rendered.prompt_body


def test_context_tree_update_plan_terminal_status_tells_agent_to_answer() -> None:
    deps = _deps()
    deps.workspace_service.ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:plan-done",
            agent_id="assistant",
        ),
    )
    execution_context = ToolExecutionContext(
        attrs={
            "session_key": "session:plan-done",
            "agent_id": "assistant",
            "run_id": "run-plan-done",
        },
    )

    result = asyncio.run(
        context_tree_update_plan(deps.tool_deps)(
            {
                "objective": "Answer from verified weather facts.",
                "status": "done",
                "current_step": "Weather facts are ready.",
                "verified_facts": ["Kunming hourly forecast is available."],
                "next_steps": ["None"],
                "update_reason": "final_summary",
            },
            execution_context,
        ),
    )

    assert result.metadata["terminal_plan"] is True
    assert "Plan status is complete" in result.blocks[0]["text"]
    assert "produce the final user-facing answer now" in result.blocks[0]["text"]


def test_context_tree_update_plan_terminal_status_blocks_same_objective_reopen() -> None:
    deps = _deps()
    deps.workspace_service.ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:plan-terminal-lock",
            agent_id="assistant",
        ),
    )
    execution_context = ToolExecutionContext(
        attrs={
            "session_key": "session:plan-terminal-lock",
            "agent_id": "assistant",
            "run_id": "run-plan-terminal-lock",
        },
    )

    terminal = asyncio.run(
        context_tree_update_plan(deps.tool_deps)(
            {
                "objective": "Answer from verified weather facts.",
                "status": "done",
                "current_step": "Weather facts are ready.",
                "verified_facts": ["Kunming hourly forecast is available."],
                "update_reason": "final_summary",
            },
            execution_context,
        ),
    )
    first_revision = int(terminal.details["revision"])

    reopen = asyncio.run(
        context_tree_update_plan(deps.tool_deps)(
            {
                "objective": "Answer from verified weather facts.",
                "status": "in_progress",
                "current_step": "Re-run the same weather lookup.",
                "next_steps": ["Call the weather tool again."],
                "update_reason": "phase_change",
            },
            execution_context,
        ),
    )

    assert reopen.metadata["no_op"] is True
    assert reopen.metadata["no_op_reason"] == "terminal_plan_locked"
    assert reopen.metadata["terminal_plan"] is True
    assert int(reopen.details["revision"]) == first_revision
    assert "already complete" in reopen.blocks[0]["text"]
    assert "final user-facing answer" in reopen.blocks[0]["text"]


def test_context_tree_expand_after_terminal_plan_tells_agent_to_answer() -> None:
    deps = _deps()
    deps.workspace_service.ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:plan-expand-terminal",
            agent_id="assistant",
        ),
    )
    execution_context = ToolExecutionContext(
        attrs={
            "session_key": "session:plan-expand-terminal",
            "agent_id": "assistant",
            "run_id": "run-plan-expand-terminal",
        },
    )
    asyncio.run(
        context_tree_update_plan(deps.tool_deps)(
            {
                "objective": "Answer from verified weather facts.",
                "status": "done",
                "current_step": "Weather facts are ready.",
                "verified_facts": ["Kunming hourly forecast is available."],
                "update_reason": "final_summary",
            },
            execution_context,
        ),
    )

    expanded = asyncio.run(
        context_tree_expand(deps.tool_deps)(
            {"node_id": "tools.available"},
            execution_context,
        ),
    )

    assert expanded.metadata["terminal_plan"] is True
    assert "Current working plan is complete" in expanded.blocks[0]["text"]
    assert "final user-facing answer now" in expanded.blocks[0]["text"]


def test_context_tree_update_plan_repeated_payload_is_no_op() -> None:
    deps = _deps()
    deps.workspace_service.ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:plan-noop",
            agent_id="assistant",
        ),
    )
    execution_context = ToolExecutionContext(
        attrs={
            "session_key": "session:plan-noop",
            "agent_id": "assistant",
            "run_id": "run-plan-noop",
        },
    )
    payload = {
        "objective": "Investigate browser route drift.",
        "status": "in_progress",
        "current_step": "Compare prompt surfaces.",
        "verified_facts": ["Provider sees browser runtime starter tools."],
        "next_steps": ["Validate a fixture run."],
        "update_reason": "phase_change",
    }

    first = asyncio.run(
        context_tree_update_plan(deps.tool_deps)(payload, execution_context),
    )
    first_revision = int(first.details["revision"])
    second = asyncio.run(
        context_tree_update_plan(deps.tool_deps)(payload, execution_context),
    )

    assert second.metadata["no_op"] is True
    assert second.metadata["no_op_reason"] == "same_plan"
    assert second.details["operation_id"] is None
    assert int(second.details["revision"]) == first_revision
    assert "unchanged" in second.blocks[0]["text"]

    changed = asyncio.run(
        context_tree_update_plan(deps.tool_deps)(
            {
                **payload,
                "verified_facts": [
                    "Provider sees browser runtime starter tools.",
                    "Direct transcript uses compact tool envelopes.",
                ],
                "update_reason": "verified_fact",
            },
            execution_context,
        ),
    )

    assert changed.metadata["no_op"] is False
    assert changed.metadata["phase_changed"] is False
    assert changed.metadata["plan_update_count"] == 2
    assert int(changed.details["revision"]) > first_revision


def test_context_tree_update_plan_same_phase_update_is_no_op() -> None:
    deps = _deps()
    deps.workspace_service.ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:plan-phase",
            agent_id="assistant",
        ),
    )
    execution_context = ToolExecutionContext(
        attrs={
            "session_key": "session:plan-phase",
            "agent_id": "assistant",
            "run_id": "run-plan-phase",
        },
    )
    payload = {
        "objective": "Keep browser investigation on evidence paths.",
        "status": "in_progress",
        "current_step": "Inspect runtime and network.",
        "completed_steps": ["Opened target page."],
        "next_steps": ["Inspect runtime."],
        "update_reason": "phase_change",
    }

    first = asyncio.run(
        context_tree_update_plan(deps.tool_deps)(payload, execution_context),
    )
    first_revision = int(first.details["revision"])

    same_phase = asyncio.run(
        context_tree_update_plan(deps.tool_deps)(
            {
                **payload,
                "completed_steps": [
                    "Opened target page.",
                    "Listed visible tabs.",
                ],
            },
            execution_context,
        ),
    )

    assert same_phase.metadata["no_op"] is True
    assert same_phase.metadata["no_op_reason"] == "same_phase"
    assert same_phase.metadata["phase_changed"] is False
    assert int(same_phase.details["revision"]) == first_revision
    assert "phase unchanged" in same_phase.blocks[0]["text"]

    verified_fact = asyncio.run(
        context_tree_update_plan(deps.tool_deps)(
            {
                **payload,
                "verified_facts": ["Runtime exposes Nuxt shopping API methods."],
                "update_reason": "verified_fact",
            },
            execution_context,
        ),
    )

    assert verified_fact.metadata["no_op"] is False
    assert verified_fact.metadata["phase_changed"] is False
    assert verified_fact.metadata["plan_update_count"] == 2
    assert int(verified_fact.details["revision"]) > first_revision


class _Deps:
    def __init__(
        self,
        *,
        include_skill_provider: bool = False,
    ) -> None:
        self.workspaces = InMemoryContextWorkspaceRepository()
        self.nodes = InMemoryContextNodeRepository()
        self.operations = InMemoryContextOperationRepository()
        self.snapshots = InMemoryContextRenderSnapshotRepository()
        self.registry = ContextOwnerRegistry()
        tool_service = _ToolService()
        self.registry.register(ToolContextNodeProvider(tool_service, tool_service))
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
        )


class _ToolService:
    def get_tool(self, tool_id: str) -> Tool:
        if tool_id != "fetch_weather":
            raise ToolError(tool_id)
        return Tool(
            id="fetch_weather",
            source_id="bundled.openapi.weather",
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

    def get_tools(self, tool_ids) -> dict[str, Tool]:
        return {
            str(tool_id): self.get_tool(str(tool_id))
            for tool_id in tool_ids
            if str(tool_id) == "fetch_weather"
        }

    def list_prompt_bundles(
        self,
        function_ids,
    ) -> tuple[ToolPromptBundle, ...]:
        if "fetch_weather" not in set(function_ids):
            return ()
        return (
            ToolPromptBundle(
                source_id="bundled.openapi.weather",
                title="Weather",
                summary="Weather tools.",
                source_kind="openapi",
                function_ids=("fetch_weather",),
                function_count=1,
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


def _deps(
    *,
    include_skill_provider: bool = False,
) -> _Deps:
    return _Deps(
        include_skill_provider=include_skill_provider,
    )
