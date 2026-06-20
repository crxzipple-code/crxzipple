from __future__ import annotations

from crxzipple.modules.context_workspace.application.rendering.provider_mirror import (
    render_provider_attachments,
)
from crxzipple.modules.context_workspace.domain import (
    ContextNode,
    ContextNodeState,
    ContextWorkspace,
)


def test_render_provider_attachments_mirrors_enabled_tool_schema() -> None:
    workspace = ContextWorkspace.new(
        session_key="session:mirror",
        agent_id="assistant",
    )
    tool_node = ContextNode(
        id="tool.weather",
        workspace_id=workspace.id,
        owner="tool",
        kind="tool_function",
        title="Weather",
        owner_ref={"tool_id": "tool.weather"},
        state=ContextNodeState(schema_enabled=True),
        metadata={
            "provider_schema": {
                "name": "weather.lookup",
                "description": "Lookup weather.",
                "input_schema": {"type": "object"},
            },
        },
    )

    attachments, mirrored_node_ids, available, report = render_provider_attachments(
        (tool_node,),
        base={},
        render_metadata={},
    )

    assert available is True
    assert mirrored_node_ids == ("tool.weather",)
    assert attachments["tool_schemas"][0]["name"] == "weather.lookup"
    budget = report["tool_schema_mirror_budget"]
    assert budget["available_count"] == 1
    assert budget["enabled_candidate_count"] == 1
    assert budget["mirrored_added_count"] == 1
    assert budget["status"] == "ok"


def test_render_provider_attachments_uses_default_schema_ids_without_state_enabled() -> None:
    workspace = ContextWorkspace.new(
        session_key="session:mirror",
        agent_id="assistant",
    )
    tool_node = ContextNode(
        id="tool.search",
        workspace_id=workspace.id,
        owner="tool",
        kind="tool_function",
        title="Search",
        owner_ref={"tool_id": "tool.search"},
        state=ContextNodeState(schema_enabled=False),
        metadata={
            "provider_schema": {
                "name": "search.web",
                "description": "Search web.",
            },
        },
    )

    attachments, mirrored_node_ids, _available, report = render_provider_attachments(
        (tool_node,),
        base={},
        render_metadata={
            "default_tool_schema_ids": ["tool.search"],
            "default_tool_schema_source": "runtime_policy",
        },
    )

    assert mirrored_node_ids == ("tool.search",)
    assert attachments["tool_schemas"][0]["name"] == "search.web"
    budget = report["tool_schema_mirror_budget"]
    assert budget["default_requested_count"] == 1
    assert budget["default_candidate_count"] == 1
    assert budget["default_mirrored_count"] == 1


def test_render_provider_attachments_prioritizes_context_tree_controls_under_budget() -> None:
    workspace = ContextWorkspace.new(
        session_key="session:mirror",
        agent_id="assistant",
    )
    noisy_nodes = tuple(
        ContextNode(
            id=f"tool.browser.{index:02d}",
            workspace_id=workspace.id,
            owner="tool",
            kind="tool_function",
            title=f"Browser {index}",
            owner_ref={"tool_id": f"browser.noisy_{index:02d}"},
            display_order=index,
            state=ContextNodeState(schema_enabled=True),
            metadata={
                "provider_schema": {
                    "name": f"browser.noisy_{index:02d}",
                    "description": "Noisy browser tool.",
                    "input_schema": {"type": "object"},
                },
            },
        )
        for index in range(34)
    )
    control_nodes = (
        ContextNode(
            id="tool.context_tree.expand",
            workspace_id=workspace.id,
            owner="tool",
            kind="tool_function",
            title="Expand",
            owner_ref={"tool_id": "context_tree.expand"},
            display_order=100,
            state=ContextNodeState(schema_enabled=True),
            metadata={
                "provider_schema": {
                    "name": "context_tree.expand",
                    "description": "Expand a context tree node.",
                    "input_schema": {"type": "object"},
                },
            },
        ),
        ContextNode(
            id="tool.context_tree.estimate",
            workspace_id=workspace.id,
            owner="tool",
            kind="tool_function",
            title="Estimate",
            owner_ref={"tool_id": "context_tree.estimate"},
            display_order=101,
            state=ContextNodeState(schema_enabled=True),
            metadata={
                "provider_schema": {
                    "name": "context_tree.estimate",
                    "description": "Estimate a context tree node.",
                    "input_schema": {"type": "object"},
                },
            },
        ),
    )

    attachments, mirrored_node_ids, _available, report = render_provider_attachments(
        noisy_nodes + control_nodes,
        base={},
        render_metadata={},
    )

    schema_names = [schema["name"] for schema in attachments["tool_schemas"]]
    budget = report["tool_schema_mirror_budget"]
    assert len(schema_names) == 32
    assert schema_names[:2] == ["context_tree.expand", "context_tree.estimate"]
    assert "tool.context_tree.expand" in mirrored_node_ids
    assert "tool.context_tree.estimate" in mirrored_node_ids
    assert budget["status"] == "limited"
    assert budget["skipped_by_reason"] == {"count_limit": 4}
    assert all(
        not str(item.get("name")).startswith("context_tree.")
        for item in budget["skipped"]
    )


