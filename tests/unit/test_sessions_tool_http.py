from __future__ import annotations

import os

from crxzipple.modules.access.application.repositories import AccessCredentialBindingRecord
from crxzipple.modules.agent.application import RegisterAgentProfileInput
from crxzipple.modules.agent.domain import (
    AgentInstructionPolicy,
    AgentLlmRoutingPolicy,
)
from crxzipple.modules.llm.application import RegisterLlmProfileInput
from crxzipple.modules.llm.application.adapters import (
    LlmAdapterRequest,
    LlmAdapterResponse,
)
from crxzipple.modules.llm.domain import (
    LlmApiFamily,
    LlmProviderKind,
    LlmResult,
)
from crxzipple.modules.orchestration.domain import OrchestrationRunStatus
from crxzipple.modules.session.application import (
    AppendSessionItemInput,
    EnsureSessionInput,
    ListSessionItemsInput,
    MergeSessionItemMetadataInput,
    ResetSessionInput,
)
from crxzipple.modules.session.domain import (
    SessionItemKind,
)
from crxzipple.shared.content_blocks import describe_content_for_text_fallback
from tests.unit.tool_test_support import *  # noqa: F403


class _StaticTextAdapter:
    def __init__(self, *, text: str) -> None:
        self.text = text
        self.requests: list[LlmAdapterRequest] = []

    def invoke(self, _profile: object, request: LlmAdapterRequest) -> LlmAdapterResponse:
        self.requests.append(request)
        return LlmAdapterResponse(result=LlmResult(text=self.text))


class _SequentialTextAdapter:
    def __init__(self, *responses: str) -> None:
        self._responses = list(responses)
        self.requests: list[LlmAdapterRequest] = []

    def invoke(self, _profile: object, request: LlmAdapterRequest) -> LlmAdapterResponse:
        self.requests.append(request)
        if self._responses:
            text = self._responses.pop(0)
        else:
            text = ""
        return LlmAdapterResponse(result=LlmResult(text=text))


class _OverlayAccessConfigView:
    def __init__(self, records: dict[str, AccessCredentialBindingRecord], *, fallback):
        self.records = records
        self.fallback = fallback

    def get_credential_binding(self, binding_id: str):
        normalized = binding_id.strip()
        if normalized in self.records:
            return self.records[normalized]
        get_binding = getattr(self.fallback, "get_credential_binding", None)
        if callable(get_binding):
            return get_binding(normalized)
        return None


