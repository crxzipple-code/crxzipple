from __future__ import annotations

from crxzipple.modules.context_workspace.application.root_node_common import (
    optional_text,
)
from crxzipple.modules.context_workspace.application.root_node_constants import (
    CAPABILITIES_ROOT_NODE_ID,
    KNOWLEDGE_ROOT_NODE_ID,
    SESSION_CURRENT_NODE_ID,
    SESSION_ROOT_NODE_ID,
)
from crxzipple.modules.context_workspace.domain import (
    ContextAction,
    ContextEstimate,
    ContextNodeSeed,
    ContextNodeState,
)


def session_and_resource_node_seeds(
    *,
    session_key: str,
    agent_id: str,
    metadata: dict[str, object] | None,
    actions: tuple[ContextAction, ...],
) -> tuple[ContextNodeSeed, ...]:
    seeds: list[ContextNodeSeed] = [
        _session_current_node_seed(session_key=session_key, actions=actions),
        _tools_available_node_seed(
            session_key=session_key,
            agent_id=agent_id,
            actions=actions,
        ),
        _skills_available_node_seed(agent_id=agent_id, actions=actions),
        _memory_visible_node_seed(
            session_key=session_key,
            agent_id=agent_id,
            actions=actions,
        ),
        _session_artifacts_node_seed(session_key=session_key, actions=actions),
    ]
    if optional_text((metadata or {}).get("workspace_dir")) is not None:
        seeds.append(
            _workspace_resources_node_seed(
                session_key=session_key,
                agent_id=agent_id,
                actions=actions,
            ),
        )
    return tuple(seeds)


def _session_current_node_seed(
    *,
    session_key: str,
    actions: tuple[ContextAction, ...],
) -> ContextNodeSeed:
    return ContextNodeSeed(
        node_id=SESSION_CURRENT_NODE_ID,
        parent_id=SESSION_ROOT_NODE_ID,
        owner="session",
        kind="session",
        title="Current Session",
        summary=f"Active context handles for session '{session_key}'.",
        state=ContextNodeState(collapsed=False, loaded=True),
        actions=actions,
        owner_ref={"session_key": session_key},
        estimate=ContextEstimate(text_chars=96, text_tokens=24),
        display_order=20,
    )


def _tools_available_node_seed(
    *,
    session_key: str,
    agent_id: str,
    actions: tuple[ContextAction, ...],
) -> ContextNodeSeed:
    return ContextNodeSeed(
        node_id="tools.available",
        parent_id=CAPABILITIES_ROOT_NODE_ID,
        owner="tool",
        kind="tool_bundle_root",
        title="Available Tools",
        summary=(
            "Authorized tool handles are actionable capability groups. Expand "
            "relevant collapsed bundles before concluding a needed tool is "
            "unavailable; expanded tool functions can be mirrored as provider "
            "schemas."
        ),
        state=ContextNodeState(collapsed=False, loaded=True),
        actions=actions,
        owner_ref={"agent_id": agent_id, "session_key": session_key},
        estimate=ContextEstimate(text_chars=240, text_tokens=60),
        display_order=30,
    )


def _skills_available_node_seed(
    *,
    agent_id: str,
    actions: tuple[ContextAction, ...],
) -> ContextNodeSeed:
    return ContextNodeSeed(
        node_id="skills.available",
        parent_id=CAPABILITIES_ROOT_NODE_ID,
        owner="skills",
        kind="skill_group",
        title="Available Skills",
        summary=(
            "Ready skill handles can be expanded for guidance; use skill_read "
            "for full skill files."
        ),
        actions=actions,
        owner_ref={"agent_id": agent_id},
        estimate=ContextEstimate(text_chars=96, text_tokens=24),
        display_order=40,
    )


def _memory_visible_node_seed(
    *,
    session_key: str,
    agent_id: str,
    actions: tuple[ContextAction, ...],
) -> ContextNodeSeed:
    return ContextNodeSeed(
        node_id="memory.visible",
        parent_id=KNOWLEDGE_ROOT_NODE_ID,
        owner="memory",
        kind="memory_scope_group",
        title="Visible Memory",
        summary="Memory scopes visible to the current agent and session.",
        actions=actions,
        owner_ref={"agent_id": agent_id, "session_key": session_key},
        estimate=ContextEstimate(text_chars=96, text_tokens=24),
        display_order=50,
    )


def _session_artifacts_node_seed(
    *,
    session_key: str,
    actions: tuple[ContextAction, ...],
) -> ContextNodeSeed:
    return ContextNodeSeed(
        node_id="artifacts.session",
        parent_id=KNOWLEDGE_ROOT_NODE_ID,
        owner="artifacts",
        kind="artifact_group",
        title="Session Artifacts",
        summary=(
            "Artifacts referenced by the session; pin an artifact handle to mirror "
            "it into provider attachments."
        ),
        actions=actions,
        owner_ref={"session_key": session_key},
        estimate=ContextEstimate(text_chars=96, text_tokens=24),
        display_order=60,
    )


def _workspace_resources_node_seed(
    *,
    session_key: str,
    agent_id: str,
    actions: tuple[ContextAction, ...],
) -> ContextNodeSeed:
    return ContextNodeSeed(
        node_id="workspace.resources",
        parent_id=KNOWLEDGE_ROOT_NODE_ID,
        owner="workspace",
        kind="workspace_resource_group",
        title="Workspace Resources",
        summary=(
            "Optional task workspace file handles. This is not a universal "
            "instruction layer; use it only when the session is bound to a "
            "workspace directory."
        ),
        actions=actions,
        owner_ref={"agent_id": agent_id, "session_key": session_key},
        estimate=ContextEstimate(text_chars=96, text_tokens=24),
        display_order=70,
    )
