from __future__ import annotations

from crxzipple.modules.orchestration.domain import OrchestrationRun
from crxzipple.modules.session.application import (
    CompactSessionSegmentInput,
    MergeSessionItemMetadataInput,
)
from crxzipple.modules.session.domain import (
    SessionItem,
    SessionItemKind,
    SessionItemNotFoundError,
)
from crxzipple.shared.time import format_datetime_utc


class OrchestrationMaintenanceCompactionSummaryMixin:
    def apply_compaction_summary(self, run: OrchestrationRun) -> None:
        runtime_request_mode = str(run.metadata.get("runtime_request_mode", "")).strip().lower()
        if runtime_request_mode != "compaction":
            return
        session_key = str(run.metadata.get("session_key", "")).strip()
        if not session_key:
            return
        if run.active_session_id is None or not run.active_session_id.strip():
            return
        if self.session_service is None:
            return
        result_payload = run.result_payload or {}
        summary_item = self._summary_item_from_result_payload(
            result_payload,
            session_key=session_key,
            session_id=run.active_session_id,
        )
        summary_text = result_payload.get("output_text")
        if not isinstance(summary_text, str) or not summary_text.strip():
            return
        if summary_item is None:
            return
        self.session_service.merge_item_metadata(
            MergeSessionItemMetadataInput(
                item_id=summary_item.id,
                metadata={
                    "maintenance_kind": "compaction_summary",
                    "maintenance_run_id": run.id,
                },
            ),
        )
        cutoff_item_sequence_no = summary_item.sequence_no - 1
        if cutoff_item_sequence_no <= 0:
            return
        compacted_at = (
            format_datetime_utc(run.completed_at)
            if run.completed_at is not None
            else format_datetime_utc(run.updated_at)
        )
        segment_result = self.session_service.compact_active_segment(
            CompactSessionSegmentInput(
                session_key=session_key,
                session_id=run.active_session_id,
                summary_text=summary_text.strip(),
                compaction_run_id=run.id,
                summary_item_id=summary_item.id,
                archived_through_item_sequence_no=cutoff_item_sequence_no,
                reason="compaction",
            ),
        )
        result_compacted_at = segment_result.compacted_at or compacted_at
        with self.uow_factory() as uow:
            persisted_run = self._get_run(uow, run.id)
            updated_result_payload = dict(persisted_run.result_payload or {})
            updated_result_payload["archived_item_count"] = int(
                segment_result.archived_item_count,
            )
            if segment_result.archived_through_item_sequence_no is not None:
                updated_result_payload["archived_through_item_sequence_no"] = (
                    segment_result.archived_through_item_sequence_no
                )
            if summary_item is not None:
                updated_result_payload["summary_item_id"] = summary_item.id
            updated_result_payload["compacted_at"] = result_compacted_at
            persisted_run.result_payload = updated_result_payload
            uow.orchestration_runs.add(persisted_run)
            uow.collect(persisted_run)
            uow.commit()

    def _summary_item_from_result_payload(
        self,
        result_payload: dict[str, object],
        *,
        session_key: str,
        session_id: str,
    ) -> SessionItem | None:
        raw_ids = result_payload.get("session_item_ids")
        if not isinstance(raw_ids, (list, tuple)):
            return None
        candidate_ids = [
            item_id.strip()
            for item_id in raw_ids
            if isinstance(item_id, str) and item_id.strip()
        ]
        for item_id in reversed(candidate_ids):
            try:
                item = self.session_service.get_item(item_id)
            except SessionItemNotFoundError:
                continue
            if item.session_key != session_key or item.session_id != session_id:
                continue
            if item.kind not in {
                SessionItemKind.ASSISTANT_MESSAGE,
                SessionItemKind.CONTEXT_COMPACTION,
            }:
                continue
            return item
        return None
