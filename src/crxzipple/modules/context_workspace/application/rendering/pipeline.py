from __future__ import annotations

from crxzipple.modules.context_workspace.application import root_nodes
from crxzipple.modules.context_workspace.application.models import (
    RenderContextPromptResult,
)
from crxzipple.modules.context_workspace.domain import ContextNode, ContextWorkspace

from .estimates import aggregate_estimate, estimate_breakdown, text_estimate
from .provider_mirror import render_provider_attachments
from .snapshot_metadata import root_node_ids, runtime_contract_metadata
from .xml_renderer import render_context_tree, tree_prompt_visible_nodes


class ContextRenderPipeline:
    def render_prompt_body(
        self,
        *,
        workspace: ContextWorkspace,
        nodes: tuple[ContextNode, ...],
        provider_attachments: dict[str, object],
        metadata: dict[str, object],
    ) -> RenderContextPromptResult:
        visible_nodes = tree_prompt_visible_nodes(nodes)
        node_estimate = aggregate_estimate(visible_nodes)
        breakdown = estimate_breakdown(visible_nodes)
        prompt_body = render_context_tree(workspace, visible_nodes)
        estimate = text_estimate(prompt_body)
        breakdown["node_visible"] = node_estimate.to_payload()
        breakdown["rendered_prompt"] = estimate.to_payload()
        (
            mirrored_attachments,
            mirrored_node_ids,
            tool_schema_mirror_available,
            provider_attachment_report,
        ) = render_provider_attachments(
            visible_nodes,
            base=provider_attachments,
            render_metadata=metadata,
        )
        return RenderContextPromptResult(
            workspace=workspace,
            prompt_body=prompt_body,
            estimate=estimate,
            included_node_ids=tuple(node.id for node in visible_nodes),
            estimate_breakdown=breakdown,
            runtime_contract=runtime_contract_metadata(visible_nodes),
            tree_schema_version=root_nodes.CONTEXT_TREE_SCHEMA_VERSION,
            root_node_ids=root_node_ids(visible_nodes),
            provider_attachments=mirrored_attachments,
            provider_attachment_report=provider_attachment_report,
            mirrored_node_ids=mirrored_node_ids,
            tool_schema_mirror_available=tool_schema_mirror_available,
        )


__all__ = ["ContextRenderPipeline"]
