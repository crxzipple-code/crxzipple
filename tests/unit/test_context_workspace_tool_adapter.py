from __future__ import annotations

from crxzipple.app.integration.context_workspace_tool import ToolContextNodeProvider
from crxzipple.modules.context_workspace.application import (
    ContextActionInput,
    ContextRenderService,
    ContextOwnerRegistry,
    ContextTreeService,
    ContextWorkspaceService,
    EnsureContextWorkspaceInput,
    RenderContextPromptInput,
)
from crxzipple.modules.context_workspace.domain import ContextAction
from crxzipple.modules.context_workspace.infrastructure import (
    InMemoryContextNodeRepository,
    InMemoryContextOperationRepository,
    InMemoryContextRenderSnapshotRepository,
    InMemoryContextWorkspaceRepository,
)
from crxzipple.modules.tool.domain import Tool, ToolNotFoundError, ToolParameter


def test_tool_adapter_expands_only_prompt_surface_tool_nodes() -> None:
    tool_service = _FakeToolService(
        Tool(
            id="fetch_weather",
            name="Fetch Weather",
            description="Fetch current weather for a location.",
            parameters=(
                ToolParameter(
                    name="location",
                    description="Location to query.",
                    data_type="string",
                    required=True,
                ),
            ),
            required_effect_ids=("network_fetch",),
        ),
        Tool(
            id="web_search",
            name="Web Search",
            description="Search the web.",
        ),
    )
    services = _context_services(tool_service)

    services["workspace"].ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:tools",
            agent_id="assistant",
            metadata={"available_tool_names": ["fetch_weather"]},
        ),
    )
    services["tree"].apply_action(
        ContextActionInput(
            session_key="session:tools",
            node_id="tools.available",
            action=ContextAction.EXPAND,
        ),
    )
    tree = services["tree"].list_tree("session:tools")
    tool_nodes = [node for node in tree.nodes if node.parent_id == "tools.available"]

    assert [node.id for node in tool_nodes] == ["tools.tool.fetch_weather"]
    assert tool_nodes[0].state.schema_enabled is True
    assert "location" in tool_nodes[0].summary
    assert tool_nodes[0].metadata["required_effect_ids"] == ["network_fetch"]
    assert tool_nodes[0].metadata["provider_schema"]["name"] == "fetch_weather"


def test_tool_schema_mirror_follows_context_node_state() -> None:
    services = _context_services(
        _FakeToolService(
            Tool(
                id="fetch_weather",
                name="Fetch Weather",
                description="Fetch current weather for a location.",
                parameters=(
                    ToolParameter(
                        name="location",
                        description="Location to query.",
                        data_type="string",
                        required=True,
                    ),
                ),
            ),
        ),
    )
    services["workspace"].ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:tools",
            agent_id="assistant",
            metadata={"available_tool_names": ["fetch_weather"]},
        ),
    )
    services["tree"].apply_action(
        ContextActionInput(
            session_key="session:tools",
            node_id="tools.available",
            action=ContextAction.EXPAND,
        ),
    )

    rendered = services["render"].render_prompt_body(
        RenderContextPromptInput(session_key="session:tools"),
    )

    assert rendered.mirrored_node_ids == ("tools.tool.fetch_weather",)
    assert rendered.provider_attachments["tool_schemas"][0]["name"] == "fetch_weather"

    services["tree"].apply_action(
        ContextActionInput(
            session_key="session:tools",
            node_id="tools.tool.fetch_weather",
            action=ContextAction.DISABLE_TOOL_SCHEMA,
        ),
    )
    rendered_after_disable = services["render"].render_prompt_body(
        RenderContextPromptInput(session_key="session:tools"),
    )

    assert rendered_after_disable.mirrored_node_ids == ()
    assert "tool_schemas" not in rendered_after_disable.provider_attachments


def test_owner_refresh_preserves_tool_schema_toggle_state() -> None:
    services = _context_services(
        _FakeToolService(
            Tool(
                id="fetch_weather",
                name="Fetch Weather",
                description="Fetch current weather for a location.",
            ),
        ),
    )
    services["workspace"].ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:tools",
            agent_id="assistant",
            metadata={"available_tool_names": ["fetch_weather"]},
        ),
    )
    services["tree"].apply_action(
        ContextActionInput(
            session_key="session:tools",
            node_id="tools.available",
            action=ContextAction.EXPAND,
        ),
    )
    services["tree"].apply_action(
        ContextActionInput(
            session_key="session:tools",
            node_id="tools.tool.fetch_weather",
            action=ContextAction.DISABLE_TOOL_SCHEMA,
        ),
    )

    services["workspace"].ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:tools",
            agent_id="assistant",
            metadata={"available_tool_names": ["fetch_weather"]},
        ),
    )
    rendered = services["render"].render_prompt_body(
        RenderContextPromptInput(session_key="session:tools"),
    )

    assert rendered.mirrored_node_ids == ()
    assert "tool_schemas" not in rendered.provider_attachments


def test_tool_adapter_keeps_tools_collapsed_without_resolved_surface() -> None:
    services = _context_services(_FakeToolService())

    services["workspace"].ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:tools",
            agent_id="assistant",
        ),
    )
    services["tree"].apply_action(
        ContextActionInput(
            session_key="session:tools",
            node_id="tools.available",
            action=ContextAction.EXPAND,
        ),
    )
    tree = services["tree"].list_tree("session:tools")

    assert [node for node in tree.nodes if node.parent_id == "tools.available"] == []


def _context_services(tool_service: "_FakeToolService"):
    registry = ContextOwnerRegistry()
    registry.register(ToolContextNodeProvider(tool_service))
    workspaces = InMemoryContextWorkspaceRepository()
    nodes = InMemoryContextNodeRepository()
    operations = InMemoryContextOperationRepository()
    snapshots = InMemoryContextRenderSnapshotRepository()
    return {
        "workspace": ContextWorkspaceService(
            workspace_repository=workspaces,
            node_repository=nodes,
            owner_registry=registry,
        ),
        "tree": ContextTreeService(
            workspace_repository=workspaces,
            node_repository=nodes,
            operation_repository=operations,
            owner_registry=registry,
        ),
        "render": ContextRenderService(
            workspace_repository=workspaces,
            node_repository=nodes,
            snapshot_repository=snapshots,
        ),
    }


class _FakeToolService:
    def __init__(self, *tools: Tool) -> None:
        self._tools = {tool.id: tool for tool in tools}

    def get_tool(self, tool_id: str) -> Tool:
        tool = self._tools.get(tool_id)
        if tool is None:
            raise ToolNotFoundError(f"Tool '{tool_id}' does not exist.")
        return tool
