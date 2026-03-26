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
                    content="hello",
                ),
            ),
        )

        self.assertEqual(transcript.message_count, 1)
        self.assertEqual(len(transcript.messages), 1)
        self.assertEqual(transcript.messages[0].role, LlmMessageRole.USER)
        self.assertEqual(transcript.messages[0].content, "hello")

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
                    content="done",
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


if __name__ == "__main__":
    unittest.main()