def test_render_provider_attachments_uses_default_schema_priority_and_reasons() -> None:
    workspace = ContextWorkspace.new(
        session_key="session:mirror",
        agent_id="assistant",
    )
    late_node = ContextNode(
        id="tool.late",
        workspace_id=workspace.id,
        owner="tool",
        kind="tool_function",
        title="Late",
        owner_ref={"tool_id": "late.tool"},
        display_order=1,
        state=ContextNodeState(schema_enabled=False),
        metadata={
            "provider_schema": {
                "name": "late.tool",
                "description": "Late default tool.",
                "input_schema": {"type": "object"},
            },
        },
    )
    early_node = ContextNode(
        id="tool.early",
        workspace_id=workspace.id,
        owner="tool",
        kind="tool_function",
        title="Early",
        owner_ref={"tool_id": "early.tool"},
        display_order=2,
        state=ContextNodeState(schema_enabled=False),
        metadata={
            "provider_schema": {
                "name": "early.tool",
                "description": "Early default tool.",
                "input_schema": {"type": "object"},
            },
        },
    )

    attachments, _mirrored_node_ids, _available, report = render_provider_attachments(
        (late_node, early_node),
        base={},
        render_metadata={
            "default_tool_schema_ids": ["late.tool", "early.tool"],
            "default_tool_schema_source": "source_prompt.default_tool_schema_group_refs",
            "default_tool_schema_group_refs": [
                {
                    "source_id": "bundled.local_package.browser",
                    "group_key": "code_insight",
                    "reason": "browser_starter_code_insight",
                },
            ],
            "default_tool_schema_priorities": {
                "late.tool": 500,
                "early.tool": 100,
            },
            "default_tool_schema_reasons": {
                "early.tool": "browser_starter_code_insight",
                "late.tool": "browser_starter_navigation",
            },
        },
    )

    assert [schema["name"] for schema in attachments["tool_schemas"]] == [
        "early.tool",
        "late.tool",
    ]
    budget = report["tool_schema_mirror_budget"]
    assert budget["default_group_ref_count"] == 1
    assert budget["default_group_refs"][0]["reason"] == "browser_starter_code_insight"
    assert budget["default_schema_priorities"]["early.tool"] == 100
    assert budget["default_schema_reasons"]["late.tool"] == "browser_starter_navigation"
    assert budget["default_mirrored"][0]["name"] == "early.tool"
    assert budget["default_mirrored"][0]["bootstrap_reason"] == (
        "browser_starter_code_insight"
    )


