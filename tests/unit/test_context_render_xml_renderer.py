from __future__ import annotations

from crxzipple.modules.context_workspace.application.rendering.xml_renderer import (
    render_context_tree,
    tree_snapshot_visible_nodes,
)
from crxzipple.modules.context_workspace.domain import (
    ContextNode,
    ContextNodeState,
    ContextWorkspace,
)


def test_render_context_tree_outputs_xml_like_tree_with_escaped_content() -> None:
    workspace = ContextWorkspace.new(
        session_key="session:xml",
        agent_id="assistant",
    )
    nodes = (
        ContextNode(
            id="root",
            workspace_id=workspace.id,
            owner="runtime",
            kind="section",
            title="Root",
            summary="Summary",
            content="Visible <content> & details",
            state=ContextNodeState(collapsed=False),
        ),
        ContextNode(
            id="child",
            workspace_id=workspace.id,
            parent_id="root",
            owner="session",
            kind="note",
            title="Child",
            summary="Child summary",
            content="Hidden while parent is visible.",
            state=ContextNodeState(collapsed=True),
        ),
    )

    rendered = render_context_tree(workspace, nodes)

    assert rendered.startswith('<context_tree session="session:xml"')
    assert '<node id="root" kind="section" owner="runtime" state="expanded"' in rendered
    assert "<content>Visible &lt;content&gt; &amp; details</content>" in rendered
    assert '<node id="child" kind="note" owner="session" state="collapsed"' in rendered
    assert "Hidden while parent is visible." not in rendered


def test_render_context_tree_suppresses_handle_only_owner_content() -> None:
    workspace = ContextWorkspace.new(
        session_key="session:xml",
        agent_id="assistant",
    )
    node = ContextNode(
        id="workspace.file.AGENTS.md",
        workspace_id=workspace.id,
        owner="workspace",
        kind="workspace_file",
        title="AGENTS.md",
        summary="Workspace file handle.",
        content="Raw workspace file body must not render.",
        state=ContextNodeState(collapsed=False, pinned=True),
    )

    rendered = render_context_tree(workspace, (node,))

    assert "Workspace file handle." in rendered
    assert "Raw workspace file body must not render." not in rendered


def test_tree_snapshot_visible_nodes_keeps_pinned_descendant_under_collapsed_parent() -> None:
    workspace = ContextWorkspace.new(
        session_key="session:xml",
        agent_id="assistant",
    )
    root = ContextNode(
        id="root",
        workspace_id=workspace.id,
        owner="runtime",
        kind="section",
        title="Root",
        state=ContextNodeState(collapsed=True),
    )
    pinned_child = ContextNode(
        id="child",
        workspace_id=workspace.id,
        parent_id="root",
        owner="session",
        kind="note",
        title="Child",
        state=ContextNodeState(collapsed=True, pinned=True),
    )
    hidden_child = ContextNode(
        id="hidden",
        workspace_id=workspace.id,
        parent_id="root",
        owner="session",
        kind="note",
        title="Hidden",
        state=ContextNodeState(collapsed=True),
    )

    visible = tree_snapshot_visible_nodes((root, hidden_child, pinned_child))

    assert tuple(node.id for node in visible) == ("root", "child")


def test_render_context_tree_guards_large_non_frontier_tool_interaction_content() -> None:
    workspace = ContextWorkspace.new(
        session_key="session:xml",
        agent_id="assistant",
    )
    tool_node = ContextNode(
        id="session.tool_interaction.big",
        workspace_id=workspace.id,
        owner="session",
        kind="tool_interaction",
        title="browser.observe",
        summary="Large consumed browser observation.",
        owner_ref={
            "tool_name": "browser.observe",
            "tool_call_id": "call-big",
            "status": "success",
            "frontier": False,
            "consumed": True,
        },
        state=ContextNodeState(collapsed=False, consumed=True),
        metadata={
            "tool_name": "browser.observe",
            "tool_call_id": "call-big",
            "result_content": "large snapshot " + ("x" * 2_000) + " SECRET_TAIL",
        },
    )

    rendered = render_context_tree(workspace, (tool_node,))

    assert 'summary="Large consumed browser observation."' in rendered
    assert 'content_omitted="non_frontier_budget_guard"' in rendered
    assert 'frontier="false"' not in rendered
    assert 'consumed="true"' not in rendered
    assert "SECRET_TAIL" not in rendered


