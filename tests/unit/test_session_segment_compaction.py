from __future__ import annotations

import unittest

from crxzipple.modules.session.application import (
    AppendSessionMessageInput,
    CompactSessionSegmentInput,
    EnsureSessionInput,
    ListSessionInstancesInput,
    ListSessionMessagesInput,
    ResetSessionInput,
    SessionApplicationService,
)
from crxzipple.modules.session.domain import SessionMessageVisibility
from crxzipple.modules.session.domain.exceptions import SessionValidationError
from crxzipple.modules.session.infrastructure import (
    InMemorySessionInstanceRepository,
    InMemorySessionMessageRepository,
    InMemorySessionRepository,
)


class _FakeSessionUnitOfWork:
    def __init__(self) -> None:
        self.sessions = InMemorySessionRepository()
        self.session_messages = InMemorySessionMessageRepository()
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

    def _append(self, text: str, *, role: str = "user"):
        return self.service.append_message(
            AppendSessionMessageInput(
                session_key="agent:assistant:main",
                role=role,
                content_payload={"blocks": [{"type": "text", "text": text}]},
            ),
        )

    def test_compact_active_segment_closes_old_instance_archives_history_and_opens_next(
        self,
    ) -> None:
        session = self._start_session()
        old_session_id = session.active_session_id
        first = self._append("old user message")
        second = self._append("old assistant message", role="assistant")
        summary = self._append("summary", role="assistant")

        result = self.service.compact_active_segment(
            CompactSessionSegmentInput(
                session_key=session.id,
                session_id=old_session_id,
                summary_message_id=summary.id,
                summary_text="The user and assistant discussed an old topic.",
                compaction_run_id="run-compact-1",
                reason="context_window_pressure",
            ),
        )
        compacted = result.session

        self.assertNotEqual(compacted.active_session_id, old_session_id)
        self.assertEqual(compacted.last_reset_at, compacted.updated_at)
        self.assertEqual(result.compacted_session_id, old_session_id)
        self.assertEqual(result.active_session_id, compacted.active_session_id)
        self.assertEqual(result.archived_message_count, 2)
        self.assertEqual(result.archived_through_sequence_no, summary.sequence_no - 1)
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
        self.assertEqual(segment["summary_message_id"], summary.id)
        self.assertEqual(
            segment["summary_text"],
            "The user and assistant discussed an old topic.",
        )
        self.assertEqual(segment["compaction_run_id"], "run-compact-1")
        self.assertEqual(segment["archived_message_count"], 2)
        self.assertEqual(segment["archived_through_sequence_no"], summary.sequence_no - 1)
        self.assertEqual(segment["reason"], "context_window_pressure")
        self.assertIn("compacted_at", segment)

        messages = self.service.list_messages(
            ListSessionMessagesInput(
                session_key=session.id,
                include_archived=True,
            ),
        )
        by_id = {message.id: message for message in messages}
        self.assertEqual(
            by_id[first.id].visibility,
            SessionMessageVisibility.ARCHIVED,
        )
        self.assertEqual(
            by_id[second.id].visibility,
            SessionMessageVisibility.ARCHIVED,
        )
        self.assertEqual(
            by_id[summary.id].visibility,
            SessionMessageVisibility.DEFAULT,
        )
        self.assertEqual(
            by_id[first.id].metadata["archived_by_compaction_run_id"],
            "run-compact-1",
        )

        active_messages = self.service.list_messages(
            ListSessionMessagesInput(
                session_key=session.id,
                active_session_only=True,
            ),
        )
        self.assertEqual(active_messages, [])

        event = self.uow.published_events[-1]
        self.assertEqual(event.name, "session.segment.compacted")
        self.assertEqual(event.payload["session_key"], session.id)
        self.assertEqual(event.payload["closed_session_id"], old_session_id)
        self.assertEqual(event.payload["active_session_id"], compacted.active_session_id)
        self.assertEqual(event.payload["archived_message_count"], 2)
        self.assertEqual(event.payload["compaction_run_id"], "run-compact-1")

    def test_compact_active_segment_respects_explicit_archive_threshold_without_summary(
        self,
    ) -> None:
        session = self._start_session()
        old_session_id = session.active_session_id
        before = self._append("before summary")
        summary = self._append("summary", role="assistant")
        after = self._append("after summary", role="assistant")

        self.service.compact_active_segment(
            CompactSessionSegmentInput(
                session_key=session.id,
                session_id=old_session_id,
                summary_message_id=summary.id,
                summary_text="Summary stays visible in the closed segment.",
                compaction_run_id="run-compact-2",
                archived_through_sequence_no=after.sequence_no,
            ),
        )

        messages = self.service.list_messages(
            ListSessionMessagesInput(
                session_key=session.id,
                include_archived=True,
            ),
        )
        by_id = {message.id: message for message in messages}
        self.assertEqual(
            by_id[before.id].visibility,
            SessionMessageVisibility.ARCHIVED,
        )
        self.assertEqual(
            by_id[summary.id].visibility,
            SessionMessageVisibility.DEFAULT,
        )
        self.assertEqual(
            by_id[after.id].visibility,
            SessionMessageVisibility.ARCHIVED,
        )

        closed = self.service.list_instances(
            ListSessionInstancesInput(session_key=session.id),
        )[0]
        self.assertEqual(closed.metadata["segment"]["archived_message_count"], 2)
        self.assertEqual(
            closed.metadata["segment"]["archived_through_sequence_no"],
            after.sequence_no,
        )

    def test_compact_active_segment_rejects_non_active_session_id(self) -> None:
        session = self._start_session()
        old_session_id = session.active_session_id
        summary = self._append("summary", role="assistant")
        reset = self.service.reset_session(
            ResetSessionInput(session_key=session.id),
        )

        with self.assertRaises(SessionValidationError):
            self.service.compact_active_segment(
                CompactSessionSegmentInput(
                    session_key=session.id,
                    session_id=old_session_id,
                    summary_message_id=summary.id,
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
