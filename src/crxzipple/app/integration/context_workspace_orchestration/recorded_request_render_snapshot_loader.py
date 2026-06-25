from __future__ import annotations

from crxzipple.modules.context_workspace.domain import ContextSnapshot
from crxzipple.modules.llm.domain import LlmCapability
from crxzipple.modules.orchestration.application.ports import (
    RequestRenderSnapshotRecord,
)
from crxzipple.modules.orchestration.application.runtime_llm_request_draft import (
    RuntimeLlmRequestDraft,
)

from .artifact_mirror import ArtifactMirrorAdapter
from .request_render_snapshot_recorder import RequestRenderSnapshotRecorder


class RecordedRequestRenderSnapshotLoader:
    def __init__(
        self,
        *,
        request_render_snapshot_recorder: RequestRenderSnapshotRecorder,
        artifact_mirror_adapter: ArtifactMirrorAdapter,
    ) -> None:
        self._request_render_snapshot_recorder = request_render_snapshot_recorder
        self._artifact_mirror_adapter = artifact_mirror_adapter

    def load(
        self,
        snapshot: ContextSnapshot,
        *,
        draft: RuntimeLlmRequestDraft,
    ) -> RequestRenderSnapshotRecord:
        provider_attachments = dict(snapshot.provider_attachments)
        metadata = dict(snapshot.metadata)
        tool_schemas = self._request_render_snapshot_recorder.tool_schemas(snapshot)
        return RequestRenderSnapshotRecord(
            snapshot_id=snapshot.id,
            estimate=snapshot.estimate.to_payload(),
            included_node_ids=snapshot.included_node_ids,
            mirrored_node_ids=snapshot.mirrored_node_ids,
            included_refs=snapshot.included_refs,
            collapsed_refs=snapshot.collapsed_refs,
            protocol_required_refs=snapshot.protocol_required_refs,
            input_item_refs=(
                self._request_render_snapshot_recorder.input_item_refs(snapshot)
            ),
            projected_input_items=(
                self._request_render_snapshot_recorder.projected_input_items(snapshot)
            ),
            metadata=metadata,
            tool_schemas=tool_schemas,
            tool_schema_refs=(
                self._request_render_snapshot_recorder.tool_schema_refs(snapshot)
            ),
            tool_schema_mirror_available=bool(tool_schemas),
            artifact_content_blocks=self._artifact_mirror_adapter.content_blocks(
                provider_attachments,
                allow_vision=LlmCapability.VISION_INPUT in draft.llm_capabilities,
            ),
            parent_snapshot_id=snapshot.parent_snapshot_id,
            parent_tree_revision=snapshot.parent_tree_revision,
        )
