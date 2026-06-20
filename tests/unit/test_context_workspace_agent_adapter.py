from __future__ import annotations

from dataclasses import dataclass

from crxzipple.app.integration.context_workspace_agent import (
    AgentHomeContextNodeProvider,
)
from crxzipple.modules.agent.domain.exceptions import AgentNotFoundError
from crxzipple.modules.context_workspace.application import (
    CONTEXT_INSTRUCTIONS_NODE_ID,
    ContextSliceBuilderService,
    ContextActionInput,
    ContextOwnerRegistry,
    ContextObservationSnapshotService,
    ContextTreeService,
    ContextWorkspaceService,
    EnsureContextWorkspaceInput,
    ContextObservationRenderInput,
)
from crxzipple.modules.context_workspace.domain import ContextAction
from crxzipple.modules.context_workspace.infrastructure import (
    InMemoryContextNodeRepository,
    InMemoryContextOperationRepository,
    InMemoryContextSnapshotRepository,
    InMemoryContextWorkspaceRepository,
)


def test_agent_home_provider_mounts_home_files_as_agent_nodes() -> None:
    services = _context_services(
        _AgentHomeService(
            _Snapshot(
                files=(
                    _File("AGENT.md", True, "# Role\n\nBuild the thing."),
                    _File("SOUL.md", True, "Calm, direct voice."),
                    _File("USER.md", True, "Prefers concise updates."),
                    _File("IDENTITY.md", True, "Codex local runtime."),
                ),
            ),
        ),
    )

    services["workspace"].ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:agent-home",
            agent_id="assistant",
        ),
    )
    tree = services["tree"].list_tree("session:agent-home")
    nodes = {node.id: node for node in tree.nodes}

    assert nodes["agent.home"].parent_id == CONTEXT_INSTRUCTIONS_NODE_ID
    assert nodes["agent.home"].owner == "agent"
    assert [
        node.id
        for node in tree.nodes
        if node.parent_id == "agent.home"
    ] == [
        "agent.home.AGENT.md",
        "agent.home.SOUL.md",
        "agent.home.USER.md",
        "agent.home.IDENTITY.md",
    ]
    assert nodes["agent.home.AGENT.md"].metadata["role"] == "agent_instructions"
    assert nodes["agent.home.SOUL.md"].metadata["role"] == "style"
    assert nodes["agent.home.USER.md"].metadata["role"] == "user_preferences"
    assert nodes["agent.home.IDENTITY.md"].metadata["role"] == "identity"
    assert not nodes["agent.home.AGENT.md"].state.collapsed
    assert nodes["agent.home.USER.md"].state.collapsed
    assert nodes["agent.home.USER.md"].content == ""
    assert nodes["agent.home.USER.md"].summary == "Prefers concise updates."


def test_agent_home_provider_skips_missing_profile_home() -> None:
    services = _context_services(_AgentHomeService(error=AgentNotFoundError()))

    services["workspace"].ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:missing-profile",
            agent_id="missing",
        ),
    )
    tree = services["tree"].list_tree("session:missing-profile")

    assert "agent.home" in {node.id for node in tree.nodes}
    assert [node for node in tree.nodes if node.parent_id == "agent.home"] == []


def test_agent_home_provider_skips_missing_files() -> None:
    services = _context_services(
        _AgentHomeService(
            _Snapshot(
                files=(
                    _File("AGENT.md", False, ""),
                    _File("SOUL.md", True, "Still available."),
                    _File("USER.md", True, "   "),
                    _File("IDENTITY.md", False, ""),
                ),
            ),
        ),
    )

    services["workspace"].ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:missing-files",
            agent_id="assistant",
        ),
    )
    tree = services["tree"].list_tree("session:missing-files")

    assert [
        node.id
        for node in tree.nodes
        if node.parent_id == "agent.home"
    ] == ["agent.home.SOUL.md"]


