"""Orchestration to Context Workspace integration."""

from __future__ import annotations

from crxzipple.modules.context_workspace.application import (
    ContextRenderService,
    ContextTreeService,
    ContextWorkspaceService,
    EnsureContextWorkspaceInput,
    RecordContextRenderSnapshotInput,
    RenderContextPromptInput,
)
from crxzipple.modules.context_workspace.domain import (
    ContextRenderSnapshot,
    ContextRenderSnapshotNotFoundError,
)
from crxzipple.modules.llm.domain import LlmCapability
from crxzipple.modules.orchestration.application.flow_context import (
    build_flow_context_payload,
)
from crxzipple.modules.orchestration.application.ports import (
    ContextRenderSnapshotRecord,
)
from crxzipple.modules.orchestration.application.prompt_input import (
    RunPromptInput,
)
from crxzipple.modules.orchestration.domain import OrchestrationRun

from .artifact_mirror import build_artifact_content_blocks
from .run_workspace_metadata import build_run_workspace_metadata
from .snapshot_metadata import (
    build_context_snapshot_metadata,
    build_snapshot_provider_attachments,
    mirrored_tool_schemas,
)
from .tool_schema_bootstrap import (
    merge_default_tool_schema_metadata,
    resolve_default_tool_schema_metadata,
    resolve_prompt_tool_schema_metadata,
)


