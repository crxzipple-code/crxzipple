from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from crxzipple.modules.orchestration.application.maintenance import (
    OrchestrationMaintenanceService,
)
from crxzipple.modules.session.application import (
    CompactSessionSegmentInput,
    CompactSessionSegmentResult,
    MergeSessionMessageMetadataInput,
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
from crxzipple.modules.session.domain.value_objects import SessionMessage


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
    def __init__(self, summary_message: SessionMessage) -> None:
        self.summary_message = summary_message
        self.merged_message_metadata: list[MergeSessionMessageMetadataInput] = []
        self.compact_calls: list[CompactSessionSegmentInput] = []

    def get_message(self, message_id: str) -> SessionMessage:
        if message_id != self.summary_message.id:
            raise AssertionError(f"unexpected message lookup: {message_id}")
        return self.summary_message

    def merge_message_metadata(
        self,
        data: MergeSessionMessageMetadataInput,
    ) -> SessionMessage:
        self.merged_message_metadata.append(data)
        return self.summary_message

    def compact_active_segment(
        self,
        data: CompactSessionSegmentInput,
    ) -> CompactSessionSegmentResult:
        self.compact_calls.append(data)
        return CompactSessionSegmentResult(
            session=Session(id=data.session_key, agent_id="assistant"),
            archived_message_count=3,
            archived_through_sequence_no=data.archived_through_sequence_no,
            compacted_at="2026-06-01T08:00:00+00:00",
            compacted_session_id=data.session_id,
            active_session_id="segment-2",
        )


def _unexpected(*args: object, **kwargs: object) -> Any:
    raise AssertionError("unexpected maintenance dependency call")


def test_compaction_summary_requests_session_segment_compaction() -> None:
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
            "prompt_mode": "compaction",
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
    summary_message = SessionMessage(
        id="msg-summary",
        session_key="agent:assistant:main",
        session_id="segment-1",
        sequence_no=4,
        role="assistant",
        content_payload={
            "blocks": [
                {
                    "type": "text",
                    "text": "Compacted session summary.",
                },
            ],
        },
    )
    session_service = _FakeSessionMaintenancePort(summary_message)
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

    assert session_service.merged_message_metadata == [
        MergeSessionMessageMetadataInput(
            message_id="msg-summary",
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
            summary_message_id="msg-summary",
            summary_text="Compacted session summary.",
            compaction_run_id="run-compact",
            archived_through_sequence_no=3,
            reason="compaction",
        ),
    ]
    persisted_run = runs.get("run-compact")
    assert persisted_run is not None
    assert persisted_run.result_payload is not None
    assert persisted_run.result_payload["output_text"] == "Compacted session summary."
    assert persisted_run.result_payload["archived_message_count"] == 3
    assert persisted_run.result_payload["archived_through_sequence_no"] == 3
    assert persisted_run.result_payload["compacted_at"] == "2026-06-01T08:00:00+00:00"