def test_agent_home_provider_truncates_oversized_home_file() -> None:
    services = _context_services(
        _AgentHomeService(
            _Snapshot(files=(_File("AGENT.md", True, "a" * 20_050),)),
        ),
    )

    services["workspace"].ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:oversized-home",
            agent_id="assistant",
        ),
    )
    tree = services["tree"].list_tree("session:oversized-home")
    node = next(item for item in tree.nodes if item.id == "agent.home.AGENT.md")

    assert node.content == ""
    assert node.metadata["content_chars"] == 20_000
    assert node.metadata["truncated"] is True


def test_agent_home_collapsed_files_show_summary_until_expanded() -> None:
    services = _context_services(
        _AgentHomeService(
            _Snapshot(
                files=(
                    _File("AGENT.md", True, "Core role instructions."),
                    _File("USER.md", True, "Stable user preference details."),
                ),
            ),
        ),
    )

    services["workspace"].ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:render-home",
            agent_id="assistant",
        ),
    )
    prompt = services["render"].render_observation(
        ContextObservationRenderInput(session_key="session:render-home"),
    ).debug_body

    assert "<summary>Stable user preference details.</summary>" in prompt
    assert "<content>Stable user preference details.</content>" not in prompt
    assert "<content>Core role instructions.</content>" not in prompt

    services["tree"].apply_action(
        ContextActionInput(
            session_key="session:render-home",
            node_id="agent.home.USER.md",
            action=ContextAction.EXPAND,
        ),
    )
    expanded_prompt = services["render"].render_observation(
        ContextObservationRenderInput(session_key="session:render-home"),
    ).debug_body

    assert "<content>Stable user preference details.</content>" not in expanded_prompt
    assert "<summary>Stable user preference details.</summary>" in expanded_prompt


def test_agent_home_slice_is_handle_only_without_file_body() -> None:
    services = _context_services(
        _AgentHomeService(
            _Snapshot(
                files=(
                    _File("AGENT.md", True, "Core role instructions."),
                ),
            ),
        ),
    )

    services["workspace"].ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:slice-home",
            agent_id="assistant",
        ),
    )
    services["tree"].apply_action(
        ContextActionInput(
            session_key="session:slice-home",
            node_id="agent.home.AGENT.md",
            action=ContextAction.EXPAND,
        ),
    )
    context_slice = services["slice"].build_slice(
        session_key="session:slice-home",
        run_id="run-home",
        audience="trace_timeline",
    )

    item = next(
        item for item in context_slice.items if item.item_id == "agent.home.AGENT.md"
    )
    assert item.text == ""
    assert item.content is None
    assert item.summary == "Core role instructions."
    assert item.metadata["owner_resolution"] == "handle_only"


@dataclass(frozen=True, slots=True)
class _File:
    name: str
    exists: bool
    content: str
    path: str = "/agent/home/file.md"
    language: str = "markdown"


@dataclass(frozen=True, slots=True)
class _Snapshot:
    files: tuple[_File, ...]
    home_dir: str = "/agent/home"
    workdir: str | None = None


class _AgentHomeService:
    def __init__(
        self,
        snapshot: _Snapshot | None = None,
        *,
        error: Exception | None = None,
    ) -> None:
        self._snapshot = snapshot
        self._error = error

    def inspect_profile_home(self, profile_id: str) -> _Snapshot:
        if self._error is not None:
            raise self._error
        assert profile_id
        assert self._snapshot is not None
        return self._snapshot


def _context_services(agent_service: _AgentHomeService):
    registry = ContextOwnerRegistry()
    registry.register(AgentHomeContextNodeProvider(agent_service))
    workspaces = InMemoryContextWorkspaceRepository()
    nodes = InMemoryContextNodeRepository()
    operations = InMemoryContextOperationRepository()
    snapshots = InMemoryContextSnapshotRepository()
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
        "render": ContextObservationSnapshotService(
            workspace_repository=workspaces,
            node_repository=nodes,
            snapshot_repository=snapshots,
        ),
        "slice": ContextSliceBuilderService(
            workspace_repository=workspaces,
            node_repository=nodes,
        ),
    }