def test_render_context_tree_allows_pinned_tool_interaction_full_content() -> None:
    workspace = ContextWorkspace.new(
        session_key="session:xml",
        agent_id="assistant",
    )
    tool_node = ContextNode(
        id="session.tool_interaction.big",
        workspace_id=workspace.id,
        owner="session",
        kind="tool_interaction",
        title="browser.observe",
        summary="Pinned browser observation.",
        owner_ref={
            "tool_name": "browser.observe",
            "tool_call_id": "call-big",
            "status": "success",
            "frontier": False,
            "consumed": True,
        },
        state=ContextNodeState(collapsed=False, pinned=True, consumed=True),
        metadata={
            "tool_name": "browser.observe",
            "tool_call_id": "call-big",
            "result_content": "large snapshot " + ("x" * 2_000) + " SECRET_TAIL",
        },
    )

    rendered = render_context_tree(workspace, (tool_node,))

    assert "<result>" in rendered
    assert "SECRET_TAIL" in rendered
    assert "content_omitted" not in rendered


def test_render_context_tree_compacts_non_frontier_context_tree_tool_results() -> None:
    workspace = ContextWorkspace.new(
        session_key="session:xml",
        agent_id="assistant",
    )
    tool_node = ContextNode(
        id="session.tool_interaction.context_tree",
        workspace_id=workspace.id,
        owner="session",
        kind="tool_interaction",
        title="context_tree.expand",
        summary="Expanded a tool group.",
        owner_ref={
            "tool_name": "context_tree.expand",
            "tool_call_id": "call-tree",
            "status": "success",
            "frontier": False,
            "consumed": True,
        },
        state=ContextNodeState(collapsed=False, consumed=True),
        metadata={
            "tool_name": "context_tree.expand",
            "tool_call_id": "call-tree",
            "result_content": "Loaded child handles: tools.tool.browser.observe",
        },
    )

    rendered = render_context_tree(workspace, (tool_node,))

    assert "content_omitted" in rendered
    assert "Loaded child handles" not in rendered


def test_render_context_tree_omits_collapsed_enabled_tool_function_catalog_entry() -> None:
    workspace = ContextWorkspace.new(
        session_key="session:xml",
        agent_id="assistant",
    )
    tool_node = ContextNode(
        id="tools.tool.browser.observe",
        workspace_id=workspace.id,
        owner="tool",
        kind="tool_function",
        title="browser.observe",
        summary=(
            "Observe the current browser page and return a concise interaction "
            "surface. " + ("x" * 1_000) + " SECRET_TAIL"
        ),
        owner_ref={
            "tool_id": "browser.observe",
            "tool_name": "Browser Observe",
            "source_id": "bundled.local_package.browser",
            "runtime_key": "browser",
        },
        state=ContextNodeState(collapsed=True, schema_enabled=True),
        metadata={
            "required_effect_ids": ["browser.read"],
            "access_requirements": ["daemon-group:browser"],
            "capability_ids": ["browser.observe"],
        },
    )

    rendered = render_context_tree(workspace, (tool_node,))

    assert "<tool_function" not in rendered
    assert 'schema_enabled="true"' not in rendered
    assert 'access="daemon-group:browser"' not in rendered
    assert "effects=" not in rendered
    assert "capabilities=" not in rendered
    assert "summary=" not in rendered
    assert "<summary>" not in rendered
    assert "SECRET_TAIL" not in rendered
    assert len(rendered) < 520