class SessionsToolHttpTestCase(ToolTestCaseBase):
    default_llm_credential_binding_id = "openai-api-key"
    default_llm_credential_env_name = "CRXZIPPLE_TEST_OPENAI_API_KEY"

    def _register_openai_llm_profile(self) -> None:
        credential_binding_id = self._install_default_llm_access_binding()
        self.llm_service.register_profile(
            RegisterLlmProfileInput(
                id="openai.gpt-5.4-mini",
                provider=LlmProviderKind.OPENAI,
                api_family=LlmApiFamily.OPENAI_RESPONSES,
                model_name="gpt-5.4-mini",
                credential_binding_id=credential_binding_id,
            ),
        )

    def _install_default_llm_access_binding(self) -> str:
        previous_value = os.environ.get(self.default_llm_credential_env_name)
        os.environ[self.default_llm_credential_env_name] = "test-openai-api-key"
        if previous_value is None:
            self.addCleanup(os.environ.pop, self.default_llm_credential_env_name, None)
        else:
            self.addCleanup(
                os.environ.__setitem__,
                self.default_llm_credential_env_name,
                previous_value,
            )
        existing_view = getattr(self.access_service, "config_view", None)
        self.access_service.config_view = _OverlayAccessConfigView(
            {
                self.default_llm_credential_binding_id: AccessCredentialBindingRecord(
                    binding_id=self.default_llm_credential_binding_id,
                    asset_id=None,
                    binding_kind="api_key",
                    source_kind="env",
                    source_ref=self.default_llm_credential_env_name,
                    masked_preview=f"env:{self.default_llm_credential_env_name}",
                    metadata={"test_fixture": "sessions_tool_http"},
                ),
            },
            fallback=existing_view,
        )
        return self.default_llm_credential_binding_id

    def _append_text(
        self,
        *,
        session_key: str,
        role: str,
        text: str,
        session_id: str | None = None,
        kind: SessionItemKind | None = None,
        source_kind: str | None = None,
        source_id: str | None = None,
    ) -> None:
        item_kind = kind or (
            SessionItemKind.TOOL_RESULT if role == "tool" else SessionItemKind.ASSISTANT_MESSAGE
        )
        if role == "user":
            item_kind = kind or SessionItemKind.USER_MESSAGE
        self.session_service.append_item(
            AppendSessionItemInput(
                session_key=session_key,
                session_id=session_id,
                role=role,
                kind=item_kind,
                source_module="test",
                source_kind=source_kind,
                source_id=source_id,
                content_payload={
                    "blocks": [
                        {
                            "type": "text",
                            "text": text,
                        }
                    ]
                },
            ),
        )

    def _archive_items(
        self,
        *,
        session_key: str,
        session_id: str,
        max_sequence_no: int,
        reason: str = "compacted",
    ) -> None:
        items = self.session_service.list_items(
            ListSessionItemsInput(
                session_key=session_key,
                active_session_only=False,
            ),
        )
        for item in items:
            if item.session_id != session_id or item.sequence_no > max_sequence_no:
                continue
            self.session_service.merge_item_metadata(
                MergeSessionItemMetadataInput(
                    item_id=item.id,
                    metadata={
                        "archived_reason": reason,
                        "compacted_segment_id": session_id,
                        "archived_through_item_sequence_no": max_sequence_no,
                    },
                ),
            )

    def test_session_status_uses_execution_context_and_reports_counts(self) -> None:
        session = self.session_service.ensure_session(
            EnsureSessionInput(
                key="agent:assistant:main",
                agent_id="assistant",
                workspace="/tmp/assistant",
                channel="webchat",
                chat_type="direct",
            ),
        )
        self.session_service.merge_session_metadata(
            session.id,
            metadata={
                "compaction": {
                    "summary": "latest compacted summary",
                    "archived_message_count": 4,
                }
            },
            touch_activity=False,
        )
        self._append_text(
            session_key=session.id,
            role="assistant",
            text="archive me first",
        )
        self._archive_items(
            session_key=session.id,
            session_id=session.active_session_id,
            max_sequence_no=1,
            reason="compacted",
        )
        self._append_text(
            session_key=session.id,
            role="user",
            text="keep me visible",
        )
        self._append_text(
            session_key=session.id,
            role="tool",
            text="internal tool result",
            kind=SessionItemKind.TOOL_RESULT,
            source_kind="tool_run",
            source_id="run-1",
        )

        tool_run = asyncio.run(
            self.tool_service.execute(
                ExecuteToolInput(
                    tool_id="session_status",
                    arguments={},
                    execution_context=ToolExecutionContext(
                        attrs={
                            "session_key": session.id,
                            "agent_id": "assistant",
                        },
                    ),
                ),
            ),
        )

        self.assertEqual(tool_run.status, ToolRunStatus.SUCCEEDED)
        metadata = tool_run.result.metadata
        self.assertEqual(metadata["tool"], "session_status")
        self.assertEqual(metadata["session"]["key"], session.id)
        self.assertEqual(metadata["active_instance"]["id"], session.active_session_id)
        self.assertEqual(metadata["counts"]["instance_count"], 1)
        self.assertEqual(metadata["counts"]["active_unarchived_item_count"], 2)
        self.assertEqual(metadata["counts"]["unarchived_item_count"], 2)
        self.assertEqual(metadata["counts"]["total_item_count"], 3)
        self.assertEqual(
            metadata["compaction"]["summary"],
            "latest compacted summary",
        )
        rendered = tool_run.result.blocks[0]["text"]
        self.assertIn("# Session Status", rendered)
        self.assertIn("- compaction: present", rendered)

    def test_sessions_list_defaults_to_context_agent_and_filters_status(self) -> None:
        self.session_service.ensure_session(
            EnsureSessionInput(
                key="agent:assistant:main",
                agent_id="assistant",
                status="active",
            ),
        )
        paused = self.session_service.ensure_session(
            EnsureSessionInput(
                key="agent:assistant:review",
                agent_id="assistant",
                status="paused",
            ),
        )
        self.session_service.ensure_session(
            EnsureSessionInput(
                key="agent:other:main",
                agent_id="other",
                status="paused",
            ),
        )

        tool_run = asyncio.run(
            self.tool_service.execute(
                ExecuteToolInput(
                    tool_id="sessions_list",
                    arguments={"status": "paused", "limit": 5},
                    execution_context=ToolExecutionContext(
                        attrs={"agent_id": "assistant"},
                    ),
                ),
            ),
        )

        self.assertEqual(tool_run.status, ToolRunStatus.SUCCEEDED)
        metadata = tool_run.result.metadata
        self.assertEqual(metadata["tool"], "sessions_list")
        self.assertEqual(metadata["agent_id"], "assistant")
        self.assertEqual(metadata["status"], "paused")
        self.assertEqual(metadata["available_count"], 1)
        self.assertEqual(metadata["returned_count"], 1)
        self.assertEqual(metadata["sessions"][0]["key"], paused.id)
        self.assertEqual(
            metadata["sessions"][0]["runtime_binding"]["agent_id"],
            "assistant",
        )
        self.assertIn("# Sessions", tool_run.result.blocks[0]["text"])

    def test_sessions_history_defaults_to_active_instance_only(self) -> None:
        session = self.session_service.ensure_session(
            EnsureSessionInput(
                key="agent:assistant:main",
                agent_id="assistant",
            ),
        )
        old_session_id = session.active_session_id
        self._append_text(
            session_key=session.id,
            session_id=old_session_id,
            role="user",
            text="old instance context",
        )

        self.session_service.reset_session(
            ResetSessionInput(
                session_key=session.id,
                reason="manual",
            ),
        )
        refreshed = self.session_service.get_session(session.id)
        active_session_id = refreshed.active_session_id
        self._append_text(
            session_key=session.id,
            session_id=active_session_id,
            role="assistant",
            text="archive this active message",
        )
        self._archive_items(
            session_key=session.id,
            session_id=active_session_id,
            max_sequence_no=1,
            reason="compacted",
        )
        self._append_text(
            session_key=session.id,
            session_id=active_session_id,
            role="user",
            text="active visible message",
        )
        self._append_text(
            session_key=session.id,
            session_id=active_session_id,
            role="tool",
            text="active internal tool",
            kind=SessionItemKind.TOOL_RESULT,
            source_kind="tool_run",
            source_id="run-2",
        )

        tool_run = asyncio.run(
            self.tool_service.execute(
                ExecuteToolInput(
                    tool_id="sessions_history",
                    arguments={},
                    execution_context=ToolExecutionContext(
                        attrs={"session_key": session.id},
                    ),
                ),
            ),
        )

        self.assertEqual(tool_run.status, ToolRunStatus.SUCCEEDED)
        metadata = tool_run.result.metadata
        self.assertTrue(metadata["active_session_only"])
        self.assertIsNone(metadata["session_id"])
        self.assertEqual(metadata["active_session_id"], active_session_id)
        self.assertEqual(metadata["available_count"], 2)
        self.assertEqual(metadata["returned_count"], 2)
        self.assertEqual(len(metadata["items"]), 2)
        self.assertEqual(metadata["items"][0]["session_id"], active_session_id)
        rendered = tool_run.result.blocks[0]["text"]
        self.assertIn("active visible message", rendered)
        self.assertNotIn("old instance context", rendered)
        self.assertIn("active internal tool", rendered)
        self.assertNotIn("archive this active message", rendered)

    def test_sessions_history_supports_explicit_session_id_and_include_archived(self) -> None:
        session = self.session_service.ensure_session(
            EnsureSessionInput(
                key="agent:assistant:main",
                agent_id="assistant",
            ),
        )
        old_session_id = session.active_session_id
        self._append_text(
            session_key=session.id,
            session_id=old_session_id,
            role="user",
            text="older visible message",
        )
        self._append_text(
            session_key=session.id,
            session_id=old_session_id,
            role="assistant",
            text="older archived message",
        )
        self._archive_items(
            session_key=session.id,
            session_id=old_session_id,
            max_sequence_no=2,
            reason="compacted",
        )
        self.session_service.reset_session(
            ResetSessionInput(
                session_key=session.id,
                reason="manual",
            ),
        )
        refreshed = self.session_service.get_session(session.id)
        self._append_text(
            session_key=session.id,
            session_id=refreshed.active_session_id,
            role="user",
            text="new active message",
        )

        tool_run = asyncio.run(
            self.tool_service.execute(
                ExecuteToolInput(
                    tool_id="sessions_history",
                    arguments={
                        "session_id": old_session_id,
                        "active_session_only": False,
                        "include_archived": True,
                        "limit": 10,
                    },
                    execution_context=ToolExecutionContext(
                        attrs={"session_key": session.id},
                    ),
                ),
            ),
        )

        self.assertEqual(tool_run.status, ToolRunStatus.SUCCEEDED)
        metadata = tool_run.result.metadata
        self.assertEqual(metadata["session_id"], old_session_id)
        self.assertFalse(metadata["active_session_only"])
        self.assertTrue(metadata["include_archived"])
        self.assertEqual(metadata["available_count"], 2)
        self.assertEqual(metadata["returned_count"], 2)
        self.assertEqual(
            [item["session_id"] for item in metadata["items"]],
            [old_session_id, old_session_id],
        )
        rendered = tool_run.result.blocks[0]["text"]
        self.assertIn("older visible message", rendered)
        self.assertIn("older archived message", rendered)
        self.assertNotIn("new active message", rendered)

    def test_sessions_send_appends_message_and_enqueues_exact_follow_up_run(self) -> None:
        adapter = _StaticTextAdapter(text="session send complete")
        self.llm_adapter_registry.register(
            LlmApiFamily.OPENAI_RESPONSES,
            adapter,
        )
        self._register_openai_llm_profile()
        self.agent_service.register_profile(
            RegisterAgentProfileInput(
                id="assistant",
                name="Assistant",
                instruction_policy=AgentInstructionPolicy(
                    system_prompt="Be helpful and concise.",
                ),
                llm_routing_policy=AgentLlmRoutingPolicy(
                    default_llm_id="openai.gpt-5.4-mini",
                ),
            ),
        )
        sender = self.session_service.ensure_session(
            EnsureSessionInput(
                key="agent:assistant:sender",
                agent_id="assistant",
            ),
        )
        target = self.session_service.ensure_session(
            EnsureSessionInput(
                key="agent:assistant:main",
                agent_id="assistant",
            ),
        )

        tool_run = asyncio.run(
            self.tool_service.execute(
                ExecuteToolInput(
                    tool_id="sessions_send",
                    arguments={
                        "session_key": target.id,
                        "text": "follow up from sender",
                    },
                    execution_context=ToolExecutionContext(
                        attrs={
                            "session_key": sender.id,
                            "agent_id": "assistant",
                            "run_id": "run-parent-1",
                        },
                    ),
                ),
            ),
        )

        self.assertEqual(tool_run.status, ToolRunStatus.SUCCEEDED)
        metadata = tool_run.result.metadata
        self.assertEqual(metadata["tool"], "sessions_send")
        self.assertEqual(metadata["session_key"], target.id)
        enqueued_run = self.orchestration_run_query_service.get_run(metadata["run_id"])
        self.assertEqual(enqueued_run.status, OrchestrationRunStatus.QUEUED)
        self.assertEqual(enqueued_run.session_key, target.id)
        self.assertEqual(enqueued_run.active_session_id, target.active_session_id)
        self.assertEqual(enqueued_run.inbound_instruction.source, "sessions_send")

        processed = process_next_orchestration_assignment(self.container,
            worker_id="worker-1",
        )

        self.assertIsNotNone(processed)
        assert processed is not None
        self.assertEqual(processed.status, OrchestrationRunStatus.COMPLETED)
        messages = self.session_service.list_items(
            ListSessionItemsInput(
                session_key=target.id,
                active_session_only=False,
            ),
        )
        self.assertEqual(len(messages), 2)
        self.assertEqual([item.role for item in messages], ["user", "assistant"])
        self.assertEqual(
            describe_content_for_text_fallback(messages[0].content_payload),
            "follow up from sender",
        )
        self.assertEqual(
            describe_content_for_text_fallback(messages[1].content_payload),
            "session send complete",
        )

    def test_sessions_spawn_creates_child_session_and_enqueues_child_run(self) -> None:
        adapter = _StaticTextAdapter(text="child session complete")
        self.llm_adapter_registry.register(
            LlmApiFamily.OPENAI_RESPONSES,
            adapter,
        )
        self._register_openai_llm_profile()
        self.agent_service.register_profile(
            RegisterAgentProfileInput(
                id="assistant",
                name="Assistant",
                instruction_policy=AgentInstructionPolicy(
                    system_prompt="Be helpful and concise.",
                ),
                llm_routing_policy=AgentLlmRoutingPolicy(
                    default_llm_id="openai.gpt-5.4-mini",
                ),
            ),
        )
        requester = self.session_service.ensure_session(
            EnsureSessionInput(
                key="agent:assistant:main",
                agent_id="assistant",
            ),
        )

        tool_run = asyncio.run(
            self.tool_service.execute(
                ExecuteToolInput(
                    tool_id="sessions_spawn",
                    arguments={
                        "text": "investigate this in a child session",
                    },
                    execution_context=ToolExecutionContext(
                        attrs={
                            "session_key": requester.id,
                            "agent_id": "assistant",
                            "run_id": "run-parent-2",
                        },
                    ),
                ),
            ),
        )

        self.assertEqual(tool_run.status, ToolRunStatus.SUCCEEDED)
        metadata = tool_run.result.metadata
        self.assertEqual(metadata["tool"], "sessions_spawn")
        self.assertEqual(metadata["requester_session_key"], requester.id)
        self.assertEqual(metadata["agent_id"], "assistant")
        self.assertTrue(metadata["child_session_key"].startswith("agent:assistant:subagent:"))

        child_session = self.session_service.get_session(
            metadata["child_session_key"],
        )
        self.assertEqual(child_session.active_session_id, metadata["child_active_session_id"])
        self.assertEqual(
            child_session.metadata["spawn"]["requester_session_key"],
            requester.id,
        )
        self.assertEqual(
            child_session.metadata["spawn"]["requester_run_id"],
            "run-parent-2",
        )

        enqueued_run = self.orchestration_run_query_service.get_run(metadata["run_id"])
        self.assertEqual(enqueued_run.status, OrchestrationRunStatus.QUEUED)
        self.assertEqual(enqueued_run.session_key, child_session.id)
        self.assertEqual(enqueued_run.active_session_id, child_session.active_session_id)
        self.assertEqual(enqueued_run.inbound_instruction.source, "sessions_spawn")

        processed = process_next_orchestration_assignment(self.container,
            worker_id="worker-1",
        )

        self.assertIsNotNone(processed)
        assert processed is not None
        self.assertEqual(processed.status, OrchestrationRunStatus.COMPLETED)
        messages = self.session_service.list_items(
            ListSessionItemsInput(
                session_key=child_session.id,
                active_session_only=False,
            ),
        )
        self.assertEqual(len(messages), 2)
        self.assertEqual([item.role for item in messages], ["user", "assistant"])
        self.assertEqual(
            describe_content_for_text_fallback(messages[0].content_payload),
            "investigate this in a child session",
        )
        self.assertEqual(
            describe_content_for_text_fallback(messages[1].content_payload),
            "child session complete",
        )

    def test_subagents_lists_child_session_buckets_for_requester(self) -> None:
        adapter = _StaticTextAdapter(text="child listing complete")
        self.llm_adapter_registry.register(
            LlmApiFamily.OPENAI_RESPONSES,
            adapter,
        )
        self._register_openai_llm_profile()
        self.agent_service.register_profile(
            RegisterAgentProfileInput(
                id="assistant",
                name="Assistant",
                instruction_policy=AgentInstructionPolicy(
                    system_prompt="Be helpful and concise.",
                ),
                llm_routing_policy=AgentLlmRoutingPolicy(
                    default_llm_id="openai.gpt-5.4-mini",
                ),
            ),
        )
        requester = self.session_service.ensure_session(
            EnsureSessionInput(
                key="agent:assistant:main",
                agent_id="assistant",
            ),
        )

        spawn_run = asyncio.run(
            self.tool_service.execute(
                ExecuteToolInput(
                    tool_id="sessions_spawn",
                    arguments={"text": "inspect child bucket"},
                    execution_context=ToolExecutionContext(
                        attrs={
                            "session_key": requester.id,
                            "agent_id": "assistant",
                            "run_id": "run-parent-3",
                        },
                    ),
                ),
            ),
        )
        self.assertEqual(spawn_run.status, ToolRunStatus.SUCCEEDED)
        child_session_key = spawn_run.result.metadata["child_session_key"]

        tool_run = asyncio.run(
            self.tool_service.execute(
                ExecuteToolInput(
                    tool_id="subagents",
                    arguments={},
                    execution_context=ToolExecutionContext(
                        attrs={
                            "session_key": requester.id,
                            "agent_id": "assistant",
                        },
                    ),
                ),
            ),
        )

        self.assertEqual(tool_run.status, ToolRunStatus.SUCCEEDED)
        metadata = tool_run.result.metadata
        self.assertEqual(metadata["tool"], "subagents")
        self.assertEqual(metadata["requester_session_key"], requester.id)
        self.assertEqual(metadata["returned_count"], 1)
        self.assertEqual(metadata["subagents"][0]["key"], child_session_key)
        self.assertEqual(metadata["subagents"][0]["depth"], 1)
        self.assertEqual(metadata["subagents"][0]["parent_session_key"], requester.id)
        self.assertEqual(metadata["subagents"][0]["requester_run_id"], "run-parent-3")
        self.assertEqual(metadata["subagents"][0]["inflight_run_count"], 1)
        self.assertEqual(
            metadata["subagents"][0]["latest_run"]["status"],
            OrchestrationRunStatus.QUEUED.value,
        )
        self.assertEqual(
            metadata["subagents"][0]["latest_run"]["id"],
            spawn_run.result.metadata["run_id"],
        )
        self.assertEqual(
            metadata["subagents"][0]["inflight_runs"][0]["id"],
            spawn_run.result.metadata["run_id"],
        )

    def test_subagents_lists_recursive_tree_and_run_state(self) -> None:
        requester = self.session_service.ensure_session(
            EnsureSessionInput(
                key="agent:assistant:main",
                agent_id="assistant",
            ),
        )

        first_spawn = asyncio.run(
            self.tool_service.execute(
                ExecuteToolInput(
                    tool_id="sessions_spawn",
                    arguments={"text": "first child task"},
                    execution_context=ToolExecutionContext(
                        attrs={
                            "session_key": requester.id,
                            "agent_id": "assistant",
                            "run_id": "run-parent-tree-1",
                        },
                    ),
                ),
            ),
        )
        self.assertEqual(first_spawn.status, ToolRunStatus.SUCCEEDED)
        child_session_key = first_spawn.result.metadata["child_session_key"]
        child_run_id = first_spawn.result.metadata["run_id"]

        second_spawn = asyncio.run(
            self.tool_service.execute(
                ExecuteToolInput(
                    tool_id="sessions_spawn",
                    arguments={"text": "grandchild task"},
                    execution_context=ToolExecutionContext(
                        attrs={
                            "session_key": child_session_key,
                            "agent_id": "assistant",
                            "run_id": "run-child-tree-1",
                        },
                    ),
                ),
            ),
        )
        self.assertEqual(second_spawn.status, ToolRunStatus.SUCCEEDED)
        grandchild_session_key = second_spawn.result.metadata["child_session_key"]
        grandchild_run_id = second_spawn.result.metadata["run_id"]

        tool_run = asyncio.run(
            self.tool_service.execute(
                ExecuteToolInput(
                    tool_id="subagents",
                    arguments={},
                    execution_context=ToolExecutionContext(
                        attrs={
                            "session_key": requester.id,
                            "agent_id": "assistant",
                        },
                    ),
                ),
            ),
        )

        self.assertEqual(tool_run.status, ToolRunStatus.SUCCEEDED)
        metadata = tool_run.result.metadata
        self.assertEqual(metadata["tool"], "subagents")
        self.assertEqual(metadata["requester_session_key"], requester.id)
        self.assertEqual(metadata["returned_count"], 2)
        self.assertEqual(metadata["available_count"], 2)

        child_payload = next(
            item for item in metadata["subagents"] if item["key"] == child_session_key
        )
        grandchild_payload = next(
            item
            for item in metadata["subagents"]
            if item["key"] == grandchild_session_key
        )

        self.assertEqual(child_payload["depth"], 1)
        self.assertEqual(child_payload["parent_session_key"], requester.id)
        self.assertEqual(child_payload["latest_run"]["id"], child_run_id)
        self.assertEqual(
            child_payload["latest_run"]["status"],
            OrchestrationRunStatus.QUEUED.value,
        )

        self.assertEqual(grandchild_payload["depth"], 2)
        self.assertEqual(grandchild_payload["parent_session_key"], child_session_key)
        self.assertEqual(grandchild_payload["latest_run"]["id"], grandchild_run_id)
        self.assertEqual(
            grandchild_payload["latest_run"]["status"],
            OrchestrationRunStatus.QUEUED.value,
        )
        self.assertEqual(grandchild_payload["inflight_run_count"], 1)

    def test_sessions_spawn_child_completion_enqueues_requester_followup(self) -> None:
        adapter = _SequentialTextAdapter(
            "child session complete",
            "parent follow-up complete",
        )
        self.llm_adapter_registry.register(
            LlmApiFamily.OPENAI_RESPONSES,
            adapter,
        )
        self._register_openai_llm_profile()
        self.agent_service.register_profile(
            RegisterAgentProfileInput(
                id="assistant",
                name="Assistant",
                instruction_policy=AgentInstructionPolicy(
                    system_prompt="Be helpful and concise.",
                ),
                llm_routing_policy=AgentLlmRoutingPolicy(
                    default_llm_id="openai.gpt-5.4-mini",
                ),
            ),
        )
        requester = self.session_service.ensure_session(
            EnsureSessionInput(
                key="agent:assistant:main",
                agent_id="assistant",
            ),
        )

        spawn_run = asyncio.run(
            self.tool_service.execute(
                ExecuteToolInput(
                    tool_id="sessions_spawn",
                    arguments={"text": "delegate this child task"},
                    execution_context=ToolExecutionContext(
                        attrs={
                            "session_key": requester.id,
                            "agent_id": "assistant",
                            "run_id": "run-parent-4",
                        },
                    ),
                ),
            ),
        )
        self.assertEqual(spawn_run.status, ToolRunStatus.SUCCEEDED)
        child_session_key = spawn_run.result.metadata["child_session_key"]

        child_completed = process_next_orchestration_assignment(self.container,
            worker_id="worker-1",
        )
        self.assertIsNotNone(child_completed)
        assert child_completed is not None
        self.assertEqual(child_completed.status, OrchestrationRunStatus.COMPLETED)
        self.assertEqual(child_completed.session_key, child_session_key)

        processed_continuation = None
        for _ in range(4):
            candidate = self.orchestration_scheduler_service.process_next_continuation(
                worker_id="scheduler-1",
            )
            self.assertIsNotNone(candidate)
            assert candidate is not None
            if candidate.continuation_kind.value == "sessions_spawn_followup":
                processed_continuation = candidate
                break
        self.assertIsNotNone(processed_continuation)

        requester_followup = process_next_orchestration_assignment(self.container,
            worker_id="worker-1",
        )
        self.assertIsNotNone(requester_followup)
        assert requester_followup is not None
        self.assertEqual(requester_followup.status, OrchestrationRunStatus.COMPLETED)
        self.assertEqual(requester_followup.session_key, requester.id)
        self.assertEqual(requester_followup.metadata["runtime_request_mode"], "recovery_resume")

        requester_messages = self.session_service.list_items(
            ListSessionItemsInput(
                session_key=requester.id,
                active_session_only=False,
            ),
        )
        self.assertEqual([item.role for item in requester_messages], ["user", "assistant"])
        self.assertIn(
            "Child session completed.",
            describe_content_for_text_fallback(requester_messages[0].content_payload),
        )
        self.assertIn(
            child_session_key,
            describe_content_for_text_fallback(requester_messages[0].content_payload),
        )
        self.assertEqual(
            describe_content_for_text_fallback(requester_messages[1].content_payload),
            "parent follow-up complete",
        )

    def test_session_status_reports_requester_followup_scheduling(self) -> None:
        adapter = _StaticTextAdapter(text="child session complete")
        self.llm_adapter_registry.register(
            LlmApiFamily.OPENAI_RESPONSES,
            adapter,
        )
        self._register_openai_llm_profile()
        self.agent_service.register_profile(
            RegisterAgentProfileInput(
                id="assistant",
                name="Assistant",
                instruction_policy=AgentInstructionPolicy(
                    system_prompt="Be helpful and concise.",
                ),
                llm_routing_policy=AgentLlmRoutingPolicy(
                    default_llm_id="openai.gpt-5.4-mini",
                ),
            ),
        )
        requester = self.session_service.ensure_session(
            EnsureSessionInput(
                key="agent:assistant:main",
                agent_id="assistant",
            ),
        )

        spawn_run = asyncio.run(
            self.tool_service.execute(
                ExecuteToolInput(
                    tool_id="sessions_spawn",
                    arguments={"text": "delegate this child task"},
                    execution_context=ToolExecutionContext(
                        attrs={
                            "session_key": requester.id,
                            "agent_id": "assistant",
                            "run_id": "run-parent-followup-1",
                        },
                    ),
                ),
            ),
        )
        self.assertEqual(spawn_run.status, ToolRunStatus.SUCCEEDED)
        child_session_key = spawn_run.result.metadata["child_session_key"]

        child_completed = process_next_orchestration_assignment(self.container,
            worker_id="worker-1",
        )
        self.assertIsNotNone(child_completed)
        assert child_completed is not None
        self.assertEqual(child_completed.status, OrchestrationRunStatus.COMPLETED)

        processed_continuation = None
        for _ in range(4):
            candidate = self.orchestration_scheduler_service.process_next_continuation(
                worker_id="scheduler-1",
            )
            self.assertIsNotNone(candidate)
            assert candidate is not None
            if candidate.continuation_kind.value == "sessions_spawn_followup":
                processed_continuation = candidate
                break
        self.assertIsNotNone(processed_continuation)

        tool_run = asyncio.run(
            self.tool_service.execute(
                ExecuteToolInput(
                    tool_id="session_status",
                    arguments={},
                    execution_context=ToolExecutionContext(
                        attrs={
                            "session_key": requester.id,
                            "agent_id": "assistant",
                        },
                    ),
                ),
            ),
        )

        self.assertEqual(tool_run.status, ToolRunStatus.SUCCEEDED)
        metadata = tool_run.result.metadata
        requester_tree = metadata["requester_tree"]
        self.assertEqual(
            requester_tree["subagent_tree"]["child_session_count"],
            1,
        )
        self.assertEqual(
            requester_tree["subagent_tree"]["inflight_child_session_count"],
            0,
        )
        self.assertEqual(
            requester_tree["subagent_tree"]["inflight_child_run_count"],
            0,
        )
        self.assertEqual(
            requester_tree["followup"]["run_count"],
            1,
        )
        self.assertEqual(
            requester_tree["followup"]["inflight_run_count"],
            1,
        )
        self.assertEqual(
            requester_tree["followup"]["latest_run"]["status"],
            OrchestrationRunStatus.QUEUED.value,
        )
        self.assertEqual(
            requester_tree["followup"]["latest_run"]["child_session_key"],
            child_session_key,
        )
        rendered = tool_run.result.blocks[0]["text"]
        self.assertIn("## Follow-up Scheduling", rendered)
        self.assertIn("latest_followup_status: queued", rendered)

    def test_sessions_stop_cancels_requester_child_session_tree(self) -> None:
        requester = self.session_service.ensure_session(
            EnsureSessionInput(
                key="agent:assistant:main",
                agent_id="assistant",
            ),
        )

        first_spawn = asyncio.run(
            self.tool_service.execute(
                ExecuteToolInput(
                    tool_id="sessions_spawn",
                    arguments={"text": "first child task"},
                    execution_context=ToolExecutionContext(
                        attrs={
                            "session_key": requester.id,
                            "agent_id": "assistant",
                            "run_id": "run-parent-stop-1",
                        },
                    ),
                ),
            ),
        )
        self.assertEqual(first_spawn.status, ToolRunStatus.SUCCEEDED)
        child_session_key = first_spawn.result.metadata["child_session_key"]
        child_run_id = first_spawn.result.metadata["run_id"]

        second_spawn = asyncio.run(
            self.tool_service.execute(
                ExecuteToolInput(
                    tool_id="sessions_spawn",
                    arguments={"text": "grandchild task"},
                    execution_context=ToolExecutionContext(
                        attrs={
                            "session_key": child_session_key,
                            "agent_id": "assistant",
                            "run_id": "run-child-stop-1",
                        },
                    ),
                ),
            ),
        )
        self.assertEqual(second_spawn.status, ToolRunStatus.SUCCEEDED)
        grandchild_session_key = second_spawn.result.metadata["child_session_key"]
        grandchild_run_id = second_spawn.result.metadata["run_id"]

        tool_run = asyncio.run(
            self.tool_service.execute(
                ExecuteToolInput(
                    tool_id="sessions_stop",
                    arguments={"reason": "user stopped requester"},
                    execution_context=ToolExecutionContext(
                        attrs={
                            "session_key": requester.id,
                            "agent_id": "assistant",
                        },
                    ),
                ),
            ),
        )

        self.assertEqual(tool_run.status, ToolRunStatus.SUCCEEDED)
        metadata = tool_run.result.metadata
        self.assertEqual(metadata["tool"], "sessions_stop")
        self.assertEqual(metadata["requester_session_key"], requester.id)
        self.assertEqual(metadata["cancelled_run_count"], 2)
        self.assertEqual(metadata["cancelled_tool_run_count"], 0)
        self.assertEqual(metadata["terminal_run_count"], 0)
        self.assertEqual(
            metadata["session_keys"],
            [requester.id, child_session_key, grandchild_session_key],
        )
        self.assertEqual(
            set(metadata["cancelled_run_ids"]),
            {child_run_id, grandchild_run_id},
        )
        self.assertEqual(
            self.orchestration_run_query_service.get_run(child_run_id).status,
            OrchestrationRunStatus.CANCELLED,
        )
        self.assertEqual(
            self.orchestration_run_query_service.get_run(grandchild_run_id).status,
            OrchestrationRunStatus.CANCELLED,
        )
        self.assertIn("# Session Stop", tool_run.result.blocks[0]["text"])

    def test_sessions_yield_returns_control_metadata(self) -> None:
        session = self.session_service.ensure_session(
            EnsureSessionInput(
                key="agent:assistant:main",
                agent_id="assistant",
            ),
        )

        tool_run = asyncio.run(
            self.tool_service.execute(
                ExecuteToolInput(
                    tool_id="sessions_yield",
                    arguments={"reason": "wait for child session"},
                    execution_context=ToolExecutionContext(
                        attrs={
                            "session_key": session.id,
                            "run_id": "run-yield-1",
                        },
                    ),
                ),
            ),
        )

        self.assertEqual(tool_run.status, ToolRunStatus.SUCCEEDED)
        metadata = tool_run.result.metadata
        self.assertEqual(metadata["tool"], "sessions_yield")
        self.assertEqual(metadata["run_id"], "run-yield-1")
        self.assertTrue(metadata["yield_requested"])
        self.assertEqual(metadata["yield_reason"], "wait for child session")
        self.assertEqual(
            tool_run.result.metadata["session_control"],
            {
                "yield": True,
                "reason": "wait for child session",
            },
        )
