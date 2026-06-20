from __future__ import annotations

from crxzipple.modules.context_workspace.application import root_nodes


def test_default_root_node_seeds_group_runtime_agent_execution_and_session_roots() -> None:
    seeds = root_nodes.default_root_node_seeds(
        session_key="session:root",
        agent_id="assistant",
        metadata={},
    )
    by_id = {seed.node_id: seed for seed in seeds}

    assert tuple(seed.node_id for seed in seeds if seed.parent_id is None) == (
        root_nodes.RUNTIME_ROOT_NODE_ID,
        root_nodes.TASK_ROOT_NODE_ID,
        root_nodes.SESSION_ROOT_NODE_ID,
        root_nodes.CAPABILITIES_ROOT_NODE_ID,
        root_nodes.KNOWLEDGE_ROOT_NODE_ID,
        root_nodes.RENDER_ROOT_NODE_ID,
    )
    assert by_id[root_nodes.CONTEXT_INSTRUCTIONS_NODE_ID].parent_id == (
        root_nodes.RUNTIME_ROOT_NODE_ID
    )
    assert by_id[root_nodes.EXECUTION_CURRENT_NODE_ID].parent_id == (
        root_nodes.RUNTIME_ROOT_NODE_ID
    )
    assert by_id[root_nodes.SESSION_CURRENT_NODE_ID].parent_id == (
        root_nodes.SESSION_ROOT_NODE_ID
    )
    assert by_id["tools.available"].parent_id == root_nodes.CAPABILITIES_ROOT_NODE_ID
    assert by_id["skills.available"].parent_id == root_nodes.CAPABILITIES_ROOT_NODE_ID
    assert by_id["memory.visible"].parent_id == root_nodes.KNOWLEDGE_ROOT_NODE_ID
    assert by_id["artifacts.session"].parent_id == root_nodes.KNOWLEDGE_ROOT_NODE_ID
    assert by_id["runtime.contract"].parent_id == (
        root_nodes.CONTEXT_INSTRUCTIONS_NODE_ID
    )
    assert by_id["agent.identity"].parent_id == root_nodes.CONTEXT_INSTRUCTIONS_NODE_ID
    assert by_id["run.flow"].parent_id == root_nodes.EXECUTION_CURRENT_NODE_ID
    assert by_id["run.goal"].parent_id == root_nodes.TASK_ROOT_NODE_ID
    assert by_id["run.environment"].parent_id == root_nodes.EXECUTION_CURRENT_NODE_ID
    assert by_id["run.permissions"].parent_id == root_nodes.EXECUTION_CURRENT_NODE_ID
    assert by_id["run.provider"].parent_id == root_nodes.EXECUTION_CURRENT_NODE_ID
    assert by_id["run.context_budget"].parent_id == root_nodes.EXECUTION_CURRENT_NODE_ID
    assert by_id["run.constraints"].parent_id == root_nodes.EXECUTION_CURRENT_NODE_ID
    assert "evidence.frontier" not in by_id
    assert by_id["execution.continuation"].parent_id == (
        root_nodes.EXECUTION_CURRENT_NODE_ID
    )
    runtime_contract = by_id["runtime.contract"]
    assert runtime_contract.metadata["contract_version"] == "2026-06-10"
    assert "rg --files" in runtime_contract.content
    assert "exec" in runtime_contract.content
    assert "process" in runtime_contract.content
    assert "Do not substitute search snippets" in runtime_contract.content
    assert "repeated tool calls return no new facts" in runtime_contract.content
    assert "script.extract_request" not in runtime_contract.content
    assert "Playwright" not in runtime_contract.content
    assert "CDP" not in runtime_contract.content
    assert "browser.evaluate" not in runtime_contract.content
    execution_guide = by_id["execution.guide"]
    assert "Treat search/list tools as indexes" in execution_guide.content
    assert "validate that candidate" in execution_guide.content
    assert "browser runtime" not in execution_guide.content
    assert "runtime_and_code" not in execution_guide.content
    assert "network_truth" not in execution_guide.content
    assert "capability.search" in by_id["context.tree_usage"].content
    assert "context_tree.render_current" not in by_id["context.tree_usage"].content
    assert "workspace.resources" not in by_id


def test_default_root_node_seeds_add_workspace_resource_root_when_bound() -> None:
    seeds = root_nodes.default_root_node_seeds(
        session_key="session:root",
        agent_id="assistant",
        metadata={"workspace_dir": "/workspace/task"},
    )
    by_id = {seed.node_id: seed for seed in seeds}

    workspace_root = by_id["workspace.resources"]
    assert workspace_root.parent_id == root_nodes.KNOWLEDGE_ROOT_NODE_ID
    assert workspace_root.kind == "workspace_resource_group"
    assert workspace_root.owner_ref == {
        "agent_id": "assistant",
        "session_key": "session:root",
    }


def test_default_parent_id_for_known_non_root_nodes() -> None:
    assert root_nodes.default_parent_id_for_node_id("runtime.contract") == (
        root_nodes.CONTEXT_INSTRUCTIONS_NODE_ID
    )
    assert root_nodes.default_parent_id_for_node_id("work.plan") == (
        root_nodes.TASK_ROOT_NODE_ID
    )
    assert root_nodes.default_parent_id_for_node_id("run.runtime") is None
    assert root_nodes.default_parent_id_for_node_id("tools.available") == (
        root_nodes.CAPABILITIES_ROOT_NODE_ID
    )