def test_render_context_tree_keeps_compact_tool_summary_without_schema_mirror() -> None:
    workspace = ContextWorkspace.new(
        session_key="session:xml",
        agent_id="assistant",
    )
    tool_node = ContextNode(
        id="tools.tool.fetch_weather",
        workspace_id=workspace.id,
        owner="tool",
        kind="tool_function",
        title="fetch_weather",
        summary="Fetch current weather by city name.",
        owner_ref={
            "tool_id": "fetch_weather",
            "source_id": "configured.openapi.weather",
        },
        state=ContextNodeState(collapsed=True, schema_enabled=False),
    )

    rendered = render_context_tree(workspace, (tool_node,))

    assert '<tool_function name="fetch_weather"' in rendered
    assert 'schema_enabled="false"' in rendered
    assert 'summary="Fetch current weather by city name."' in rendered


def test_render_context_tree_compacts_tool_bundle_and_group_nodes() -> None:
    workspace = ContextWorkspace.new(
        session_key="session:xml",
        agent_id="assistant",
    )
    bundle = ContextNode(
        id="tools.bundle.bundled.local_package.browser",
        workspace_id=workspace.id,
        owner="tool",
        kind="tool_bundle",
        title="Browser Automation",
        summary="Browser source summary. " + ("x" * 500) + " SECRET_TAIL",
        owner_ref={
            "source_id": "bundled.local_package.browser",
            "function_count": 12,
        },
        state=ContextNodeState(collapsed=False),
        metadata={
            "credential_requirement_count": 0,
            "runtime_requirement_count": 1,
        },
    )
    group = ContextNode(
        id="tools.bundle.bundled.local_package.browser.group.observation",
        workspace_id=workspace.id,
        parent_id=bundle.id,
        owner="tool",
        kind="tool_bundle_group",
        title="Browser Observation",
        summary="Observation group summary. " + ("y" * 500) + " SECRET_GROUP_TAIL",
        owner_ref={
            "source_id": "bundled.local_package.browser",
            "group_key": "observation",
            "function_count": 1,
        },
        state=ContextNodeState(collapsed=False),
    )
    tool = ContextNode(
        id="tools.tool.browser.observe",
        workspace_id=workspace.id,
        parent_id=group.id,
        owner="tool",
        kind="tool_function",
        title="browser.observe",
        summary="Observe browser state.",
        owner_ref={"tool_id": "browser.observe"},
        state=ContextNodeState(collapsed=True, schema_enabled=False),
    )

    rendered = render_context_tree(workspace, (bundle, group, tool))

    assert '<tool_bundle node_id="tools.bundle.bundled.local_package.browser"' in rendered
    assert '<tool_group node_id="tools.bundle.bundled.local_package.browser.group.observation"' in rendered
    assert 'title="Browser Observation"' in rendered
    assert 'group_key="observation"' in rendered
    assert 'runtime_requirements="1"' in rendered
    assert '<node id="tools.bundle.bundled.local_package.browser"' not in rendered
    assert "SECRET_TAIL" not in rendered
    assert "SECRET_GROUP_TAIL" not in rendered
    assert '<tool_function name="browser.observe"' in rendered
    assert len(rendered) < 1_500


def test_render_context_tree_expands_tool_function_details_when_opened() -> None:
    workspace = ContextWorkspace.new(
        session_key="session:xml",
        agent_id="assistant",
    )
    tool_node = ContextNode(
        id="tools.tool.browser.observe",
        workspace_id=workspace.id,
        owner="tool",
        kind="tool_function",
        title="browser.observe",
        summary="FULL_BROWSER_OBSERVE_DESCRIPTION",
        owner_ref={
            "tool_id": "browser.observe",
            "tool_name": "Browser Observe",
            "source_id": "bundled.local_package.browser",
        },
        state=ContextNodeState(collapsed=False, opened=True, schema_enabled=True),
    )

    rendered = render_context_tree(workspace, (tool_node,))

    assert '<node id="tools.tool.browser.observe" kind="tool_function"' in rendered
    assert 'display_name="Browser Observe"' in rendered
    assert "<summary>FULL_BROWSER_OBSERVE_DESCRIPTION</summary>" in rendered
