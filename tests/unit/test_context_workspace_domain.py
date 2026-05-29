from __future__ import annotations

import pytest

from crxzipple.modules.context_workspace.domain import (
    ContextEstimate,
    ContextNodeSeed,
    ContextNodeState,
    ContextWorkspace,
    ContextWorkspaceValidationError,
)


def test_workspace_requires_session_and_agent_identity() -> None:
    with pytest.raises(ContextWorkspaceValidationError):
        ContextWorkspace.new(session_key="", agent_id="assistant")

    with pytest.raises(ContextWorkspaceValidationError):
        ContextWorkspace.new(session_key="session:test", agent_id="")


def test_workspace_revision_increments() -> None:
    workspace = ContextWorkspace.new(
        session_key="session:test",
        agent_id="assistant",
    )

    assert workspace.active_revision == 1

    next_revision = workspace.touch_revision()

    assert next_revision == 2
    assert workspace.active_revision == 2


def test_node_state_round_trips_and_estimate_aggregates() -> None:
    state = ContextNodeState(collapsed=True).expand().with_updates(pinned=True)

    assert ContextNodeState.from_payload(state.to_payload()) == state
    assert not state.collapsed
    assert state.loaded
    assert state.pinned

    estimate = ContextEstimate(text_tokens=2, image_count=1).plus(
        ContextEstimate(text_tokens=3, file_tokens=5),
    )

    assert estimate.text_tokens == 5
    assert estimate.image_count == 1
    assert estimate.file_tokens == 5


def test_node_seed_rejects_blank_identity() -> None:
    with pytest.raises(ContextWorkspaceValidationError):
        ContextNodeSeed(
            node_id="",
            owner="session",
            kind="session",
            title="Session",
        )
