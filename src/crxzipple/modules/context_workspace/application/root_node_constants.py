from __future__ import annotations


CONTEXT_TREE_SCHEMA_VERSION = "2026-06-07.context_tree.v2"
CONTEXT_STATIC_GUIDE_REVISION = "2026-06-10.browser_relevance_and_history_guard.v1"
RUNTIME_ROOT_NODE_ID = "runtime"
TASK_ROOT_NODE_ID = "task"
SESSION_ROOT_NODE_ID = "session"
CAPABILITIES_ROOT_NODE_ID = "capabilities"
KNOWLEDGE_ROOT_NODE_ID = "knowledge"
RENDER_ROOT_NODE_ID = "render"
CONTEXT_INSTRUCTIONS_NODE_ID = "context.instructions"
EXECUTION_CURRENT_NODE_ID = "execution.current"
SESSION_CURRENT_NODE_ID = "session.current"

ROOT_SECTION_NODE_IDS = (
    RUNTIME_ROOT_NODE_ID,
    TASK_ROOT_NODE_ID,
    SESSION_ROOT_NODE_ID,
    CAPABILITIES_ROOT_NODE_ID,
    KNOWLEDGE_ROOT_NODE_ID,
    RENDER_ROOT_NODE_ID,
)

DEFAULT_PARENT_BY_NODE_ID = {
    CONTEXT_INSTRUCTIONS_NODE_ID: RUNTIME_ROOT_NODE_ID,
    EXECUTION_CURRENT_NODE_ID: RUNTIME_ROOT_NODE_ID,
    SESSION_CURRENT_NODE_ID: SESSION_ROOT_NODE_ID,
    "tools.available": CAPABILITIES_ROOT_NODE_ID,
    "skills.available": CAPABILITIES_ROOT_NODE_ID,
    "memory.visible": KNOWLEDGE_ROOT_NODE_ID,
    "artifacts.session": KNOWLEDGE_ROOT_NODE_ID,
    "workspace.resources": KNOWLEDGE_ROOT_NODE_ID,
    "runtime.contract": CONTEXT_INSTRUCTIONS_NODE_ID,
    "execution.guide": CONTEXT_INSTRUCTIONS_NODE_ID,
    "agent.identity": CONTEXT_INSTRUCTIONS_NODE_ID,
    "agent.home": CONTEXT_INSTRUCTIONS_NODE_ID,
    "context.priority": CONTEXT_INSTRUCTIONS_NODE_ID,
    "context.tree_usage": CONTEXT_INSTRUCTIONS_NODE_ID,
    "run.goal": TASK_ROOT_NODE_ID,
    "run.flow": EXECUTION_CURRENT_NODE_ID,
    "run.environment": EXECUTION_CURRENT_NODE_ID,
    "run.permissions": EXECUTION_CURRENT_NODE_ID,
    "run.provider": EXECUTION_CURRENT_NODE_ID,
    "run.context_budget": EXECUTION_CURRENT_NODE_ID,
    "run.constraints": EXECUTION_CURRENT_NODE_ID,
    "work.plan": TASK_ROOT_NODE_ID,
    "execution.continuation": EXECUTION_CURRENT_NODE_ID,
}
