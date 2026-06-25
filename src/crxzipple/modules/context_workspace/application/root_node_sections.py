from __future__ import annotations

from crxzipple.modules.context_workspace.application.root_node_constants import (
    CAPABILITIES_ROOT_NODE_ID,
    CONTEXT_TREE_SCHEMA_VERSION,
    KNOWLEDGE_ROOT_NODE_ID,
    RENDER_ROOT_NODE_ID,
    RUNTIME_ROOT_NODE_ID,
    SESSION_ROOT_NODE_ID,
    TASK_ROOT_NODE_ID,
)
from crxzipple.modules.context_workspace.application.root_node_common import (
    text_estimate,
)
from crxzipple.modules.context_workspace.domain import (
    ContextAction,
    ContextNodeSeed,
    ContextNodeState,
)


def section_root_node_seeds(
    *,
    actions: tuple[ContextAction, ...],
) -> tuple[ContextNodeSeed, ...]:
    return (
        _section_root_node_seed(
            node_id=RUNTIME_ROOT_NODE_ID,
            owner="context_workspace",
            kind="runtime_root",
            title="Runtime",
            summary=(
                "Runtime contract, environment, execution state, provider state, "
                "permissions, budget, and continuation controls."
            ),
            display_order=0,
            actions=actions,
        ),
        _section_root_node_seed(
            node_id=TASK_ROOT_NODE_ID,
            owner="context_workspace",
            kind="task_root",
            title="Task",
            summary="Current user goal, task state, working plan, and task progress.",
            display_order=10,
            actions=actions,
        ),
        _section_root_node_seed(
            node_id=SESSION_ROOT_NODE_ID,
            owner="context_workspace",
            kind="session_root",
            title="Session",
            summary="Current session, visible turns, steps, and response items.",
            display_order=20,
            actions=actions,
        ),
        _section_root_node_seed(
            node_id=CAPABILITIES_ROOT_NODE_ID,
            owner="context_workspace",
            kind="capabilities_root",
            title="Capabilities",
            summary=(
                "Visible tools, loaded tools, skills, model capabilities, and "
                "provider-callable active surface."
            ),
            display_order=30,
            actions=actions,
        ),
        _section_root_node_seed(
            node_id=KNOWLEDGE_ROOT_NODE_ID,
            owner="context_workspace",
            kind="knowledge_root",
            title="Knowledge",
            summary="Memory, workspace resources, artifacts, and opened knowledge handles.",
            display_order=40,
            actions=actions,
        ),
        _section_root_node_seed(
            node_id=RENDER_ROOT_NODE_ID,
            owner="context_workspace",
            kind="render_root",
            title="Render",
            summary=(
                "Current context slice, provider payload mapping, omitted items, "
                "and render budget reports."
            ),
            display_order=50,
            actions=actions,
        ),
    )


def _section_root_node_seed(
    *,
    node_id: str,
    owner: str,
    kind: str,
    title: str,
    summary: str,
    display_order: int,
    actions: tuple[ContextAction, ...],
) -> ContextNodeSeed:
    return ContextNodeSeed(
        node_id=node_id,
        owner=owner,
        kind=kind,
        title=title,
        summary=summary,
        state=ContextNodeState(collapsed=False, loaded=True),
        actions=actions,
        owner_ref={"schema_version": CONTEXT_TREE_SCHEMA_VERSION},
        estimate=text_estimate(summary),
        display_order=display_order,
        metadata={
            "schema_version": CONTEXT_TREE_SCHEMA_VERSION,
            "section": node_id,
        },
    )
