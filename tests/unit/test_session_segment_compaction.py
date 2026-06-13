from __future__ import annotations

import unittest

from crxzipple.modules.session.application import (
    AppendSessionItemInput,
    CompactSessionSegmentInput,
    EnsureSessionInput,
    ListSessionInstancesInput,
    ListSessionItemsInput,
    ResetSessionInput,
    SessionApplicationService,
)
from crxzipple.modules.session.domain import (
    SessionItemKind,
    SessionItemVisibility,
)
from crxzipple.modules.session.domain.exceptions import SessionValidationError
from crxzipple.modules.session.infrastructure import (
    InMemorySessionInstanceRepository,
    InMemorySessionItemRepository,
    InMemorySessionRepository,
)


class _FakeSessionUnitOfWork:
    def __init__(self) -> None:
        self.sessions = InMemorySessionRepository()
        self.session_items = InMemorySessionItemRepository()
        self.session_instances = InMemorySessionInstanceRepository()
        self.published_events = []

    def __enter__(self) -> "_FakeSessionUnitOfWork":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # noqa: ANN001
        del exc_type, exc, tb

    def collect(self, aggregate) -> None:  # noqa: ANN001
        for event in aggregate.pull_events():
            self.published_events.append(event)

    def commit(self) -> None:
        return None

    def flush(self) -> None:
        return None

    def rollback(self) -> None:
        return None


class SessionSegmentCompactionTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.uow = _FakeSessionUnitOfWork()
        self.service = SessionApplicationService(
            lambda: self.uow,
            workspace_defaults_resolver=lambda agent_id: f"/tmp/{agent_id}-home",
        )

    def _start_session(self):
        session = self.service.ensure_session(
            EnsureSessionInput(
                key="agent:assistant:main",
                agent_id="assistant",
            ),
        )
        self.uow.published_events.clear()
        return session

    def _append_item(
        self,
        text: str,
        *,
        role: str = "assistant",
        kind: SessionItemKind = SessionItemKind.ASSISTANT_MESSAGE,
    ):
        return self.service.append_item(
            AppendSessionItemInput(
                session_key="agent:assistant:main",
                role=role,
                kind=kind,
                content_payload={"text": text},
                visibility=SessionItemVisibility(model_visible=True),
            ),
        )

    def test_compact_active_segment_archives_items_and_opens_next_instance(self) -> None:
        session = self._start_session()
        old_session_id = session.active_session_id
        reasoning = self._append_item(
            "old assistant reasoning",
            kind=SessionItemKind.REASONING,
        )
        answer = self._append_item("old assistant answer")
        summary = self._append_item(
            "Item summary",
            kind=SessionItemKind.COMPACTION,
        )

        result = self.service.compact_active_segment(
            CompactSessionSegmentInput(
                session_key=session.id,
                session_id=old_session_id,
                summary_item_id=summary.id,
                summary_text="Item summary",
                compaction_run_id="run-compact-items",
                reason="context_window_pressure",
            ),
        )
        compacted = result.session

        self.assertNotEqual(compacted.active_session_id, old_session_id)
        self.assertEqual(compacted.last_reset_at, compacted.updated_at)
        self.assertEqual(result.compacted_session_id, old_session_id)
        self.assertEqual(result.active_session_id, compacted.active_session_id)
        self.assertEqual(result.archived_item_count, 2)
        self.assertEqual(
            result.archived_through_item_sequence_no,
            summary.sequence_no - 1,
        )
        self.assertIsNotNone(result.compacted_at)

        instances = self.service.list_instances(
            ListSessionInstancesInput(session_key=session.id),
        )
        self.assertEqual(len(instances), 2)
        closed, active = instances
        self.assertEqual(closed.id, old_session_id)
        self.assertEqual(closed.status, "closed")
        self.assertEqual(closed.reset_reason, "context_window_pressure")
        self.assertEqual(active.id, compacted.active_session_id)
        self.assertEqual(active.status, "active")
        self.assertEqual(active.sequence_no, closed.sequence_no + 1)

        segment = closed.metadata["segment"]
        self.assertEqual(segment["kind"], "compacted")
        self.assertEqual(segment["summary_item_id"], summary.id)
        self.assertEqual(segment["summary_text"], "Item summary")
        self.assertEqual(segment["compaction_run_id"], "run-compact-items")
        self.assertEqual(segment["archived_item_count"], 2)
        self.assertEqual(
            segment["archived_through_item_sequence_no"],
            summary.sequence_no - 1,
        )
        self.assertEqual(segment["reason"], "context_window_pressure")
        self.assertIn("compacted_at", segment)
        self.assertNotIn("summary_message_id", segment)
        self.assertNotIn("archived_message_count", segment)

        active_items = self.service.list_items(
            ListSessionItemsInput(
                session_key=session.id,
                active_session_only=True,
            ),
        )
        self.assertEqual(active_items, [])

        all_items = self.service.list_items(
            ListSessionItemsInput(session_key=session.id),
        )
        by_id = {item.id: item for item in all_items}
        for archived_item_id in (reasoning.id, answer.id):
            metadata = by_id[archived_item_id].metadata
            self.assertEqual(metadata["compacted_segment_id"], old_session_id)
            self.assertEqual(
                metadata["archived_by_compaction_run_id"],
                "run-compact-items",
            )
            self.assertEqual(metadata["archived_reason"], "context_window_pressure")
            self.assertEqual(metadata["summary_item_id"], summary.id)
            self.assertEqual(
                metadata["archived_through_item_sequence_no"],
                summary.sequence_no - 1,
            )
        self.assertNotIn("compacted_segment_id", by_id[summary.id].metadata)

        event = self.uow.published_events[-1]
        self.assertEqual(event.name, "session.segment.compacted")
        self.assertEqual(event.payload["session_key"], session.id)
        self.assertEqual(event.payload["closed_session_id"], old_session_id)
        self.assertEqual(event.payload["active_session_id"], compacted.active_session_id)
        self.assertEqual(event.payload["archived_item_count"], 2)
        self.assertNotIn("archived_message_count", event.payload)
        self.assertEqual(event.payload["compaction_run_id"], "run-compact-items")

    def test_compact_active_segment_respects_explicit_item_archive_threshold(self) -> None:
        session = self._start_session()
        old_session_id = session.active_session_id
        before = self._append_item("before summary")
        summary = self._append_item("summary", kind=SessionItemKind.COMPACTION)
        after = self._append_item("after summary")

        self.service.compact_active_segment(
            CompactSessionSegmentInput(
                session_key=session.id,
                session_id=old_session_id,
                summary_item_id=summary.id,
                summary_text="Summary stays visible in the closed segment.",
                compaction_run_id="run-compact-threshold",
                archived_through_item_sequence_no=after.sequence_no,
            ),
        )

        items = self.service.list_items(ListSessionItemsInput(session_key=session.id))
        by_id = {item.id: item for item in items}
        self.assertEqual(
            by_id[before.id].metadata["archived_by_compaction_run_id"],
            "run-compact-threshold",
        )
        self.assertNotIn("archived_by_compaction_run_id", by_id[summary.id].metadata)
        self.assertEqual(
            by_id[after.id].metadata["archived_by_compaction_run_id"],
            "run-compact-threshold",
        )

        closed = self.service.list_instances(
            ListSessionInstancesInput(session_key=session.id),
        )[0]
        self.assertEqual(closed.metadata["segment"]["archived_item_count"], 2)
        self.assertEqual(
            closed.metadata["segment"]["archived_through_item_sequence_no"],
            after.sequence_no,
        )

    def test_compact_active_segment_rejects_non_active_session_id(self) -> None:
        session = self._start_session()
        old_session_id = session.active_session_id
        summary = self._append_item("summary", kind=SessionItemKind.COMPACTION)
        reset = self.service.reset_session(
            ResetSessionInput(session_key=session.id),
        )

        with self.assertRaises(SessionValidationError):
            self.service.compact_active_segment(
                CompactSessionSegmentInput(
                    session_key=session.id,
                    session_id=old_session_id,
                    summary_item_id=summary.id,
                    summary_text="Should not compact a closed segment.",
                    compaction_run_id="run-compact-3",
                ),
            )

        self.assertEqual(
            self.service.get_session(session.id).active_session_id,
            reset.active_session_id,
        )


if __name__ == "__main__":
    unittest.main()
