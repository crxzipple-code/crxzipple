from __future__ import annotations

from crxzipple.modules.context_workspace.application.root_node_common import (
    context_block_payload,
    text_estimate,
)
from crxzipple.modules.context_workspace.application.root_node_constants import (
    TASK_ROOT_NODE_ID,
)
from crxzipple.modules.context_workspace.domain import (
    ContextAction,
    ContextNodeSeed,
    ContextNodeState,
)


def run_goal_node_seed(
    metadata: dict[str, object] | None,
    *,
    actions: tuple[ContextAction, ...],
) -> ContextNodeSeed:
    payload = context_block_payload(
        metadata,
        key="run_goal_node",
        default_summary="Current run goal derived from the latest inbound instruction.",
    )
    content = payload["content"]
    return ContextNodeSeed(
        node_id="run.goal",
        parent_id=TASK_ROOT_NODE_ID,
        owner="orchestration",
        kind="run_goal",
        title="Run Goal",
        summary=payload["summary"],
        content=content,
        state=ContextNodeState(collapsed=False, loaded=True),
        actions=actions,
        owner_ref=dict(payload["metadata"]),
        estimate=text_estimate(payload["summary"] + "\n" + content),
        display_order=14,
        metadata={"section": "execution", **dict(payload["metadata"])},
    )


def working_plan_node_seed(
    *,
    actions: tuple[ContextAction, ...],
) -> ContextNodeSeed:
    summary = (
        "Visible engineering working plan for the current task. Use "
        "context_tree.update_plan to record the current goal, public progress, "
        "observed facts, assumptions, uncertainty, and blockers."
    )
    content = "No active working plan has been recorded yet."
    return ContextNodeSeed(
        node_id="work.plan",
        parent_id=TASK_ROOT_NODE_ID,
        owner="context_workspace",
        kind="working_plan",
        title="Working Plan",
        summary=summary,
        content=content,
        state=ContextNodeState(collapsed=False, loaded=True),
        actions=actions,
        owner_ref={"plan_state": "empty"},
        estimate=text_estimate(f"{summary}\n{content}"),
        display_order=21,
        metadata={
            "plan_state": "empty",
            "managed_by": "context_workspace",
            "public_plan": True,
        },
    )
