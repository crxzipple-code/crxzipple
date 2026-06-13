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
from crxzipple.modules.context_workspace.application.rendering import (
    render_context_delta_body,
    tool_schema_names,
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
        run_workspace_metadata = build_run_workspace_metadata(
            run=run,
            prompt=prompt,
            flow_context=flow_context.to_payload(),
        )
        self._workspace_service.ensure_workspace(
            EnsureContextWorkspaceInput(
                session_key=session_key,
                agent_id=agent_id,
                metadata=run_workspace_metadata,
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
        evidence_frontier = _evidence_frontier_from_workspace_metadata(
            run_workspace_metadata,
        )
        if evidence_frontier is not None:
            snapshot_metadata["evidence_frontier"] = evidence_frontier
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
        parent_snapshot = _parent_snapshot_ref(
            run=run,
            render_service=self._render_service,
        )
        parent_snapshot_id = parent_snapshot.id if parent_snapshot is not None else None
        parent_tree_revision = (
            parent_snapshot.tree_revision if parent_snapshot is not None else None
        )
        context_delta = _context_delta_metadata(
            parent_snapshot=parent_snapshot,
            current_revision=rendered.workspace.active_revision,
            session_key=session_key,
            current_included_node_ids=rendered.included_node_ids,
            current_provider_attachments=provider_attachments,
            current_snapshot_metadata=snapshot_metadata,
        )
        if context_delta is not None:
            snapshot_metadata["context_delta"] = context_delta
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
) -> ContextRenderSnapshot | None:
    value = run.metadata.get("context_render_snapshot_id")
    if not isinstance(value, str) or not value.strip():
        return None
    snapshot_id = value.strip()
    try:
        return render_service.get_snapshot(snapshot_id)
    except ContextRenderSnapshotNotFoundError:
        return None


def _context_delta_metadata(
    *,
    parent_snapshot: ContextRenderSnapshot | None,
    current_revision: int,
    session_key: str,
    current_included_node_ids: tuple[str, ...],
    current_provider_attachments: dict[str, object],
    current_snapshot_metadata: dict[str, object],
) -> dict[str, object] | None:
    if parent_snapshot is None:
        return None
    baseline_node_ids = tuple(parent_snapshot.included_node_ids)
    added_node_ids = tuple(
        node_id
        for node_id in current_included_node_ids
        if node_id not in baseline_node_ids
    )
    removed_node_ids = tuple(
        node_id
        for node_id in baseline_node_ids
        if node_id not in current_included_node_ids
    )
    baseline_tool_schema_names = tool_schema_names(parent_snapshot.provider_attachments)
    current_tool_schema_names = tool_schema_names(current_provider_attachments)
    added_tool_schema_names = tuple(
        name for name in current_tool_schema_names if name not in baseline_tool_schema_names
    )
    removed_tool_schema_names = tuple(
        name for name in baseline_tool_schema_names if name not in current_tool_schema_names
    )
    evidence_delta = _evidence_frontier_delta(
        parent_snapshot.metadata,
        current_snapshot_metadata,
    )
    changed_revision = current_revision != parent_snapshot.tree_revision
    if (
        not changed_revision
        and not added_node_ids
        and not removed_node_ids
        and not added_tool_schema_names
        and not removed_tool_schema_names
        and evidence_delta is None
    ):
        return None
    prompt_body = render_context_delta_body(
        workspace=_DeltaWorkspace(
            session_key=session_key,
            active_revision=current_revision,
        ),
        baseline=parent_snapshot,
        added_node_ids=added_node_ids,
        removed_node_ids=removed_node_ids,
        added_tool_schema_names=added_tool_schema_names,
        removed_tool_schema_names=removed_tool_schema_names,
        evidence_delta=evidence_delta,
    )
    payload: dict[str, object] = {
        "baseline_snapshot_id": parent_snapshot.id,
        "baseline_revision": parent_snapshot.tree_revision,
        "current_revision": current_revision,
        "changed_revision": changed_revision,
        "added_node_ids": list(added_node_ids),
        "removed_node_ids": list(removed_node_ids),
        "added_tool_schema_names": list(added_tool_schema_names),
        "removed_tool_schema_names": list(removed_tool_schema_names),
        "prompt_body": prompt_body,
    }
    if evidence_delta is not None:
        payload["evidence_delta"] = evidence_delta
    return payload


def _evidence_frontier_from_workspace_metadata(
    metadata: dict[str, object],
) -> dict[str, object] | None:
    node = metadata.get("evidence_frontier_node")
    if not isinstance(node, dict):
        return None
    frontier = node.get("metadata")
    if not isinstance(frontier, dict):
        return None
    return dict(frontier)


def _evidence_frontier_delta(
    baseline_metadata: dict[str, object],
    current_metadata: dict[str, object],
) -> dict[str, object] | None:
    baseline = _dict_value(baseline_metadata.get("evidence_frontier"))
    current = _dict_value(current_metadata.get("evidence_frontier"))
    if not current:
        return None
    if baseline.get("fingerprint") == current.get("fingerprint"):
        return None
    baseline_ids = {
        str(item.get("id"))
        for item in _dict_list_value(baseline.get("items"))
        if item.get("id") is not None
    }
    current_items = _dict_list_value(current.get("items"))
    new_items = [
        item
        for item in current_items
        if str(item.get("id")) not in baseline_ids
    ]
    return {
        "schema_version": current.get("schema_version"),
        "baseline_fingerprint": baseline.get("fingerprint"),
        "current_fingerprint": current.get("fingerprint"),
        "item_count": current.get("item_count", len(current_items)),
        "new_items": new_items,
        "verified_facts": _list_value(current.get("verified_facts")),
        "failed_evidence_paths": _list_value(current.get("failed_evidence_paths")),
        "remaining_gaps": _list_value(current.get("remaining_gaps")),
    }


def _dict_value(value: object) -> dict[str, object]:
    return dict(value) if isinstance(value, dict) else {}


def _dict_list_value(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list | tuple):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]


def _list_value(value: object) -> list[object]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return []


class _DeltaWorkspace:
    def __init__(self, *, session_key: str, active_revision: int) -> None:
        self.session_key = session_key
        self.active_revision = active_revision


__all__ = ["ContextWorkspacePromptSnapshotAdapter"]
