from __future__ import annotations

from crxzipple.app.integration.context_workspace_session import (
    SessionContextNodeProvider,
)
from crxzipple.modules.context_workspace.application import (
    ContextActionInput,
    ContextOwnerRegistry,
    ContextTreeService,
    ContextWorkspaceService,
    EnsureContextWorkspaceInput,
)
from crxzipple.modules.context_workspace.domain import ContextAction
from crxzipple.modules.context_workspace.infrastructure import (
    InMemoryContextNodeRepository,
    InMemoryContextOperationRepository,
    InMemoryContextWorkspaceRepository,
)
from crxzipple.modules.session.application import (
    AppendSessionMessageInput,
    ArchiveSessionMessagesInput,
    EnsureSessionInput,
    SessionApplicationService,
)
from crxzipple.modules.session.infrastructure import (
    InMemorySessionInstanceRepository,
    InMemorySessionMessageRepository,
    InMemorySessionRepository,
)


def test_session_adapter_populates_current_instance_and_recent_message_nodes() -> None:
    session_service = _session_service()
    session_service.ensure_session(
        EnsureSessionInput(
            key="session:tree",
            agent_id="assistant",
        ),
    )
    session_service.append_message(
        AppendSessionMessageInput(
            session_key="session:tree",
            role="user",
            content_payload={"blocks": [{"type": "text", "text": "hello tree"}]},
        ),
    )
    session_service.append_message(
        AppendSessionMessageInput(
            session_key="session:tree",
            role="assistant",
            content_payload={"blocks": [{"type": "text", "text": "tree received"}]},
        ),
    )
    services = _context_services(session_service)

    services["workspace"].ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:tree",
            agent_id="assistant",
        ),
    )
    tree = services["tree"].list_tree("session:tree")

    assert {node.id for node in tree.nodes} >= {
        "session.instance.current",
        "session.messages.recent",
    }
    recent_node = next(node for node in tree.nodes if node.id == "session.messages.recent")
    assert recent_node.owner_ref["from_sequence_no"] == 1
    assert recent_node.owner_ref["to_sequence_no"] == 2

    services["tree"].apply_action(
        ContextActionInput(
            session_key="session:tree",
            node_id="session.messages.recent",
            action=ContextAction.EXPAND,
        ),
    )
    expanded_tree = services["tree"].list_tree("session:tree")
    message_nodes = [
        node
        for node in expanded_tree.nodes
        if node.parent_id == "session.messages.recent"
    ]

    assert [node.owner_ref["sequence_no"] for node in message_nodes] == [1, 2]
    assert "hello tree" in message_nodes[0].summary


def test_session_adapter_exposes_older_message_chunks() -> None:
    session_service = _session_service()
    session_service.ensure_session(
        EnsureSessionInput(
            key="session:chunks",
            agent_id="assistant",
        ),
    )
    for index in range(1, 6):
        session_service.append_message(
            AppendSessionMessageInput(
                session_key="session:chunks",
                role="user",
                content_payload={
                    "blocks": [{"type": "text", "text": f"message {index}"}],
                },
            ),
        )
    services = _context_services(session_service, recent_limit=2)

    services["workspace"].ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:chunks",
            agent_id="assistant",
        ),
    )
    tree = services["tree"].list_tree("session:chunks")

    older_node = next(
        node for node in tree.nodes if node.id == "session.messages.older.before.4"
    )
    assert older_node.owner_ref["count"] == 3

    services["tree"].apply_action(
        ContextActionInput(
            session_key="session:chunks",
            node_id=older_node.id,
            action=ContextAction.EXPAND,
        ),
    )
    expanded_tree = services["tree"].list_tree("session:chunks")
    older_children = [
        node
        for node in expanded_tree.nodes
        if node.parent_id == "session.messages.older.before.4"
    ]

    assert older_children[0].id == "session.messages.older.before.2"
    assert [node.owner_ref.get("sequence_no") for node in older_children[1:]] == [
        2,
        3,
    ]


def test_session_adapter_exposes_folded_history_as_exact_archived_ranges() -> None:
    session_service = _session_service()
    session = session_service.ensure_session(
        EnsureSessionInput(
            key="session:folded",
            agent_id="assistant",
        ),
    )
    for index in range(1, 6):
        session_service.append_message(
            AppendSessionMessageInput(
                session_key="session:folded",
                role="user",
                content_payload={
                    "blocks": [{"type": "text", "text": f"archived message {index}"}],
                },
            ),
        )
    session_service.archive_messages(
        ArchiveSessionMessagesInput(
            session_key="session:folded",
            session_id=session.active_session_id,
            max_sequence_no=3,
            reason="test folded history",
        ),
    )
    services = _context_services(session_service, recent_limit=2)

    services["workspace"].ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:folded",
            agent_id="assistant",
        ),
    )
    tree = services["tree"].list_tree("session:folded")
    folded_node = next(node for node in tree.nodes if node.id == "session.history.folded")

    services["tree"].apply_action(
        ContextActionInput(
            session_key="session:folded",
            node_id=folded_node.id,
            action=ContextAction.EXPAND,
        ),
    )
    expanded_tree = services["tree"].list_tree("session:folded")
    range_nodes = [
        node for node in expanded_tree.nodes if node.parent_id == folded_node.id
    ]

    assert [node.owner_ref["from_sequence_no"] for node in range_nodes] == [1, 3]
    assert [node.owner_ref["to_sequence_no"] for node in range_nodes] == [2, 3]

    first_range = range_nodes[0]
    services["tree"].apply_action(
        ContextActionInput(
            session_key="session:folded",
            node_id=first_range.id,
            action=ContextAction.EXPAND,
        ),
    )
    message_tree = services["tree"].list_tree("session:folded")
    archived_message_nodes = [
        node for node in message_tree.nodes if node.parent_id == first_range.id
    ]

    assert [node.owner_ref["sequence_no"] for node in archived_message_nodes] == [1, 2]
    assert {
        node.owner_ref["visibility"] for node in archived_message_nodes
    } == {"archived"}


def _context_services(
    session_service: SessionApplicationService,
    *,
    recent_limit: int = 8,
):
    registry = ContextOwnerRegistry()
    registry.register(
        SessionContextNodeProvider(session_service, recent_limit=recent_limit),
    )
    workspaces = InMemoryContextWorkspaceRepository()
    nodes = InMemoryContextNodeRepository()
    operations = InMemoryContextOperationRepository()
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
    }


def _session_service() -> SessionApplicationService:
    uow = _FakeSessionUnitOfWork()
    return SessionApplicationService(lambda: uow)


class _FakeSessionUnitOfWork:
    def __init__(self) -> None:
        self.sessions = InMemorySessionRepository()
        self.session_messages = InMemorySessionMessageRepository()
        self.session_instances = InMemorySessionInstanceRepository()

    def __enter__(self) -> "_FakeSessionUnitOfWork":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # noqa: ANN001
        del exc_type, exc, tb

    def collect(self, aggregate) -> None:  # noqa: ANN001
        del aggregate

    def commit(self) -> None:
        return None

    def flush(self) -> None:
        return None

    def rollback(self) -> None:
        return None
