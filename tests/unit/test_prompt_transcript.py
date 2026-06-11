from __future__ import annotations

import unittest

from crxzipple.modules.llm.domain import LlmMessageRole
from crxzipple.modules.orchestration.application.prompt_transcript import (
    build_current_run_prompt_window,
    build_memory_flush_prompt_transcript,
)
from crxzipple.modules.orchestration.application.prompting import (
    PromptMode,
    PromptReport,
)
from crxzipple.modules.session.domain import SessionMessage, SessionMessageKind
from crxzipple.modules.tool.application.result_envelope import (
    TOOL_RESULT_ENVELOPE_METADATA_KEY,
)


class PromptTranscriptTestCase(unittest.TestCase):
    def test_prompt_report_payload_includes_tool_result_stats(self) -> None:
        report = PromptReport(
            mode=PromptMode.NORMAL_TURN,
            context_blocks=(),
            context_budget_source="test",
            context_budget_chars=1000,
            context_budget_estimated_tokens=250,
            llm_context_window_tokens=2000,
            context_chars=10,
            context_estimated_tokens=3,
            transcript_message_count=2,
            transcript_chars=50,
            transcript_estimated_tokens=13,
            transcript_tool_result_stats={
                "tool_result_message_count": 1,
                "compacted_result_count": 1,
                "omitted_chars": 22400,
            },
        )

        payload = report.to_payload()

        self.assertEqual(
            payload["transcript"]["tool_result_stats"],
            {
                "tool_result_message_count": 1,
                "compacted_result_count": 1,
                "omitted_chars": 22400,
            },
        )

    def test_filters_unresolved_function_call_messages(self) -> None:
        transcript = build_current_run_prompt_window(
            (
                SessionMessage(
                    id="msg-1",
                    session_key="session",
                    session_id="active",
                    sequence_no=1,
                    role="assistant",
                    kind=SessionMessageKind.MESSAGE,
                    content_payload={
                        "type": "function_call",
                        "call_id": "call-1",
                        "name": "search_docs",
                        "arguments": {"query": "ddd"},
                    },
                    metadata={
                        "tool_call_id": "call-1",
                        "tool_name": "search_docs",
                    },
                ),
                SessionMessage(
                    id="msg-2",
                    session_key="session",
                    session_id="active",
                    sequence_no=2,
                    role="user",
                    content_payload={"blocks": [{"type": "text", "text": "hello"}]},
                ),
            ),
        )

        self.assertEqual(transcript.message_count, 1)
        self.assertEqual(len(transcript.messages), 1)
        self.assertEqual(transcript.messages[0].role, LlmMessageRole.USER)
        self.assertEqual(
            transcript.messages[0].content,
            [{"type": "text", "text": "hello"}],
        )

    def test_keeps_assistant_progress_text_before_function_call(self) -> None:
        transcript = build_current_run_prompt_window(
            (
                SessionMessage(
                    id="msg-progress",
                    session_key="session",
                    session_id="active",
                    sequence_no=1,
                    role="assistant",
                    kind=SessionMessageKind.MESSAGE,
                    content_payload={
                        "blocks": [
                            {
                                "type": "text",
                                "text": "我先检查页面状态。",
                            },
                        ],
                        "text": "我先检查页面状态。",
                        "finish_reason": "tool_calls",
                    },
                    source_kind="llm_invocation",
                    source_id="invocation-progress",
                ),
                SessionMessage(
                    id="msg-call",
                    session_key="session",
                    session_id="active",
                    sequence_no=2,
                    role="assistant",
                    kind=SessionMessageKind.MESSAGE,
                    content_payload={
                        "type": "function_call",
                        "call_id": "call-1",
                        "name": "search_docs",
                        "arguments": {"query": "ddd"},
                    },
                    metadata={
                        "tool_call_id": "call-1",
                        "tool_name": "search_docs",
                    },
                ),
                SessionMessage(
                    id="msg-tool",
                    session_key="session",
                    session_id="active",
                    sequence_no=3,
                    role="tool",
                    kind=SessionMessageKind.TOOL_RESULT,
                    content_payload={"blocks": [{"type": "text", "text": "done"}]},
                    metadata={
                        "tool_call_id": "call-1",
                        "tool_name": "search_docs",
                    },
                ),
            ),
        )

        self.assertEqual(transcript.message_count, 3)
        self.assertEqual(transcript.messages[0].role, LlmMessageRole.ASSISTANT)
        self.assertEqual(
            transcript.messages[0].content,
            [{"type": "text", "text": "我先检查页面状态。"}],
        )
        self.assertEqual(transcript.messages[1].role, LlmMessageRole.ASSISTANT)
        self.assertEqual(transcript.messages[1].tool_call_id, "call-1")
        self.assertEqual(transcript.messages[2].role, LlmMessageRole.TOOL)

    def test_keeps_completed_function_call_messages_in_transcript(self) -> None:
        transcript = build_current_run_prompt_window(
            (
                SessionMessage(
                    id="msg-1",
                    session_key="session",
                    session_id="active",
                    sequence_no=1,
                    role="assistant",
                    kind=SessionMessageKind.MESSAGE,
                    content_payload={
                        "type": "function_call",
                        "call_id": "call-1",
                        "name": "search_docs",
                        "arguments": {"query": "ddd"},
                    },
                    metadata={
                        "tool_call_id": "call-1",
                        "tool_name": "search_docs",
                    },
                ),
                SessionMessage(
                    id="msg-2",
                    session_key="session",
                    session_id="active",
                    sequence_no=2,
                    role="tool",
                    kind=SessionMessageKind.TOOL_RESULT,
                    content_payload={"blocks": [{"type": "text", "text": "done"}]},
                    metadata={
                        "tool_call_id": "call-1",
                        "tool_name": "search_docs",
                    },
                ),
            ),
        )

        self.assertEqual(transcript.message_count, 2)
        self.assertEqual(transcript.messages[0].role, LlmMessageRole.ASSISTANT)
        self.assertIsInstance(transcript.messages[0].content, dict)
        assert isinstance(transcript.messages[0].content, dict)
        self.assertEqual(transcript.messages[0].content["type"], "function_call")
        self.assertEqual(transcript.messages[1].role, LlmMessageRole.TOOL)
        self.assertGreater(transcript.chars, 0)
        self.assertGreater(transcript.estimated_tokens, 0)

    def test_execution_chain_completed_tool_calls_override_session_pairs(self) -> None:
        transcript = build_current_run_prompt_window(
            (
                SessionMessage(
                    id="msg-1",
                    session_key="session",
                    session_id="active",
                    sequence_no=1,
                    role="assistant",
                    kind=SessionMessageKind.MESSAGE,
                    content_payload={
                        "type": "function_call",
                        "call_id": "call-old",
                        "name": "search_docs",
                        "arguments": {"query": "old"},
                    },
                    metadata={
                        "tool_call_id": "call-old",
                        "tool_name": "search_docs",
                    },
                ),
                SessionMessage(
                    id="msg-2",
                    session_key="session",
                    session_id="active",
                    sequence_no=2,
                    role="tool",
                    kind=SessionMessageKind.TOOL_RESULT,
                    content_payload={"blocks": [{"type": "text", "text": "old"}]},
                    metadata={
                        "tool_call_id": "call-old",
                        "tool_name": "search_docs",
                    },
                ),
                SessionMessage(
                    id="msg-3",
                    session_key="session",
                    session_id="active",
                    sequence_no=3,
                    role="assistant",
                    kind=SessionMessageKind.MESSAGE,
                    content_payload={
                        "type": "function_call",
                        "call_id": "call-current",
                        "name": "search_docs",
                        "arguments": {"query": "current"},
                    },
                    metadata={
                        "tool_call_id": "call-current",
                        "tool_name": "search_docs",
                    },
                ),
                SessionMessage(
                    id="msg-4",
                    session_key="session",
                    session_id="active",
                    sequence_no=4,
                    role="tool",
                    kind=SessionMessageKind.TOOL_RESULT,
                    content_payload={"blocks": [{"type": "text", "text": "current"}]},
                    metadata={
                        "tool_call_id": "call-current",
                        "tool_name": "search_docs",
                    },
                ),
            ),
            completed_tool_call_ids=("call-current",),
        )

        self.assertEqual(
            [message.tool_call_id for message in transcript.messages],
            ["call-current", "call-current"],
        )

    def test_consumed_frontier_keeps_current_inbound_and_latest_tool_protocol(self) -> None:
        transcript = build_current_run_prompt_window(
            (
                SessionMessage(
                    id="msg-user",
                    session_key="session",
                    session_id="active",
                    sequence_no=1,
                    role="user",
                    content_payload={"blocks": [{"type": "text", "text": "please work"}]},
                ),
                SessionMessage(
                    id="msg-old-call",
                    session_key="session",
                    session_id="active",
                    sequence_no=2,
                    role="assistant",
                    kind=SessionMessageKind.MESSAGE,
                    content_payload={
                        "type": "function_call",
                        "call_id": "call-old",
                        "name": "context_tree.expand",
                        "arguments": {"node_id": "tools"},
                    },
                    metadata={
                        "tool_call_id": "call-old",
                        "tool_name": "context_tree.expand",
                    },
                ),
                SessionMessage(
                    id="msg-old-result",
                    session_key="session",
                    session_id="active",
                    sequence_no=3,
                    role="tool",
                    kind=SessionMessageKind.TOOL_RESULT,
                    content_payload={"blocks": [{"type": "text", "text": "old"}]},
                    metadata={
                        "tool_call_id": "call-old",
                        "tool_name": "context_tree.expand",
                    },
                ),
                SessionMessage(
                    id="msg-current-call",
                    session_key="session",
                    session_id="active",
                    sequence_no=4,
                    role="assistant",
                    kind=SessionMessageKind.MESSAGE,
                    content_payload={
                        "type": "function_call",
                        "call_id": "call-current",
                        "name": "echo",
                        "arguments": {"text": "now"},
                    },
                    metadata={
                        "tool_call_id": "call-current",
                        "tool_name": "echo",
                    },
                ),
                SessionMessage(
                    id="msg-current-result",
                    session_key="session",
                    session_id="active",
                    sequence_no=5,
                    role="tool",
                    kind=SessionMessageKind.TOOL_RESULT,
                    content_payload={"blocks": [{"type": "text", "text": "now"}]},
                    metadata={
                        "tool_call_id": "call-current",
                        "tool_name": "echo",
                    },
                ),
            ),
            consumed_through_sequence_no=3,
            preserve_message_ids=("msg-user",),
        )

        self.assertEqual(
            [
                message.metadata.get("session_message_id")
                for message in transcript.messages
            ],
            ["msg-user", "msg-current-call", "msg-current-result"],
        )
        self.assertEqual(
            [message.tool_call_id for message in transcript.messages[1:]],
            ["call-current", "call-current"],
        )

    def test_consumed_frontier_does_not_keep_orphan_function_call(self) -> None:
        transcript = build_current_run_prompt_window(
            (
                SessionMessage(
                    id="msg-user",
                    session_key="session",
                    session_id="active",
                    sequence_no=1,
                    role="user",
                    content_payload={"blocks": [{"type": "text", "text": "please work"}]},
                ),
                SessionMessage(
                    id="msg-call",
                    session_key="session",
                    session_id="active",
                    sequence_no=4,
                    role="assistant",
                    kind=SessionMessageKind.MESSAGE,
                    content_payload={
                        "type": "function_call",
                        "call_id": "call-current",
                        "name": "echo",
                        "arguments": {"text": "now"},
                    },
                    metadata={
                        "tool_call_id": "call-current",
                        "tool_name": "echo",
                    },
                ),
                SessionMessage(
                    id="msg-result",
                    session_key="session",
                    session_id="active",
                    sequence_no=5,
                    role="tool",
                    kind=SessionMessageKind.TOOL_RESULT,
                    content_payload={"blocks": [{"type": "text", "text": "now"}]},
                    metadata={
                        "tool_call_id": "call-current",
                        "tool_name": "echo",
                    },
                ),
            ),
            completed_tool_call_ids=("call-current",),
            consumed_through_sequence_no=5,
            preserve_message_ids=("msg-user",),
        )

        self.assertEqual(transcript.message_count, 1)
        self.assertEqual(transcript.messages[0].role, LlmMessageRole.USER)

    def test_prunes_non_text_attachments_from_processed_history(self) -> None:
        transcript = build_current_run_prompt_window(
            (
                SessionMessage(
                    id="msg-1",
                    session_key="session",
                    session_id="active",
                    sequence_no=1,
                    role="user",
                    content_payload={
                        "blocks": [
                            {"type": "text", "text": "look at this"},
                            {
                                "type": "image",
                                "data": "aGVsbG8=",
                                "mime_type": "image/png",
                            },
                        ],
                    },
                ),
                SessionMessage(
                    id="msg-2",
                    session_key="session",
                    session_id="active",
                    sequence_no=2,
                    role="assistant",
                    content_payload={"blocks": [{"type": "text", "text": "done"}]},
                ),
            ),
        )

        self.assertEqual(
            transcript.messages[0].content,
            [
                {"type": "text", "text": "look at this"},
                {
                    "type": "text",
                    "text": "[image data removed - already processed by model]",
                },
            ],
        )

    def test_prunes_ref_attachments_from_processed_history(self) -> None:
        transcript = build_current_run_prompt_window(
            (
                SessionMessage(
                    id="msg-1",
                    session_key="session",
                    session_id="active",
                    sequence_no=1,
                    role="user",
                    content_payload={
                        "blocks": [
                            {"type": "text", "text": "look at this too"},
                            {
                                "type": "image_ref",
                                "artifact_id": "img_123",
                                "mime_type": "image/png",
                            },
                        ],
                    },
                ),
                SessionMessage(
                    id="msg-2",
                    session_key="session",
                    session_id="active",
                    sequence_no=2,
                    role="assistant",
                    content_payload={"blocks": [{"type": "text", "text": "done"}]},
                ),
            ),
        )

        self.assertEqual(
            transcript.messages[0].content,
            [
                {"type": "text", "text": "look at this too"},
                {
                    "type": "text",
                    "text": "[image data removed - already processed by model]",
                },
            ],
        )

    def test_keeps_latest_non_text_attachments_for_current_turn(self) -> None:
        transcript = build_current_run_prompt_window(
            (
                SessionMessage(
                    id="msg-1",
                    session_key="session",
                    session_id="active",
                    sequence_no=1,
                    role="assistant",
                    content_payload={"blocks": [{"type": "text", "text": "show me"}]},
                ),
                SessionMessage(
                    id="msg-2",
                    session_key="session",
                    session_id="active",
                    sequence_no=2,
                    role="user",
                    content_payload={
                        "blocks": [
                            {
                                "type": "image",
                                "data": "aGVsbG8=",
                                "mime_type": "image/png",
                            },
                        ],
                    },
                ),
            ),
        )

        self.assertEqual(
            transcript.messages[1].content,
            [
                {
                    "type": "image",
                    "data": "aGVsbG8=",
                    "mime_type": "image/png",
                },
            ],
        )

    def test_keeps_latest_tool_result_attachments_for_current_turn(self) -> None:
        transcript = build_current_run_prompt_window(
            (
                SessionMessage(
                    id="msg-1",
                    session_key="session",
                    session_id="active",
                    sequence_no=1,
                    role="assistant",
                    content_payload={"blocks": [{"type": "text", "text": "working"}]},
                ),
                SessionMessage(
                    id="msg-2",
                    session_key="session",
                    session_id="active",
                    sequence_no=2,
                    role="tool",
                    kind=SessionMessageKind.TOOL_RESULT,
                    content_payload={
                        "tool_name": "browser.screenshot",
                        "tool_call_id": "call-1",
                        "status": "succeeded",
                        "details": {"ok": True},
                        "content": [
                            {
                                "type": "text",
                                "text": "Browser screenshot captured.",
                            },
                            {
                                "type": "image",
                                "data": "aGVsbG8=",
                                "mime_type": "image/png",
                            },
                        ],
                        "text": "Browser screenshot captured.",
                    },
                    metadata={
                        "tool_call_id": "call-1",
                        "tool_name": "browser.screenshot",
                    },
                ),
            ),
        )

        self.assertEqual(
            transcript.messages[1].content,
            [
                {"type": "text", "text": "Browser screenshot captured."},
                {
                    "type": "image",
                    "data": "aGVsbG8=",
                    "mime_type": "image/png",
                },
            ],
        )

    def test_tool_messages_without_content_do_not_fallback_to_details(self) -> None:
        transcript = build_current_run_prompt_window(
            (
                SessionMessage(
                    id="msg-1",
                    session_key="session",
                    session_id="active",
                    sequence_no=1,
                    role="tool",
                    kind=SessionMessageKind.TOOL_RESULT,
                    content_payload={
                        "tool_name": "browser.screenshot",
                        "tool_call_id": "call-1",
                        "status": "succeeded",
                        "details": {"secret": "should not be shown"},
                    },
                    metadata={
                        "tool_call_id": "call-1",
                        "tool_name": "browser.screenshot",
                    },
                ),
            ),
        )

        self.assertEqual(
            transcript.messages[0].content,
            [{"type": "text", "text": "Tool completed."}],
        )

    def test_tool_result_envelope_compacts_provider_transcript_content(self) -> None:
        transcript = build_current_run_prompt_window(
            (
                SessionMessage(
                    id="msg-1",
                    session_key="session",
                    session_id="active",
                    sequence_no=1,
                    role="assistant",
                    kind=SessionMessageKind.MESSAGE,
                    content_payload={
                        "type": "function_call",
                        "call_id": "call-1",
                        "name": "debug.large_result",
                        "arguments": {},
                    },
                    metadata={
                        "tool_call_id": "call-1",
                        "tool_name": "debug.large_result",
                    },
                ),
                SessionMessage(
                    id="msg-2",
                    session_key="session",
                    session_id="active",
                    sequence_no=2,
                    role="tool",
                    kind=SessionMessageKind.TOOL_RESULT,
                    content_payload={
                        "tool_name": "debug.large_result",
                        "tool_call_id": "call-1",
                        "status": "succeeded",
                        "content": [
                            {
                                "type": "text",
                                "text": "RAW_SECRET_" + ("x" * 24000),
                            },
                        ],
                        "metadata": {
                            "artifact_ids": ["artifact-large"],
                            "browser_evidence": {
                                "evidence_path_key": "network_truth",
                                "evidence_path_title": "Trace Network Truth",
                                "evidence_path_tools": [
                                    "browser.network.inspect",
                                    "browser.network.fetch_as_page",
                                    "browser.network.replay_request",
                                ],
                            },
                            TOOL_RESULT_ENVELOPE_METADATA_KEY: {
                                "status": "ok",
                                "summary": "Large result externalized.",
                                "key_facts": {"original_text_chars": 24011},
                                "warnings": [],
                                "evidence_refs": ["artifact-large"],
                                "read_handles": [
                                    {
                                        "kind": "artifact",
                                        "artifact_id": "artifact-large",
                                    },
                                ],
                                "omitted_count": 1,
                                "omitted_chars": 22400,
                                "truncated": True,
                            },
                        },
                    },
                    metadata={
                        "tool_call_id": "call-1",
                        "tool_name": "debug.large_result",
                    },
                ),
            ),
        )

        tool_message = transcript.messages[1]
        assert isinstance(tool_message.content, list)
        text = tool_message.content[0]["text"]
        self.assertIn("omitted_from_provider_transcript", text)
        self.assertIn("summary: Large result externalized.", text)
        self.assertIn("evidence_path: network_truth (Trace Network Truth)", text)
        self.assertIn("artifact_refs: artifact-large", text)
        self.assertIn("omitted_chars: 22400", text)
        self.assertNotIn("RAW_SECRET_", text)
        self.assertEqual(
            transcript.tool_result_stats,
            {
                "tool_result_message_count": 1,
                "compacted_result_count": 1,
                "omitted_chars": 22400,
                "omitted_count": 1,
                "artifact_ref_count": 1,
                "read_handle_count": 1,
            },
        )

    def test_legacy_artifact_tool_result_compacts_provider_transcript_content(self) -> None:
        transcript = build_current_run_prompt_window(
            (
                SessionMessage(
                    id="msg-1",
                    session_key="session",
                    session_id="active",
                    sequence_no=1,
                    role="assistant",
                    kind=SessionMessageKind.MESSAGE,
                    content_payload={
                        "type": "function_call",
                        "call_id": "call-1",
                        "name": "browser.network.fetch",
                        "arguments": {},
                    },
                    metadata={
                        "tool_call_id": "call-1",
                        "tool_name": "browser.network.fetch",
                    },
                ),
                SessionMessage(
                    id="msg-2",
                    session_key="session",
                    session_id="active",
                    sequence_no=2,
                    role="tool",
                    kind=SessionMessageKind.TOOL_RESULT,
                    content_payload={
                        "tool_name": "browser.network.fetch",
                        "tool_call_id": "call-1",
                        "status": "succeeded",
                        "content": [
                            {
                                "type": "text",
                                "text": "BODY_SECRET_" + ("x" * 1000),
                            },
                        ],
                        "details": {
                            "endpoint": "/portal/v3/shopping/briefInfo",
                            "method": "POST",
                            "body_removed_from_details": True,
                        },
                        "metadata": {
                            "artifact_ids": ["artifact-body"],
                            "browser_evidence": {
                                "evidence_path_key": "network_truth",
                                "evidence_path_title": "Trace Network Truth",
                                "evidence_path_tools": [
                                    "browser.network.inspect",
                                    "browser.network.fetch_as_page",
                                    "browser.network.replay_request",
                                ],
                            },
                        },
                    },
                    metadata={
                        "tool_call_id": "call-1",
                        "tool_name": "browser.network.fetch",
                    },
                ),
            ),
        )

        tool_message = transcript.messages[1]
        assert isinstance(tool_message.content, list)
        text = tool_message.content[0]["text"]
        self.assertIn("omitted_from_provider_transcript", text)
        self.assertIn("endpoint: /portal/v3/shopping/briefInfo", text)
        self.assertIn("method: POST", text)
        self.assertIn("evidence_path: network_truth (Trace Network Truth)", text)
        self.assertIn("artifact_refs: artifact-body", text)
        self.assertNotIn("BODY_SECRET_", text)

    def test_truncates_to_recent_budget_while_preserving_tool_call_pairs(self) -> None:
        transcript = build_memory_flush_prompt_transcript(
            (
                SessionMessage(
                    id="msg-1",
                    session_key="session",
                    session_id="active",
                    sequence_no=1,
                    role="user",
                    content_payload={
                        "blocks": [{"type": "text", "text": "A" * 500}],
                    },
                ),
                SessionMessage(
                    id="msg-2",
                    session_key="session",
                    session_id="active",
                    sequence_no=2,
                    role="assistant",
                    kind=SessionMessageKind.MESSAGE,
                    content_payload={
                        "type": "function_call",
                        "call_id": "call-1",
                        "name": "browser.snapshot",
                        "arguments": {"format": "interactive"},
                    },
                    metadata={
                        "tool_call_id": "call-1",
                        "tool_name": "browser.snapshot",
                    },
                ),
                SessionMessage(
                    id="msg-3",
                    session_key="session",
                    session_id="active",
                    sequence_no=3,
                    role="tool",
                    kind=SessionMessageKind.TOOL_RESULT,
                    content_payload={"blocks": [{"type": "text", "text": "done"}]},
                    metadata={
                        "tool_call_id": "call-1",
                        "tool_name": "browser.snapshot",
                    },
                ),
                SessionMessage(
                    id="msg-4",
                    session_key="session",
                    session_id="active",
                    sequence_no=4,
                    role="user",
                    content_payload={
                        "blocks": [{"type": "text", "text": "continue"}],
                    },
                ),
            ),
            max_chars=120,
        )

        self.assertEqual(
            [message.role for message in transcript.messages],
            [
                LlmMessageRole.ASSISTANT,
                LlmMessageRole.TOOL,
                LlmMessageRole.USER,
            ],
        )
        self.assertNotIn("A" * 50, str(transcript.messages[0].content))
        self.assertLess(transcript.chars, 200)


if __name__ == "__main__":
    unittest.main()
