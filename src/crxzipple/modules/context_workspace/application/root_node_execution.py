from __future__ import annotations

from crxzipple.modules.context_workspace.application.root_node_common import (
    context_block_payload,
    run_flow_payload,
    text_estimate,
)
from crxzipple.modules.context_workspace.application.root_node_constants import (
    CONTEXT_TREE_SCHEMA_VERSION,
    EXECUTION_CURRENT_NODE_ID,
    RUNTIME_ROOT_NODE_ID,
)
from crxzipple.modules.context_workspace.domain import (
    ContextAction,
    ContextNodeSeed,
    ContextNodeState,
)


def execution_current_node_seed(
    *,
    actions: tuple[ContextAction, ...],
) -> ContextNodeSeed:
    summary = (
        "Current run execution surface: goal, flow, environment, permissions, "
        "provider, context budget, constraints, plan, tool results, and "
        "continuation status."
    )
    return ContextNodeSeed(
        node_id=EXECUTION_CURRENT_NODE_ID,
        parent_id=RUNTIME_ROOT_NODE_ID,
        owner="orchestration",
        kind="execution_context",
        title="Current Execution",
        summary=summary,
        state=ContextNodeState(collapsed=False, loaded=True),
        actions=actions,
        owner_ref={"schema_version": CONTEXT_TREE_SCHEMA_VERSION},
        estimate=text_estimate(summary),
        display_order=10,
        metadata={
            "schema_version": CONTEXT_TREE_SCHEMA_VERSION,
            "section": "execution",
        },
    )


def run_flow_node_seed(metadata: dict[str, object] | None) -> ContextNodeSeed:
    payload = run_flow_payload(metadata)
    summary = payload["summary"]
    return ContextNodeSeed(
        node_id="run.flow",
        parent_id=EXECUTION_CURRENT_NODE_ID,
        owner="orchestration",
        kind="run_flow",
        title=payload["title"],
        summary=summary,
        state=ContextNodeState(collapsed=False, loaded=True),
        actions=(ContextAction.PIN, ContextAction.UNPIN, ContextAction.ESTIMATE),
        owner_ref={"mode": payload["mode"]},
        estimate=text_estimate(summary),
        display_order=15,
        metadata=payload["metadata"],
    )


def run_environment_node_seed(
    metadata: dict[str, object] | None,
    *,
    actions: tuple[ContextAction, ...],
) -> ContextNodeSeed:
    payload = context_block_payload(
        metadata,
        key="run_environment_node",
        default_summary="Current run environment, session binding, workspace, and lane.",
    )
    content = payload["content"]
    return ContextNodeSeed(
        node_id="run.environment",
        parent_id=EXECUTION_CURRENT_NODE_ID,
        owner="orchestration",
        kind="run_environment",
        title="Run Environment",
        summary=payload["summary"],
        content=content,
        state=ContextNodeState(collapsed=False, loaded=True),
        actions=actions,
        owner_ref=dict(payload["metadata"]),
        estimate=text_estimate(payload["summary"] + "\n" + content),
        display_order=16,
        metadata={"section": "execution", **dict(payload["metadata"])},
    )


def run_permissions_node_seed(
    metadata: dict[str, object] | None,
    *,
    actions: tuple[ContextAction, ...],
) -> ContextNodeSeed:
    payload = context_block_payload(
        metadata,
        key="run_permissions_node",
        default_summary="Authorization, access, tool visibility, and approval boundaries.",
    )
    content = payload["content"]
    return ContextNodeSeed(
        node_id="run.permissions",
        parent_id=EXECUTION_CURRENT_NODE_ID,
        owner="orchestration",
        kind="run_permissions",
        title="Run Permissions",
        summary=payload["summary"],
        content=content,
        state=ContextNodeState(collapsed=False, loaded=True),
        actions=actions,
        owner_ref=dict(payload["metadata"]),
        estimate=text_estimate(payload["summary"] + "\n" + content),
        display_order=17,
        metadata={"section": "execution", **dict(payload["metadata"])},
    )


def run_provider_node_seed(
    metadata: dict[str, object] | None,
    *,
    actions: tuple[ContextAction, ...],
) -> ContextNodeSeed:
    payload = context_block_payload(
        metadata,
        key="run_provider_node",
        default_summary="Current LLM provider profile, capabilities, and request surface.",
    )
    content = payload["content"]
    return ContextNodeSeed(
        node_id="run.provider",
        parent_id=EXECUTION_CURRENT_NODE_ID,
        owner="llm",
        kind="run_provider",
        title="Run Provider",
        summary=payload["summary"],
        content=content,
        state=ContextNodeState(collapsed=False, loaded=True),
        actions=actions,
        owner_ref=dict(payload["metadata"]),
        estimate=text_estimate(payload["summary"] + "\n" + content),
        display_order=18,
        metadata={"section": "execution", **dict(payload["metadata"])},
    )


def run_context_budget_node_seed(
    metadata: dict[str, object] | None,
    *,
    actions: tuple[ContextAction, ...],
) -> ContextNodeSeed:
    payload = context_block_payload(
        metadata,
        key="run_context_budget_node",
        default_summary="Runtime context budget for context blocks, transcript, tools, and attachments.",
    )
    content = payload["content"]
    return ContextNodeSeed(
        node_id="run.context_budget",
        parent_id=EXECUTION_CURRENT_NODE_ID,
        owner="context_workspace",
        kind="context_budget",
        title="Context Budget",
        summary=payload["summary"],
        content=content,
        state=ContextNodeState(collapsed=False, loaded=True),
        actions=actions,
        owner_ref=dict(payload["metadata"]),
        estimate=text_estimate(payload["summary"] + "\n" + content),
        display_order=19,
        metadata={"section": "execution", **dict(payload["metadata"])},
    )


def run_constraints_node_seed(
    metadata: dict[str, object] | None,
    *,
    actions: tuple[ContextAction, ...],
) -> ContextNodeSeed:
    payload = context_block_payload(
        metadata,
        key="run_constraints_node",
        default_summary="Current run hard constraints for tool use, evidence, and continuation.",
    )
    content = payload["content"]
    return ContextNodeSeed(
        node_id="run.constraints",
        parent_id=EXECUTION_CURRENT_NODE_ID,
        owner="orchestration",
        kind="run_constraints",
        title="Run Constraints",
        summary=payload["summary"],
        content=content,
        state=ContextNodeState(collapsed=False, loaded=True),
        actions=actions,
        owner_ref=dict(payload["metadata"]),
        estimate=text_estimate(payload["summary"] + "\n" + content),
        display_order=20,
        metadata={"section": "execution", **dict(payload["metadata"])},
    )


def execution_continuation_node_seed(
    metadata: dict[str, object] | None,
    *,
    actions: tuple[ContextAction, ...],
) -> ContextNodeSeed:
    payload = context_block_payload(
        metadata,
        key="execution_continuation_node",
        default_summary=(
            "Public continuation state for pending tools, approvals, and recovery."
        ),
    )
    content = payload["content"]
    node_metadata = {
        "section": "execution",
        **dict(payload["metadata"]),
    }
    return ContextNodeSeed(
        node_id="execution.continuation",
        parent_id=EXECUTION_CURRENT_NODE_ID,
        owner="orchestration",
        kind="continuation_state",
        title="Continuation State",
        summary=payload["summary"],
        content=content,
        state=ContextNodeState(collapsed=False, loaded=True),
        actions=actions,
        owner_ref=dict(node_metadata),
        estimate=text_estimate(payload["summary"] + "\n" + content),
        display_order=23,
        metadata=node_metadata,
    )
