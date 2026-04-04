from __future__ import annotations

from datetime import timedelta
import unittest

from crxzipple.modules.orchestration.application import (
    OrchestrationRouter,
    ResolveSessionBundleInput,
    SessionResolver,
)
from crxzipple.modules.session.application import (
    ArchiveSessionMessagesInput,
    AppendSessionMessageInput,
    EnsureSessionInput,
    ListSessionInstancesInput,
    ListSessionMessagesInput,
    SessionApplicationService,
)
from crxzipple.modules.session.domain import (
    DirectSessionScope,
    SessionMessageKind,
    SessionMessageVisibility,
    SessionResetPolicy,
    SessionRouteContext,
)
from crxzipple.modules.session.infrastructure import (
    InMemorySessionInstanceRepository,
    InMemorySessionMessageRepository,
    InMemorySessionRepository,
)
from crxzipple.modules.session.domain.value_objects import utcnow


class _FakeSessionUnitOfWork:
    def __init__(self) -> None:
        self.sessions = InMemorySessionRepository()
        self.session_messages = InMemorySessionMessageRepository()
        self.session_instances = InMemorySessionInstanceRepository()

    def __enter__(self) -> "_FakeSessionUnitOfWork":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # noqa: ANN001
        del exc_type, exc, tb

    def collect(self, aggregate) -> None:  # noqa: ANN001
        del aggregate

    def commit(self) -> None:
        return None

    def rollback(self) -> None:
        return None


class SessionServiceTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.uow = _FakeSessionUnitOfWork()
        self.service = SessionApplicationService(
            lambda: self.uow,
            workspace_defaults_resolver=lambda agent_id: f"/tmp/{agent_id}-home",
        )
        self.resolver = SessionResolver(
            session_service=self.service,
            router=OrchestrationRouter(),
        )

    def test_resolve_session_ensures_main_session_with_main_instance_kind(self) -> None:
        result = self.resolver.resolve(
            ResolveSessionBundleInput(
                context=SessionRouteContext(
                    agent_id="assistant",
                    channel="webchat",
                    label="browser",
                    surface="chat",
                    direct_scope=DirectSessionScope.MAIN,
                    metadata={"scope": "main"},
                ),
                ensure=True,
            ),
        )

        self.assertEqual(result.resolution.resolution.key, "agent:assistant:main")
        self.assertEqual(result.resolution.resolution.kind.value, "main")
        self.assertTrue(result.resolution.resolution.created)
        self.assertIsNotNone(result.session)
        self.assertIsNotNone(result.active_instance)
        self.assertEqual(result.session.chat_type, "direct")
        self.assertEqual(result.active_instance.kind.value, "main")

        listed = self.service.list_instances(
            ListSessionInstancesInput(session_key="agent:assistant:main"),
        )
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0].sequence_no, 1)
        self.assertEqual(listed[0].kind.value, "main")

    def test_resolve_session_applies_idle_reset_policy_with_new_instance(self) -> None:
        started_at = utcnow()
        initial = self.resolver.resolve(
            ResolveSessionBundleInput(
                context=SessionRouteContext(
                    agent_id="assistant",
                    channel="webchat",
                    direct_scope=DirectSessionScope.MAIN,
                ),
                ensure=True,
                now=started_at,
            ),
        )
        self.service.append_message(
            AppendSessionMessageInput(
                session_key=initial.resolution.resolution.key,
                role="user",
                content_payload={"blocks": [{"type": "text", "text": "hello"}]},
            ),
        )

        resolved = self.resolver.resolve(
            ResolveSessionBundleInput(
                context=SessionRouteContext(
                    agent_id="assistant",
                    channel="webchat",
                    direct_scope=DirectSessionScope.MAIN,
                ),
                ensure=True,
                reset_policy=SessionResetPolicy(idle_minutes=30),
                now=started_at + timedelta(minutes=31),
            ),
        )

        self.assertFalse(resolved.resolution.resolution.created)
        self.assertTrue(resolved.resolution.resolution.reset)
        self.assertEqual(resolved.resolution.resolution.reset_reason, "idle")
        self.assertIsNotNone(resolved.active_instance)
        self.assertNotEqual(
            resolved.active_instance.id,
            initial.active_instance.id,
        )

        instances = self.service.list_instances(
            ListSessionInstancesInput(session_key=initial.resolution.resolution.key),
        )
        self.assertEqual(len(instances), 2)
        self.assertEqual(instances[0].id, initial.active_instance.id)
        self.assertEqual(instances[0].status, "closed")
        self.assertEqual(instances[0].reset_reason, "idle")
        self.assertEqual(instances[1].id, resolved.active_instance.id)
        self.assertEqual(instances[1].status, "active")

    def test_ensure_session_persists_runtime_binding_workspace(self) -> None:
        session = self.service.ensure_session(
            EnsureSessionInput(
                key="agent:assistant:main",
                agent_id="assistant",
                workspace="/tmp/project",
            ),
        )

        binding = session.runtime_binding()
        self.assertEqual(binding.workspace, "/tmp/project")

        instances = self.service.list_instances(
            ListSessionInstancesInput(session_key=session.id),
        )
        self.assertEqual(len(instances), 1)
        self.assertEqual(
            instances[0].metadata["runtime_binding"]["workspace"],
            "/tmp/project",
        )

    def test_ensure_session_defaults_workspace_to_agent_home(self) -> None:
        session = self.service.ensure_session(
            EnsureSessionInput(
                key="agent:assistant:main",
                agent_id="assistant",
            ),
        )

        binding = session.runtime_binding()
        self.assertEqual(binding.workspace, "/tmp/assistant-home")

    def test_append_message_creates_structured_transcript_payload_and_sequence(self) -> None:
        session = self.service.ensure_session(
            EnsureSessionInput(
                key="agent:assistant:main",
                agent_id="assistant",
            ),
        )

        first = self.service.append_message(
            AppendSessionMessageInput(
                session_key=session.id,
                role="user",
                content_payload={"blocks": [{"type": "text", "text": "hello"}]},
            ),
        )
        second = self.service.append_message(
            AppendSessionMessageInput(
                session_key=session.id,
                role="tool",
                kind=SessionMessageKind.TOOL_RESULT,
                content_payload={"tool": "search", "result": "ok"},
                source_kind="tool_run",
                source_id="run-1",
                visibility=SessionMessageVisibility.INTERNAL,
            ),
        )

        history = self.service.list_messages(
            ListSessionMessagesInput(
                session_key=session.id,
            ),
        )

        self.assertEqual(first.sequence_no, 1)
        self.assertEqual(
            first.content_payload,
            {"blocks": [{"type": "text", "text": "hello"}]},
        )
        self.assertEqual(second.sequence_no, 2)
        self.assertEqual(second.kind.value, "tool_result")
        self.assertEqual(second.content_payload["tool"], "search")
        self.assertEqual(second.source_kind, "tool_run")
        self.assertEqual(second.source_id, "run-1")
        self.assertEqual(second.visibility.value, "internal")
        self.assertEqual([item.sequence_no for item in history], [1, 2])

    def test_archive_messages_marks_existing_messages_without_duplication(self) -> None:
        session = self.service.ensure_session(
            EnsureSessionInput(
                key="agent:assistant:main",
                agent_id="assistant",
            ),
        )
        first = self.service.append_message(
            AppendSessionMessageInput(
                session_key=session.id,
                role="user",
                content_payload={"blocks": [{"type": "text", "text": "hello"}]},
            ),
        )
        second = self.service.append_message(
            AppendSessionMessageInput(
                session_key=session.id,
                role="assistant",
                content_payload={"blocks": [{"type": "text", "text": "hi"}]},
            ),
        )

        archived_count = self.service.archive_messages(
            ArchiveSessionMessagesInput(
                session_key=session.id,
                session_id=session.active_session_id,
                max_sequence_no=1,
                reason="compaction",
            ),
        )
        history = self.service.list_messages(
            ListSessionMessagesInput(
                session_key=session.id,
                active_session_only=True,
            ),
        )

        self.assertEqual(archived_count, 1)
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0].id, first.id)
        self.assertEqual(history[0].visibility.value, "archived")
        self.assertEqual(history[0].metadata["archived_reason"], "compaction")
        self.assertEqual(history[1].id, second.id)
        self.assertEqual(history[1].visibility.value, "default")

    def test_sync_routed_session_records_runtime_binding_snapshots(self) -> None:
        result = self.resolver.resolve(
            ResolveSessionBundleInput(
                context=SessionRouteContext(
                    agent_id="assistant",
                    channel="webchat",
                    direct_scope=DirectSessionScope.MAIN,
                ),
                ensure=True,
            ),
        )

        assert result.session is not None
        assert result.active_instance is not None
        self.assertEqual(
            result.session.metadata["runtime_binding"],
            {
                "agent_id": "assistant",
                "workspace": "/tmp/assistant-home",
            },
        )
        self.assertEqual(
            result.active_instance.metadata["runtime_binding"],
            {
                "agent_id": "assistant",
                "workspace": "/tmp/assistant-home",
            },
        )
        self.assertEqual(result.active_instance.metadata["agent_id"], "assistant")
        self.assertNotIn("llm_id", result.active_instance.metadata)

    def test_list_sessions_filters_by_runtime_binding_even_if_legacy_agent_field_stale(self) -> None:
        session = self.service.ensure_session(
            EnsureSessionInput(
                key="agent:assistant:main",
                agent_id="assistant",
            ),
        )
        session.agent_id = "legacy-stale-agent"

        filtered = self.service.list_sessions(agent_id="assistant")

        self.assertEqual([item.id for item in filtered], ["agent:assistant:main"])

    def test_resolve_session_routes_thread_sessions_under_parent_conversation(self) -> None:
        result = self.resolver.resolve(
            ResolveSessionBundleInput(
                context=SessionRouteContext(
                    agent_id="assistant",
                    channel="slack",
                    chat_type="group",
                    conversation_id="channel-123",
                    thread_id="thread-999",
                ),
            ),
        )

        self.assertEqual(
            result.resolution.resolution.key,
            "agent:assistant:slack:group:channel-123:thread:thread-999",
        )
        self.assertEqual(result.resolution.resolution.kind.value, "thread")
        self.assertIsNone(result.session)
        self.assertIsNone(result.active_instance)

    def test_ensure_session_repairs_missing_instance_with_main_kind(self) -> None:
        session = self.service.ensure_session(
            EnsureSessionInput(
                key="agent:assistant:main",
                agent_id="assistant",
                channel="webchat",
                chat_type="direct",
            ),
        )
        del self.uow.session_instances._items[session.active_session_id]

        repaired = self.service.ensure_session(
            EnsureSessionInput(
                key="agent:assistant:main",
                agent_id="assistant",
                channel="webchat",
                chat_type="direct",
            ),
        )

        instances = self.service.list_instances(
            ListSessionInstancesInput(session_key="agent:assistant:main"),
        )
        self.assertEqual(repaired.active_session_id, session.active_session_id)
        self.assertEqual(len(instances), 1)
        self.assertEqual(instances[0].kind.value, "main")
