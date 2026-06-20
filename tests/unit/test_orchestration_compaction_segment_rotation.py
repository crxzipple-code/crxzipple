from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from crxzipple.modules.orchestration.application.maintenance import (
    OrchestrationMaintenanceService,
)
from crxzipple.modules.session.application import (
    CompactSessionSegmentInput,
    CompactSessionSegmentResult,
    MergeSessionItemMetadataInput,
)
from crxzipple.modules.orchestration.domain.entities import OrchestrationRun
from crxzipple.modules.orchestration.domain.value_objects import (
    InboundInstruction,
    OrchestrationRunStage,
    OrchestrationRunStatus,
)
from crxzipple.modules.orchestration.infrastructure.in_memory_repository import (
    InMemoryOrchestrationRunRepository,
)
from crxzipple.modules.session.domain import Session
from crxzipple.modules.session.domain.value_objects import (
    SessionItem,
    SessionItemKind,
)


class _FakeOrchestrationUnitOfWork:
    def __init__(self, runs: InMemoryOrchestrationRunRepository) -> None:
        self.orchestration_runs = runs
        self.committed = False

    def __enter__(self) -> "_FakeOrchestrationUnitOfWork":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: Any,
    ) -> None:
        return None

    def collect(self, aggregate: object) -> None:
        return None

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        return None


class _FakeSessionMaintenancePort:
    def __init__(
        self,
        summary_item: SessionItem | None = None,
    ) -> None:
        self.summary_item = summary_item
        self.item_lookups: list[str] = []
        self.merged_item_metadata: list[MergeSessionItemMetadataInput] = []
        self.compact_calls: list[CompactSessionSegmentInput] = []

    def get_item(self, item_id: str) -> SessionItem:
        self.item_lookups.append(item_id)
        if self.summary_item is None or item_id != self.summary_item.id:
            raise AssertionError(f"unexpected item lookup: {item_id}")
        return self.summary_item

    def merge_item_metadata(
        self,
        data: MergeSessionItemMetadataInput,
    ) -> SessionItem:
        self.merged_item_metadata.append(data)
        assert self.summary_item is not None
        return self.summary_item

    def compact_active_segment(
        self,
        data: CompactSessionSegmentInput,
    ) -> CompactSessionSegmentResult:
        self.compact_calls.append(data)
        return CompactSessionSegmentResult(
            session=Session(id=data.session_key, agent_id="assistant"),
            archived_item_count=2,
            archived_through_item_sequence_no=data.archived_through_item_sequence_no,
            compacted_at="2026-06-01T08:00:00+00:00",
            compacted_session_id=data.session_id,
            active_session_id="segment-2",
        )


def _unexpected(*args: object, **kwargs: object) -> Any:
    raise AssertionError("unexpected maintenance dependency call")


def test_compaction_summary_requires_session_item_frontier() -> None:
    completed_at = datetime(2026, 6, 1, 8, 0, tzinfo=timezone.utc)
    run = OrchestrationRun(
        id="run-compact",
        inbound_instruction=InboundInstruction(
            source="compaction",
            content="compact this session",
        ),
        status=OrchestrationRunStatus.COMPLETED,
        stage=OrchestrationRunStage.COMPLETED,
        active_session_id="segment-1",
        metadata={
            "runtime_request_mode": "compaction",
            "session_key": "agent:assistant:main",
        },
        result_payload={
            "assistant_message_id": "msg-summary",
            "output_text": "Compacted session summary.",
        },
        completed_at=completed_at,
        updated_at=completed_at,
    )
    runs = InMemoryOrchestrationRunRepository()
    runs.add(run)
    session_service = _FakeSessionMaintenancePort()
    service = OrchestrationMaintenanceService(
        uow_factory=lambda: _FakeOrchestrationUnitOfWork(runs),
        engine=None,
        session_service=session_service,
        llm_port=None,
        request_coordinator=None,
        request_memory_flush=_unexpected,
        request_compaction=_unexpected,
        fail_assignment=_unexpected,
        process_requested_run_inline=_unexpected,
        auto_compaction_enabled=False,
        auto_compaction_reserve_tokens=0,
        auto_compaction_soft_threshold_tokens=0,
    )

    service.apply_compaction_summary(run)

    assert session_service.compact_calls == []
    persisted_run = runs.get("run-compact")
    assert persisted_run is not None
    assert persisted_run.result_payload is not None
    assert persisted_run.result_payload["output_text"] == "Compacted session summary."
    assert "archived_message_count" not in persisted_run.result_payload
    assert "compacted_at" not in persisted_run.result_payload


def test_compaction_summary_prefers_session_item_frontier() -> None:
    completed_at = datetime(2026, 6, 1, 8, 0, tzinfo=timezone.utc)
    run = OrchestrationRun(
        id="run-compact",
        inbound_instruction=InboundInstruction(
            source="compaction",
            content="compact this session",
        ),
        status=OrchestrationRunStatus.COMPLETED,
        stage=OrchestrationRunStage.COMPLETED,
        active_session_id="segment-1",
        metadata={
            "runtime_request_mode": "compaction",
            "session_key": "agent:assistant:main",
        },
        result_payload={
            "assistant_message_id": "msg-legacy-summary",
            "session_item_ids": ["item-reasoning", "item-summary"],
            "output_text": "Compacted session summary.",
        },
        completed_at=completed_at,
        updated_at=completed_at,
    )
    runs = InMemoryOrchestrationRunRepository()
    runs.add(run)
    summary_item = SessionItem(
        id="item-summary",
        session_key="agent:assistant:main",
        session_id="segment-1",
        sequence_no=5,
        role="assistant",
        kind=SessionItemKind.ASSISTANT_MESSAGE,
        content_payload={"text": "Compacted session summary."},
        source_module="llm",
        source_kind="llm_response_item",
        source_id="llm-response-item-summary",
    )
    session_service = _FakeSessionMaintenancePort(summary_item=summary_item)
    service = OrchestrationMaintenanceService(
        uow_factory=lambda: _FakeOrchestrationUnitOfWork(runs),
        engine=None,
        session_service=session_service,
        llm_port=None,
        request_coordinator=None,
        request_memory_flush=_unexpected,
        request_compaction=_unexpected,
        fail_assignment=_unexpected,
        process_requested_run_inline=_unexpected,
        auto_compaction_enabled=False,
        auto_compaction_reserve_tokens=0,
        auto_compaction_soft_threshold_tokens=0,
    )

    service.apply_compaction_summary(run)

    assert session_service.item_lookups == ["item-summary"]
    assert session_service.merged_item_metadata == [
        MergeSessionItemMetadataInput(
            item_id="item-summary",
            metadata={
                "maintenance_kind": "compaction_summary",
                "maintenance_run_id": "run-compact",
            },
        ),
    ]
    assert session_service.compact_calls == [
        CompactSessionSegmentInput(
            session_key="agent:assistant:main",
            session_id="segment-1",
            summary_text="Compacted session summary.",
            compaction_run_id="run-compact",
            summary_item_id="item-summary",
            archived_through_item_sequence_no=4,
            reason="compaction",
        ),
    ]
    persisted_run = runs.get("run-compact")
    assert persisted_run is not None
    assert persisted_run.result_payload is not None
    assert persisted_run.result_payload["summary_item_id"] == "item-summary"
    assert persisted_run.result_payload["archived_item_count"] == 2
    assert persisted_run.result_payload["archived_through_item_sequence_no"] == 4
