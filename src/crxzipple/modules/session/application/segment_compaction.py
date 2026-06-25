from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime

from crxzipple.modules.session.domain.entities import Session
from crxzipple.modules.session.domain.exceptions import SessionValidationError
from crxzipple.modules.session.domain.value_objects import SessionItem
from crxzipple.shared.time import format_datetime_utc as _format_datetime_utc


@dataclass(frozen=True, slots=True)
class CompactSessionSegmentInput:
    session_key: str
    session_id: str
    summary_text: str
    compaction_run_id: str
    summary_item_id: str | None = None
    archived_through_item_sequence_no: int | None = None
    reason: str | None = "compaction"


@dataclass(frozen=True, slots=True)
class CompactSessionSegmentResult:
    session: Session
    compacted_session_id: str
    active_session_id: str
    archived_item_count: int = 0
    archived_through_item_sequence_no: int | None = None
    compacted_at: str | None = None


@dataclass(frozen=True, slots=True)
class NormalizedSessionSegmentCompaction:
    session_id: str
    summary_item_id: str
    summary_text: str
    compaction_run_id: str
    reason: str
    archived_through_item_sequence_no: int | None


def normalize_segment_compaction_input(
    data: CompactSessionSegmentInput,
) -> NormalizedSessionSegmentCompaction:
    normalized_session_id = data.session_id.strip()
    normalized_summary_item_id = (data.summary_item_id or "").strip()
    normalized_summary_text = data.summary_text.strip()
    normalized_compaction_run_id = data.compaction_run_id.strip()
    normalized_reason = (data.reason or "compaction").strip() or "compaction"
    if not normalized_session_id:
        raise SessionValidationError("Compaction session_id cannot be empty.")
    if not normalized_summary_item_id:
        raise SessionValidationError("Compaction summary item id cannot be empty.")
    if not normalized_summary_text:
        raise SessionValidationError("Compaction summary_text cannot be empty.")
    if not normalized_compaction_run_id:
        raise SessionValidationError("Compaction run id cannot be empty.")
    if (
        data.archived_through_item_sequence_no is not None
        and data.archived_through_item_sequence_no < 0
    ):
        raise SessionValidationError(
            "Compaction archived_through_item_sequence_no cannot be negative.",
        )
    return NormalizedSessionSegmentCompaction(
        session_id=normalized_session_id,
        summary_item_id=normalized_summary_item_id,
        summary_text=normalized_summary_text,
        compaction_run_id=normalized_compaction_run_id,
        reason=normalized_reason,
        archived_through_item_sequence_no=data.archived_through_item_sequence_no,
    )


def ensure_summary_item_belongs_to_segment(
    *,
    session: Session,
    summary_item: SessionItem,
    compaction: NormalizedSessionSegmentCompaction,
) -> None:
    if (
        summary_item.session_key != session.id
        or summary_item.session_id != compaction.session_id
    ):
        raise SessionValidationError(
            "Compaction summary item must belong to the active session segment.",
        )


def archive_through_sequence_no(
    *,
    compaction: NormalizedSessionSegmentCompaction,
    summary_item: SessionItem,
) -> int | None:
    if compaction.archived_through_item_sequence_no is not None:
        return compaction.archived_through_item_sequence_no
    return max(summary_item.sequence_no - 1, 0)


def build_compacted_item(
    item: SessionItem,
    *,
    compaction: NormalizedSessionSegmentCompaction,
    archived_through_item_sequence_no: int | None,
) -> SessionItem | None:
    if item.id == compaction.summary_item_id:
        return None
    if (
        archived_through_item_sequence_no is not None
        and item.sequence_no > archived_through_item_sequence_no
    ):
        return None
    metadata = dict(item.metadata)
    metadata["archived_reason"] = compaction.reason
    metadata["archived_by_compaction_run_id"] = compaction.compaction_run_id
    metadata["compacted_segment_id"] = compaction.session_id
    metadata["archived_through_item_sequence_no"] = archived_through_item_sequence_no
    metadata["summary_item_id"] = compaction.summary_item_id
    return replace(item, metadata=metadata)


def compacted_segment_metadata(
    *,
    compaction: NormalizedSessionSegmentCompaction,
    archived_item_count: int,
    archived_through_item_sequence_no: int | None,
    compacted_at: datetime,
) -> dict[str, object]:
    return {
        "kind": "compacted",
        "summary_text": compaction.summary_text,
        "summary_item_id": compaction.summary_item_id,
        "compaction_run_id": compaction.compaction_run_id,
        "archived_item_count": archived_item_count,
        "archived_through_item_sequence_no": archived_through_item_sequence_no,
        "compacted_at": _format_datetime_utc(compacted_at),
        "reason": compaction.reason,
    }


def compacted_segment_result(
    *,
    session: Session,
    compaction: NormalizedSessionSegmentCompaction,
    archived_item_count: int,
    archived_through_item_sequence_no: int | None,
    compacted_at: datetime,
) -> CompactSessionSegmentResult:
    return CompactSessionSegmentResult(
        session=session,
        compacted_session_id=compaction.session_id,
        active_session_id=session.active_session_id,
        archived_item_count=archived_item_count,
        archived_through_item_sequence_no=archived_through_item_sequence_no,
        compacted_at=_format_datetime_utc(compacted_at),
    )