class ContextWorkspacePromptSnapshotAdapter:
    """Records a tree-backed prompt snapshot for real orchestration runs.

    The adapter is intentionally side-effect narrow: it materializes Context
    Workspace state alongside the existing RunPromptInputCollector output and returns
    the rendered prompt body to the orchestration engine for provider delivery.
    """

    def __init__(
        self,
        *,
        workspace_service: ContextWorkspaceService,
        render_service: ContextRenderService,
        tree_service: ContextTreeService | None = None,
        artifact_service: object | None = None,
    ) -> None:
        self._workspace_service = workspace_service
        self._render_service = render_service
        self._tree_service = tree_service
        self._artifact_service = artifact_service

    def preview_run_prompt_snapshot(
        self,
        *,
        run: OrchestrationRun,
        prompt: RunPromptInput,
    ) -> ContextRenderSnapshotRecord | None:
        return self._render_run_prompt_snapshot(
            run=run,
            prompt=prompt,
            persist=False,
        )

    def get_recorded_run_prompt_snapshot(
        self,
        *,
        run: OrchestrationRun,
        prompt: RunPromptInput,
    ) -> ContextRenderSnapshotRecord | None:
        try:
            snapshot = self._render_service.get_snapshot_by_run(run.id)
        except ContextRenderSnapshotNotFoundError:
            return None
        return self._record_from_snapshot(snapshot, prompt=prompt)

    def record_run_prompt_snapshot(
        self,
        *,
        run: OrchestrationRun,
        prompt: RunPromptInput,
    ) -> ContextRenderSnapshotRecord | None:
        return self._render_run_prompt_snapshot(
            run=run,
            prompt=prompt,
            persist=True,
        )

    def _render_run_prompt_snapshot(
        self,
        *,
        run: OrchestrationRun,
        prompt: RunPromptInput,
        persist: bool,
    ) -> ContextRenderSnapshotRecord | None:
        session_key = prompt.session_key.strip()
        agent_id = str(run.agent_id or "").strip()
        if not session_key or not agent_id:
            return None
        flow_context = build_flow_context_payload(
            mode=prompt.mode,
            hint_payload=prompt.flow_hint,
        )
        self._workspace_service.ensure_workspace(
            EnsureContextWorkspaceInput(
                session_key=session_key,
                agent_id=agent_id,
                metadata=build_run_workspace_metadata(
                    run=run,
                    prompt=prompt,
                    flow_context=flow_context.to_payload(),
                ),
            ),
        )
        render_metadata = merge_default_tool_schema_metadata(
            resolve_prompt_tool_schema_metadata(prompt),
            resolve_default_tool_schema_metadata(
                tree_service=self._tree_service,
                session_key=session_key,
                run_id=run.id,
                prompt=prompt,
            ),
        )
        rendered = self._render_service.render_prompt_body(
            RenderContextPromptInput(
                session_key=session_key,
                run_id=run.id,
                metadata=render_metadata,
            ),
        )
        provider_attachments = build_snapshot_provider_attachments(
            rendered.provider_attachments,
            prompt=prompt,
        )
        artifact_content_blocks = build_artifact_content_blocks(
            provider_attachments,
            artifact_service=self._artifact_service,
            allow_vision=LlmCapability.VISION_INPUT in prompt.llm_capabilities,
        )
        snapshot_metadata = build_context_snapshot_metadata(
            run=run,
            prompt=prompt,
            rendered_prompt_body=rendered.prompt_body,
            provider_attachments=provider_attachments,
            provider_attachment_report=rendered.provider_attachment_report,
            included_node_ids=rendered.included_node_ids,
            flow_context=flow_context.to_payload(),
            artifact_content_blocks=artifact_content_blocks,
            estimate_breakdown=rendered.estimate_breakdown,
            runtime_contract=rendered.runtime_contract,
            tree_schema_version=rendered.tree_schema_version,
            root_node_ids=rendered.root_node_ids,
            mirrored_node_ids=rendered.mirrored_node_ids,
            tool_schema_count=len(provider_attachments.get("tool_schemas", ())),
        )
        included_refs = _snapshot_ref_tuple(
            snapshot_metadata.get("direct_session_item_refs"),
        )
        collapsed_refs = _snapshot_ref_tuple(
            _snapshot_budget_dict(snapshot_metadata).get("collapsed_refs"),
        )
        protocol_required_refs = _snapshot_ref_tuple(
            snapshot_metadata.get("protocol_required_refs"),
        )
        estimate_payload = rendered.estimate.to_payload()
        if rendered.estimate_breakdown:
            estimate_payload["breakdown"] = dict(rendered.estimate_breakdown)
        parent_snapshot_id, parent_tree_revision = _parent_snapshot_ref(
            run=run,
            render_service=self._render_service,
        )
        snapshot_id = f"ctxpreview_{run.id}"
        if persist:
            snapshot = self._render_service.record_render_snapshot(
                RecordContextRenderSnapshotInput(
                    session_key=session_key,
                    run_id=run.id,
                    prompt_body=rendered.prompt_body,
                    provider_attachments=provider_attachments,
                    estimate=rendered.estimate,
                    included_node_ids=rendered.included_node_ids,
                    mirrored_node_ids=rendered.mirrored_node_ids,
                    included_refs=included_refs,
                    collapsed_refs=collapsed_refs,
                    protocol_required_refs=protocol_required_refs,
                    metadata=snapshot_metadata,
                    parent_snapshot_id=parent_snapshot_id,
                    parent_tree_revision=parent_tree_revision,
                ),
            )
            snapshot_id = snapshot.id
        return ContextRenderSnapshotRecord(
            snapshot_id=snapshot_id,
            prompt_body=rendered.prompt_body,
            estimate=estimate_payload,
            included_node_ids=rendered.included_node_ids,
            mirrored_node_ids=rendered.mirrored_node_ids,
            included_refs=included_refs,
            collapsed_refs=collapsed_refs,
            protocol_required_refs=protocol_required_refs,
            metadata=snapshot_metadata,
            provider_attachments=provider_attachments,
            tool_schemas=mirrored_tool_schemas(
                provider_attachments,
                mirror_available=rendered.tool_schema_mirror_available,
            ),
            tool_schema_mirror_available=rendered.tool_schema_mirror_available,
            artifact_content_blocks=artifact_content_blocks,
            parent_snapshot_id=parent_snapshot_id,
            parent_tree_revision=parent_tree_revision,
        )

    def _record_from_snapshot(
        self,
        snapshot: ContextRenderSnapshot,
        *,
        prompt: RunPromptInput,
    ) -> ContextRenderSnapshotRecord:
        provider_attachments = dict(snapshot.provider_attachments)
        metadata = dict(snapshot.metadata)
        mirror_available = bool(
            provider_attachments.get("tool_schemas")
            or metadata.get("mirrored_tool_schema_count"),
        )
        return ContextRenderSnapshotRecord(
            snapshot_id=snapshot.id,
            prompt_body=snapshot.prompt_body,
            estimate=snapshot.estimate.to_payload(),
            included_node_ids=snapshot.included_node_ids,
            mirrored_node_ids=snapshot.mirrored_node_ids,
            included_refs=snapshot.included_refs,
            collapsed_refs=snapshot.collapsed_refs,
            protocol_required_refs=snapshot.protocol_required_refs,
            metadata=metadata,
            provider_attachments=provider_attachments,
            tool_schemas=mirrored_tool_schemas(
                provider_attachments,
                mirror_available=mirror_available,
            ),
            tool_schema_mirror_available=mirror_available,
            artifact_content_blocks=build_artifact_content_blocks(
                provider_attachments,
                artifact_service=self._artifact_service,
                allow_vision=LlmCapability.VISION_INPUT in prompt.llm_capabilities,
            ),
            parent_snapshot_id=snapshot.parent_snapshot_id,
            parent_tree_revision=snapshot.parent_tree_revision,
        )


def _snapshot_ref_tuple(value: object) -> tuple[dict[str, object], ...]:
    if not isinstance(value, list | tuple):
        return ()
    return tuple(dict(ref) for ref in value if isinstance(ref, dict))


def _snapshot_budget_dict(metadata: dict[str, object]) -> dict[str, object]:
    value = metadata.get("direct_transcript_budget")
    if not isinstance(value, dict):
        return {}
    return dict(value)


def _parent_snapshot_ref(
    *,
    run: OrchestrationRun,
    render_service: ContextRenderService,
) -> tuple[str | None, int | None]:
    value = run.metadata.get("context_render_snapshot_id")
    if not isinstance(value, str) or not value.strip():
        return None, None
    snapshot_id = value.strip()
    try:
        snapshot = render_service.get_snapshot(snapshot_id)
    except ContextRenderSnapshotNotFoundError:
        return None, None
    return snapshot.id, snapshot.tree_revision


__all__ = ["ContextWorkspacePromptSnapshotAdapter"]
