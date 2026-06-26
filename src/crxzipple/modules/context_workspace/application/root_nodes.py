from __future__ import annotations

from crxzipple.modules.context_workspace.application.root_node_constants import (
    CAPABILITIES_ROOT_NODE_ID,
    CONTEXT_INSTRUCTIONS_NODE_ID,
    CONTEXT_STATIC_GUIDE_REVISION,
    CONTEXT_TREE_SCHEMA_VERSION,
    DEFAULT_PARENT_BY_NODE_ID,
    EXECUTION_CURRENT_NODE_ID,
    KNOWLEDGE_ROOT_NODE_ID,
    RENDER_ROOT_NODE_ID,
    ROOT_SECTION_NODE_IDS,
    RUNTIME_ROOT_NODE_ID,
    SESSION_CURRENT_NODE_ID,
    SESSION_ROOT_NODE_ID,
    TASK_ROOT_NODE_ID,
)
from crxzipple.modules.context_workspace.application.root_node_execution import (
    execution_continuation_node_seed as _execution_continuation_node_seed,
    execution_current_node_seed as _execution_current_node_seed,
    run_constraints_node_seed as _run_constraints_node_seed,
    run_context_budget_node_seed as _run_context_budget_node_seed,
    run_environment_node_seed as _run_environment_node_seed,
    run_flow_node_seed as _run_flow_node_seed,
    run_permissions_node_seed as _run_permissions_node_seed,
    run_provider_node_seed as _run_provider_node_seed,
)
from crxzipple.modules.context_workspace.application.root_node_instructions import (
    instruction_node_seeds,
)
from crxzipple.modules.context_workspace.application.root_node_resources import (
    session_and_resource_node_seeds,
)
from crxzipple.modules.context_workspace.application.root_node_sections import (
    section_root_node_seeds,
)
from crxzipple.modules.context_workspace.application.root_node_task import (
    run_goal_node_seed as _run_goal_node_seed,
    working_plan_node_seed as _working_plan_node_seed,
)
from crxzipple.modules.context_workspace.domain import (
    ContextAction,
    ContextNodeSeed,
)


def default_root_node_seeds(
    *,
    session_key: str,
    agent_id: str,
    metadata: dict[str, object] | None = None,
) -> tuple[ContextNodeSeed, ...]:
    common_actions = (
        ContextAction.EXPAND,
        ContextAction.COLLAPSE,
        ContextAction.PIN,
        ContextAction.UNPIN,
        ContextAction.ESTIMATE,
    )
    seeds: list[ContextNodeSeed] = [
        *section_root_node_seeds(actions=common_actions),
        *instruction_node_seeds(
            agent_id=agent_id,
            metadata=metadata,
            actions=common_actions,
        ),
        _execution_current_node_seed(actions=common_actions),
        _run_flow_node_seed(metadata),
        _run_goal_node_seed(
            metadata,
            actions=common_actions,
        ),
        _run_environment_node_seed(
            metadata,
            actions=common_actions,
        ),
        _run_permissions_node_seed(
            metadata,
            actions=common_actions,
        ),
        _run_provider_node_seed(
            metadata,
            actions=common_actions,
        ),
        _run_context_budget_node_seed(
            metadata,
            actions=common_actions,
        ),
        _run_constraints_node_seed(
            metadata,
            actions=common_actions,
        ),
        _working_plan_node_seed(actions=common_actions),
        _execution_continuation_node_seed(
            metadata,
            actions=common_actions,
        ),
        *session_and_resource_node_seeds(
            session_key=session_key,
            agent_id=agent_id,
            metadata=metadata,
            actions=common_actions,
        ),
    ]
    return tuple(seeds)


def default_parent_id_for_node_id(node_id: str) -> str | None:
    return DEFAULT_PARENT_BY_NODE_ID.get(node_id)


__all__ = [
    "CAPABILITIES_ROOT_NODE_ID",
    "CONTEXT_INSTRUCTIONS_NODE_ID",
    "CONTEXT_STATIC_GUIDE_REVISION",
    "CONTEXT_TREE_SCHEMA_VERSION",
    "DEFAULT_PARENT_BY_NODE_ID",
    "EXECUTION_CURRENT_NODE_ID",
    "KNOWLEDGE_ROOT_NODE_ID",
    "RENDER_ROOT_NODE_ID",
    "ROOT_SECTION_NODE_IDS",
    "RUNTIME_ROOT_NODE_ID",
    "SESSION_CURRENT_NODE_ID",
    "SESSION_ROOT_NODE_ID",
    "TASK_ROOT_NODE_ID",
    "default_parent_id_for_node_id",
    "default_root_node_seeds",
]
