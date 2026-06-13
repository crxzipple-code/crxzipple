from __future__ import annotations

from datetime import timedelta
import unittest

from crxzipple.modules.session.application import (
    AppendSessionItemInput,
    AppendSessionItemsInput,
    EnsureSessionInput,
    GetSessionItemBySourceInput,
    ListSessionInstancesInput,
    ListSessionItemsInput,
    MergeSessionItemMetadataInput,
    ResolveSessionInput,
    SessionApplicationService,
    SessionResolutionService,
)
from crxzipple.modules.session.domain import (
    DirectSessionScope,
    SessionItemKind,
    SessionItemPhase,
    SessionItemVisibility,
    SessionReply,
    SessionResetPolicy,
    SessionRouteContext,
)
from crxzipple.modules.session.infrastructure import (
    InMemorySessionItemRepository,
    InMemorySessionInstanceRepository,
    InMemorySessionRepository,
)
from crxzipple.modules.session.domain.value_objects import utcnow


class _FakeSessionUnitOfWork:
    def __init__(self) -> None:
        self.sessions = InMemorySessionRepository()
        self.session_items = InMemorySessionItemRepository()
        self.session_instances = InMemorySessionInstanceRepository()

    def __enter__(self) -> "_FakeSessionUnitOfWork":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # noqa: ANN001
        del exc_type, exc, tb

    def collect(self, aggregate) -> None:  # noqa: ANN001
        del aggregate

    def commit(self) -> None:
        return None

    def flush(self) -> None:
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
        self.resolver = SessionResolutionService(session_service=self.service)

    def test_resolve_session_ensures_main_session_with_main_instance_kind(self) -> None:
        result = self.resolver.resolve(
            ResolveSessionInput(
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

    def test_session_items_support_model_chat_and_trace_visible_views(self) -> None:
        self.service.ensure_session(
            EnsureSessionInput(
                key="agent:assistant:main",
                agent_id="assistant",
                workspace="workspace",
            ),
        )

        commentary = self.service.append_item(
            AppendSessionItemInput(
                session_key="agent:assistant:main",
                kind=SessionItemKind.ASSISTANT_MESSAGE,
                role="assistant",
                phase=SessionItemPhase.COMMENTARY,
                content_payload={"text": "I will inspect the page."},
                visibility=SessionItemVisibility(
                    model_visible=True,
                    user_visible=True,
                    chat_visible=False,
                    trace_visible=True,
                ),
                source_module="llm",
                source_kind="llm_response_item",
                source_id="llm-1:item:0",
            ),
        )
        final_answer = self.service.append_item(
            AppendSessionItemInput(
                session_key="agent:assistant:main",
                kind=SessionItemKind.ASSISTANT_MESSAGE,
                role="assistant",
                phase=SessionItemPhase.FINAL_ANSWER,
                content_payload={"text": "Done."},
                visibility=SessionItemVisibility(
                    model_visible=True,
                    user_visible=True,
                    chat_visible=True,
                    trace_visible=True,
                ),
            ),
        )
        tool_call = self.service.append_item(
            AppendSessionItemInput(
                session_key="agent:assistant:main",
                kind=SessionItemKind.TOOL_CALL,
                content_payload={"arguments": {"format": "text"}},
                visibility=SessionItemVisibility(
                    model_visible=True,
                    user_visible=False,
                    chat_visible=False,
                    trace_visible=True,
                ),
                source_module="llm",
                source_kind="llm_response_item",
                source_id="llm-1:item:1",
                provider_item_id="provider-call-1",
                call_id="call-browser-snapshot",
                tool_name="browser.snapshot",
            ),
        )

        model_items = self.service.list_model_visible_items(
            ListSessionItemsInput(session_key="agent:assistant:main"),
        )
        chat_items = self.service.list_chat_visible_items(
            ListSessionItemsInput(session_key="agent:assistant:main"),
        )
        trace_items = self.service.list_trace_visible_items(
            ListSessionItemsInput(session_key="agent:assistant:main"),
        )

        self.assertEqual(
            [item.id for item in model_items],
            [commentary.id, final_answer.id, tool_call.id],
        )
        self.assertEqual([item.id for item in chat_items], [final_answer.id])
        self.assertEqual(
            [item.id for item in trace_items],
            [commentary.id, final_answer.id, tool_call.id],
        )
        self.assertEqual(tool_call.call_id, "call-browser-snapshot")
        self.assertEqual(tool_call.provider_item_id, "provider-call-1")
        self.assertEqual(tool_call.source_id, "llm-1:item:1")

    def test_session_item_source_lookup_returns_existing_item(self) -> None:
        self.service.ensure_session(
            EnsureSessionInput(
                key="agent:assistant:main",
                agent_id="assistant",
                workspace="workspace",
            ),
        )
        item = self.service.append_item(
            AppendSessionItemInput(
                session_key="agent:assistant:main",
                kind=SessionItemKind.USER_MESSAGE,
                role="user",
                content_payload={"text": "search"},
                visibility=SessionItemVisibility(
                    model_visible=True,
                    user_visible=True,
                    chat_visible=True,
                    trace_visible=True,
                ),
                source_module="orchestration",
                source_kind="orchestration_run",
                source_id="run-user-input",
            ),
        )

        found = self.service.get_item_by_source(
            GetSessionItemBySourceInput(
                session_key="agent:assistant:main",
                session_id=item.session_id,
                source_module="orchestration",
                source_kind="orchestration_run",
                source_id="run-user-input",
            ),
        )

        self.assertIsNotNone(found)
        assert found is not None
        self.assertEqual(found.id, item.id)

    def test_resolve_session_applies_idle_reset_policy_with_new_instance(self) -> None:
        started_at = utcnow()
        initial = self.resolver.resolve(
            ResolveSessionInput(
                context=SessionRouteContext(
                    agent_id="assistant",
                    channel="webchat",
                    direct_scope=DirectSessionScope.MAIN,
                ),
                ensure=True,
                now=started_at,
            ),
        )
        self.service.append_item(
            AppendSessionItemInput(
                session_key=initial.resolution.resolution.key,
                kind=SessionItemKind.USER_MESSAGE,
                role="user",
                content_payload={"text": "hello"},
                visibility=SessionItemVisibility(
                    model_visible=True,
                    user_visible=True,
                    chat_visible=True,
                    trace_visible=True,
                ),
            ),
        )

        resolved = self.resolver.resolve(
            ResolveSessionInput(
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

    def test_ensure_session_persists_reply(self) -> None:
        session = self.service.ensure_session(
            EnsureSessionInput(
                key="agent:assistant:main",
                agent_id="assistant",
                reply=SessionReply(
                    channel="webhook",
                    to_id="conv-reply-1",
                    account_id="default",
                ),
            ),
        )

        self.assertEqual(session.reply.channel, "webhook")
        self.assertEqual(session.reply.to_id, "conv-reply-1")

    def test_append_item_creates_structured_payload_and_sequence(self) -> None:
        session = self.service.ensure_session(
            EnsureSessionInput(
                key="agent:assistant:main",
                agent_id="assistant",
            ),
        )

        first = self.service.append_item(
            AppendSessionItemInput(
                session_key=session.id,
                kind=SessionItemKind.USER_MESSAGE,
                role="user",
                content_payload={"text": "hello"},
                visibility=SessionItemVisibility(
                    model_visible=True,
                    user_visible=True,
                    chat_visible=True,
                    trace_visible=True,
                ),
            ),
        )
        second = self.service.append_item(
            AppendSessionItemInput(
                session_key=session.id,
                kind=SessionItemKind.TOOL_RESULT,
                content_payload={"tool": "search", "result": "ok"},
                source_module="tool",
                source_kind="tool_run",
                source_id="run-1",
                visibility=SessionItemVisibility(
                    model_visible=True,
                    user_visible=False,
                    chat_visible=False,
                    trace_visible=True,
                ),
            ),
        )

        history = self.service.list_items(
            ListSessionItemsInput(
                session_key=session.id,
            ),
        )

        self.assertEqual(first.sequence_no, 1)
        self.assertEqual(first.content_payload, {"text": "hello"})
        self.assertEqual(second.sequence_no, 2)
        self.assertEqual(second.kind.value, "tool_result")
        self.assertEqual(second.content_payload["tool"], "search")
        self.assertEqual(second.source_module, "tool")
        self.assertEqual(second.source_kind, "tool_run")
        self.assertEqual(second.source_id, "run-1")
        self.assertFalse(second.visibility.user_visible)
        self.assertEqual([item.sequence_no for item in history], [1, 2])

    def test_append_items_batches_sequence_assignment(self) -> None:
        session = self.service.ensure_session(
            EnsureSessionInput(
                key="agent:assistant:main",
                agent_id="assistant",
            ),
        )

        items = self.service.append_items(
            AppendSessionItemsInput(
                items=(
                    AppendSessionItemInput(
                        session_key=session.id,
                        kind=SessionItemKind.TOOL_CALL,
                        role="assistant",
                        content_payload={
                            "call_id": "call-1",
                            "name": "search",
                            "arguments": {"query": "hello"},
                        },
                        call_id="call-1",
                        tool_name="search",
                    ),
                    AppendSessionItemInput(
                        session_key=session.id,
                        kind=SessionItemKind.TOOL_RESULT,
                        content_payload={"tool": "search", "result": "ok"},
                        source_module="tool",
                        source_kind="tool_run",
                        source_id="tool-run-1",
                    ),
                ),
            ),
        )

        history = self.service.list_items(
            ListSessionItemsInput(session_key=session.id),
        )

        self.assertEqual([item.sequence_no for item in items], [1, 2])
        self.assertEqual([item.id for item in history], [item.id for item in items])
        self.assertEqual(history[0].call_id, "call-1")
        self.assertEqual(history[1].kind.value, "tool_result")

    def test_get_session_with_items_returns_bundle_from_one_read(self) -> None:
        session = self.service.ensure_session(
            EnsureSessionInput(
                key="agent:assistant:main",
                agent_id="assistant",
            ),
        )
        item = self.service.append_item(
            AppendSessionItemInput(
                session_key=session.id,
                kind=SessionItemKind.USER_MESSAGE,
                role="user",
                content_payload={"text": "hello"},
            ),
        )

        bundle = self.service.get_session_with_items(
            ListSessionItemsInput(
                session_key=session.id,
                active_session_only=True,
            ),
        )

        self.assertEqual(bundle.session.id, session.id)
        self.assertEqual([session_item.id for session_item in bundle.items], [item.id])

    def test_merge_item_metadata_keeps_item_inside_session_service(self) -> None:
        session = self.service.ensure_session(
            EnsureSessionInput(
                key="agent:assistant:main",
                agent_id="assistant",
            ),
        )
        item = self.service.append_item(
            AppendSessionItemInput(
                session_key=session.id,
                kind=SessionItemKind.COMPACTION,
                role="assistant",
                content_payload={"text": "summary"},
                metadata={"kind": "summary"},
            ),
        )

        updated = self.service.merge_item_metadata(
            MergeSessionItemMetadataInput(
                item_id=item.id,
                metadata={"maintenance_kind": "compaction_summary"},
            ),
        )

        self.assertEqual(updated.id, item.id)
        self.assertEqual(updated.metadata["kind"], "summary")
        self.assertEqual(updated.metadata["maintenance_kind"], "compaction_summary")
        self.assertEqual(
            self.service.get_item(item.id).metadata["maintenance_kind"],
            "compaction_summary",
        )

    def test_sync_routed_session_records_runtime_binding_snapshots(self) -> None:
        result = self.resolver.resolve(
            ResolveSessionInput(
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
            ResolveSessionInput(
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
