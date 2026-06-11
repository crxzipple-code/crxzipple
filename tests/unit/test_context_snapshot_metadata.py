from __future__ import annotations

from crxzipple.modules.context_workspace.application import root_nodes
from crxzipple.modules.context_workspace.application.rendering.snapshot_metadata import (
    context_render_budget_metadata,
    render_snapshot_metadata_defaults,
    root_node_ids,
    runtime_contract_metadata,
)
from crxzipple.modules.context_workspace.application.rendering.estimates import (
    evidence_path_breakdown,
)
from crxzipple.modules.context_workspace.domain import (
    ContextNode,
    ContextWorkspace,
)


def test_root_node_ids_follow_schema_order_before_display_order() -> None:
    workspace = ContextWorkspace.new(
        session_key="session:metadata",
        agent_id="assistant",
    )
    nodes = (
        ContextNode(
            id="tools.available",
            workspace_id=workspace.id,
            owner="tool",
            kind="tool_group",
            title="Tools",
            display_order=1,
        ),
        ContextNode(
            id=root_nodes.CONTEXT_INSTRUCTIONS_NODE_ID,
            workspace_id=workspace.id,
            owner="runtime",
            kind="instructions",
            title="Instructions",
            display_order=99,
        ),
        ContextNode(
            id=root_nodes.SESSION_CURRENT_NODE_ID,
            workspace_id=workspace.id,
            owner="session",
            kind="session_current",
            title="Session",
            display_order=0,
        ),
    )

    assert root_node_ids(nodes) == (
        root_nodes.CONTEXT_INSTRUCTIONS_NODE_ID,
        root_nodes.SESSION_CURRENT_NODE_ID,
        "tools.available",
    )


def test_render_snapshot_metadata_defaults_preserve_existing_values() -> None:
    workspace = ContextWorkspace.new(
        session_key="session:metadata",
        agent_id="assistant",
    )
    nodes = (
        ContextNode(
            id=root_nodes.CONTEXT_INSTRUCTIONS_NODE_ID,
            workspace_id=workspace.id,
            owner="runtime",
            kind="instructions",
            title="Instructions",
        ),
    )

    metadata = render_snapshot_metadata_defaults(
        {
            "tree_schema_version": "custom",
            "root_node_ids": ["custom.root"],
        },
        nodes=nodes,
    )

    assert metadata["tree_schema_version"] == "custom"
    assert metadata["root_node_ids"] == ["custom.root"]
    assert metadata["context_instructions_node_id"] == (
        root_nodes.CONTEXT_INSTRUCTIONS_NODE_ID
    )
    assert metadata["execution_current_node_id"] == root_nodes.EXECUTION_CURRENT_NODE_ID
    assert metadata["session_current_node_id"] == root_nodes.SESSION_CURRENT_NODE_ID


def test_runtime_contract_metadata_reads_contract_node_identity() -> None:
    workspace = ContextWorkspace.new(
        session_key="session:metadata",
        agent_id="assistant",
    )
    contract = ContextNode(
        id="runtime.contract",
        workspace_id=workspace.id,
        owner="runtime",
        kind="runtime_contract",
        title="Runtime Contract",
        revision="rev-1",
        metadata={
            "contract_version": "2026-06-08",
            "content_hash": "abc123",
        },
    )

    assert runtime_contract_metadata((contract,)) == {
        "node_id": "runtime.contract",
        "contract_version": "2026-06-08",
        "content_hash": "abc123",
        "revision": "rev-1",
    }


def test_context_render_budget_metadata_extracts_fixed_budget_fields() -> None:
    metadata = context_render_budget_metadata(
        {
            "rendered_prompt_estimated_tokens": 10,
            "direct_transcript_estimated_tokens": 2,
            "mirrored_tool_schema_estimated_tokens": 3,
            "artifact_content_estimated_tokens": 4,
            "estimated_provider_prompt_tokens": 19,
            "tool_schema_mirror_budget_status": "ok",
            "artifact_content_budget": {"status": "ok"},
            "node_estimate_breakdown": {
                "top_rendered_nodes": [{"node_id": "runtime.contract"}],
            },
        },
    )

    assert metadata == {
        "rendered_prompt_estimated_tokens": 10,
        "direct_transcript_estimated_tokens": 2,
        "mirrored_tool_schema_estimated_tokens": 3,
        "artifact_content_estimated_tokens": 4,
        "estimated_provider_prompt_tokens": 19,
        "tool_schema_mirror_budget_status": "ok",
        "artifact_content_budget": {"status": "ok"},
        "top_rendered_nodes": [{"node_id": "runtime.contract"}],
    }


def test_evidence_path_breakdown_marks_final_response_requirement() -> None:
    workspace = ContextWorkspace.new(
        session_key="session:evidence",
        agent_id="assistant",
    )
    nodes = (
        ContextNode(
            id="session.evidence.network",
            workspace_id=workspace.id,
            owner="session",
            kind="session_evidence",
            title="Network Evidence",
            metadata={
                "tool_name": "browser.network.replay_request",
                "verified": True,
                "facts": {"evidence_path": "network_truth"},
            },
            owner_ref={"evidence_lifecycle_status": "verified"},
        ),
        ContextNode(
            id="session.evidence.runtime",
            workspace_id=workspace.id,
            owner="session",
            kind="session_evidence",
            title="Runtime Evidence",
            metadata={
                "tool_name": "browser.runtime.inspect",
                "facts": {"evidence_path": "runtime_and_code"},
            },
        ),
    )

    breakdown = evidence_path_breakdown(nodes)

    assert breakdown["session_evidence_count"] == 2
    assert breakdown["verified_evidence_path_count"] == 1
    assert breakdown["verified_evidence_paths"] == ["network_truth"]
    assert breakdown["browser_verified_evidence_path_count"] == 1
    assert breakdown["browser_verified_evidence_paths"] == ["network_truth"]
    assert breakdown["unverified_evidence_paths"] == ["runtime_and_code"]
    assert breakdown["final_response_requires_evidence_path"] is True