def test_render_provider_attachments_records_budget_eviction_policy_metadata() -> None:
    workspace = ContextWorkspace.new(
        session_key="session:mirror",
        agent_id="assistant",
    )
    nodes = tuple(
        ContextNode(
            id=f"tool.default.{index}",
            workspace_id=workspace.id,
            owner="tool",
            kind="tool_function",
            title=f"Default {index}",
            owner_ref={"tool_id": f"default.tool_{index}"},
            display_order=index,
            state=ContextNodeState(schema_enabled=False),
            metadata={
                "provider_schema": {
                    "name": f"default.tool_{index}",
                    "description": f"Default tool {index}.",
                    "input_schema": {"type": "object"},
                },
            },
        )
        for index in range(3)
    )

    attachments, _mirrored_node_ids, _available, report = render_provider_attachments(
        nodes,
        base={},
        render_metadata={
            "default_tool_schema_ids": [
                "default.tool_0",
                "default.tool_1",
                "default.tool_2",
            ],
            "default_tool_schema_priorities": {
                "default.tool_0": 100,
                "default.tool_1": 200,
                "default.tool_2": 300,
            },
            "default_tool_schema_reasons": {
                "default.tool_2": "low_priority_default",
            },
            "tool_schema_mirror_max_count": 2,
        },
    )

    assert [schema["name"] for schema in attachments["tool_schemas"]] == [
        "default.tool_0",
        "default.tool_1",
    ]
    budget = report["tool_schema_mirror_budget"]
    assert budget["status"] == "limited"
    assert budget["max_count"] == 2
    assert budget["skipped_count"] == 1
    assert budget["skipped"] == [
        {
            "node_id": "tool.default.2",
            "name": "default.tool_2",
            "reason": "count_limit",
            "estimated_tokens": budget["skipped"][0]["estimated_tokens"],
            "selection": "default",
            "priority": 300,
            "bootstrap_reason": "low_priority_default",
        },
    ]


def test_render_provider_attachments_prioritizes_explicit_enabled_schema_over_defaults() -> None:
    workspace = ContextWorkspace.new(
        session_key="session:mirror",
        agent_id="assistant",
    )
    default_nodes = tuple(
        ContextNode(
            id=f"tool.default.{index}",
            workspace_id=workspace.id,
            owner="tool",
            kind="tool_function",
            title=f"Default {index}",
            owner_ref={"tool_id": f"default.tool_{index}"},
            display_order=index,
            state=ContextNodeState(schema_enabled=False),
            metadata={
                "provider_schema": {
                    "name": f"default.tool_{index}",
                    "description": f"Default tool {index}.",
                    "input_schema": {"type": "object"},
                },
            },
        )
        for index in range(2)
    )
    requested_node = ContextNode(
        id="tool.requested.network",
        workspace_id=workspace.id,
        owner="tool",
        kind="tool_function",
        title="Requested Network Tool",
        owner_ref={"tool_id": "browser.network.inspect"},
        display_order=100,
        state=ContextNodeState(schema_enabled=True),
        metadata={
            "provider_schema": {
                "name": "browser.network.inspect",
                "description": "Inspect browser network evidence.",
                "input_schema": {"type": "object"},
            },
        },
    )

    attachments, mirrored_node_ids, _available, report = render_provider_attachments(
        default_nodes + (requested_node,),
        base={},
        render_metadata={
            "default_tool_schema_ids": ["default.tool_0", "default.tool_1"],
            "default_tool_schema_priorities": {
                "default.tool_0": 100,
                "default.tool_1": 200,
            },
            "tool_schema_mirror_max_count": 2,
        },
    )

    assert [schema["name"] for schema in attachments["tool_schemas"]] == [
        "browser.network.inspect",
        "default.tool_0",
    ]
    assert "tool.requested.network" in mirrored_node_ids
    budget = report["tool_schema_mirror_budget"]
    assert budget["status"] == "limited"
    assert budget["skipped"][0]["name"] == "default.tool_1"


def test_render_provider_attachments_mirrors_opened_artifact_candidate() -> None:
    workspace = ContextWorkspace.new(
        session_key="session:mirror",
        agent_id="assistant",
    )
    artifact_node = ContextNode(
        id="artifact.image.1",
        workspace_id=workspace.id,
        owner="artifacts",
        kind="artifact_image",
        title="Chart",
        owner_ref={"artifact_id": "artifact-1", "preferred_variant": "preview"},
        state=ContextNodeState(opened=True),
        metadata={"mime_type": "image/png", "name": "chart.png"},
    )

    attachments, mirrored_node_ids, _available, _report = render_provider_attachments(
        (artifact_node,),
        base={},
        render_metadata={},
    )

    assert mirrored_node_ids == ("artifact.image.1",)
    assert attachments["artifact_content_candidates"] == [
        {
            "node_id": "artifact.image.1",
            "artifact_id": "artifact-1",
            "kind": "artifact_image",
            "mime_type": "image/png",
            "name": "chart.png",
            "preferred_variant": "preview",
        },
    ]
