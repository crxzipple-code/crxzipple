from __future__ import annotations

import unittest

from crxzipple.modules.llm.domain import LlmMessageRole
from crxzipple.modules.orchestration.application.prompt_transcript import (
    build_prompt_transcript,
)
from crxzipple.modules.session.domain import SessionMessage, SessionMessageKind


class PromptTranscriptTestCase(unittest.TestCase):
    def test_filters_unresolved_function_call_messages(self) -> None:
        transcript = build_prompt_transcript(
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

    def test_keeps_completed_function_call_messages_in_transcript(self) -> None:
        transcript = build_prompt_transcript(
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

    def test_prunes_non_text_attachments_from_processed_history(self) -> None:
        transcript = build_prompt_transcript(
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
        transcript = build_prompt_transcript(
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
        transcript = build_prompt_transcript(
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
        transcript = build_prompt_transcript(
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
                        "tool_name": "browser",
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
                        "tool_name": "browser",
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
        transcript = build_prompt_transcript(
            (
                SessionMessage(
                    id="msg-1",
                    session_key="session",
                    session_id="active",
                    sequence_no=1,
                    role="tool",
                    kind=SessionMessageKind.TOOL_RESULT,
                    content_payload={
                        "tool_name": "browser",
                        "tool_call_id": "call-1",
                        "status": "succeeded",
                        "details": {"secret": "should not be shown"},
                    },
                    metadata={
                        "tool_call_id": "call-1",
                        "tool_name": "browser",
                    },
                ),
            ),
        )

        self.assertEqual(
            transcript.messages[0].content,
            [{"type": "text", "text": "Tool completed."}],
        )

    def test_truncates_to_recent_budget_while_preserving_tool_call_pairs(self) -> None:
        transcript = build_prompt_transcript(
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
                        "name": "browser",
                        "arguments": {"kind": "snapshot"},
                    },
                    metadata={
                        "tool_call_id": "call-1",
                        "tool_name": "browser",
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
                        "tool_name": "browser",
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
