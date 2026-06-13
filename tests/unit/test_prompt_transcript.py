from __future__ import annotations

import unittest

from crxzipple.modules.llm.domain import LlmMessageRole
from crxzipple.modules.orchestration.application.prompt_transcript import (
    build_model_visible_session_item_prompt_window,
)
from crxzipple.modules.orchestration.application.prompting import (
    PromptMode,
    PromptReport,
)
from crxzipple.modules.session.domain import (
    SessionItem,
    SessionItemKind,
    SessionItemVisibility,
)
from crxzipple.modules.tool.application.result_envelope import (
    TOOL_RESULT_ENVELOPE_METADATA_KEY,
)


def _item(
    item_id: str,
    *,
    sequence_no: int,
    kind: SessionItemKind,
    role: str | None,
    content_payload: dict[str, object],
    call_id: str | None = None,
    tool_name: str | None = None,
    model_visible: bool = True,
) -> SessionItem:
    return SessionItem(
        id=item_id,
        session_key="session",
        session_id="active",
        sequence_no=sequence_no,
        role=role,
        kind=kind,
        content_payload=content_payload,
        visibility=SessionItemVisibility(
            model_visible=model_visible,
            trace_visible=True,
        ),
        call_id=call_id,
        tool_name=tool_name,
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
                "tool_result_item_count": 1,
                "compacted_result_count": 1,
                "omitted_chars": 22400,
            },
        )

        payload = report.to_payload()

        self.assertEqual(
            payload["transcript"]["tool_result_stats"],
            {
                "tool_result_item_count": 1,
                "compacted_result_count": 1,
                "omitted_chars": 22400,
            },
        )

    def test_replays_assistant_progress_tool_call_and_tool_result_items(self) -> None:
        transcript = build_model_visible_session_item_prompt_window(
            (
                _item(
                    "item-progress",
                    sequence_no=1,
                    kind=SessionItemKind.ASSISTANT_MESSAGE,
                    role="assistant",
                    content_payload={
                        "blocks": [
                            {"type": "text", "text": "I will inspect the page."},
                        ],
                        "text": "I will inspect the page.",
                        "finish_reason": "tool_calls",
                    },
                ),
                _item(
                    "item-call",
                    sequence_no=2,
                    kind=SessionItemKind.TOOL_CALL,
                    role="assistant",
                    content_payload={
                        "type": "function_call",
                        "call_id": "call-1",
                        "tool_name": "search_docs",
                        "arguments": {"query": "ddd"},
                    },
                    call_id="call-1",
                    tool_name="search_docs",
                ),
                _item(
                    "item-result",
                    sequence_no=3,
                    kind=SessionItemKind.TOOL_RESULT,
                    role="tool",
                    content_payload={"blocks": [{"type": "text", "text": "done"}]},
                    call_id="call-1",
                    tool_name="search_docs",
                ),
            ),
        )

        self.assertEqual(transcript.message_count, 3)
        self.assertEqual(transcript.messages[0].role, LlmMessageRole.ASSISTANT)
        self.assertEqual(
            transcript.messages[0].content,
            [{"type": "text", "text": "I will inspect the page."}],
        )
        self.assertEqual(transcript.messages[1].role, LlmMessageRole.ASSISTANT)
        self.assertEqual(transcript.messages[1].tool_call_id, "call-1")
        self.assertEqual(transcript.messages[2].role, LlmMessageRole.TOOL)
        self.assertEqual(transcript.messages[2].name, "search_docs")

    def test_excludes_non_model_visible_items(self) -> None:
        transcript = build_model_visible_session_item_prompt_window(
            (
                _item(
                    "item-hidden",
                    sequence_no=1,
                    kind=SessionItemKind.REASONING,
                    role="assistant",
                    content_payload={"text": "hidden reasoning"},
                    model_visible=False,
                ),
                _item(
                    "item-user",
                    sequence_no=2,
                    kind=SessionItemKind.USER_MESSAGE,
                    role="user",
                    content_payload={"blocks": [{"type": "text", "text": "hello"}]},
                ),
            ),
        )

        self.assertEqual(transcript.message_count, 1)
        self.assertEqual(transcript.messages[0].role, LlmMessageRole.USER)
        self.assertEqual(
            transcript.messages[0].metadata["session_item_id"],
            "item-user",
        )

    def test_tool_result_envelope_compacts_provider_transcript_content(self) -> None:
        transcript = build_model_visible_session_item_prompt_window(
            (
                _item(
                    "item-call",
                    sequence_no=1,
                    kind=SessionItemKind.TOOL_CALL,
                    role="assistant",
                    content_payload={
                        "type": "function_call",
                        "call_id": "call-1",
                        "tool_name": "browser.network.fetch",
                        "arguments": {},
                    },
                    call_id="call-1",
                    tool_name="browser.network.fetch",
                ),
                _item(
                    "item-tool",
                    sequence_no=2,
                    kind=SessionItemKind.TOOL_RESULT,
                    role="tool",
                    call_id="call-1",
                    tool_name="browser.network.fetch",
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
                            },
                            TOOL_RESULT_ENVELOPE_METADATA_KEY: {
                                "truncated": True,
                                "summary": "large response captured",
                                "omitted_chars": 1000,
                            },
                        },
                    },
                ),
            ),
        )

        tool_message = transcript.messages[1]
        assert isinstance(tool_message.content, list)
        text = tool_message.content[0]["text"]
        self.assertIn("omitted_from_provider_transcript", text)
        self.assertIn("summary: large response captured", text)
        self.assertIn("evidence_path: network_truth", text)
        self.assertIn("artifact_refs: artifact-body", text)
        self.assertNotIn("BODY_SECRET_", text)
        self.assertEqual(transcript.tool_result_stats["tool_result_item_count"], 1)
        self.assertEqual(transcript.tool_result_stats["compacted_result_count"], 1)
        self.assertEqual(transcript.tool_result_stats["artifact_ref_count"], 1)

    def test_budget_truncates_recent_text_but_preserves_protocol_required_items(self) -> None:
        transcript = build_model_visible_session_item_prompt_window(
            (
                _item(
                    "item-old",
                    sequence_no=1,
                    kind=SessionItemKind.USER_MESSAGE,
                    role="user",
                    content_payload={"blocks": [{"type": "text", "text": "A" * 500}]},
                ),
                _item(
                    "item-call",
                    sequence_no=2,
                    kind=SessionItemKind.TOOL_CALL,
                    role="assistant",
                    content_payload={
                        "type": "function_call",
                        "call_id": "call-1",
                        "tool_name": "browser.snapshot",
                        "arguments": {},
                    },
                    call_id="call-1",
                    tool_name="browser.snapshot",
                ),
                _item(
                    "item-result",
                    sequence_no=3,
                    kind=SessionItemKind.TOOL_RESULT,
                    role="tool",
                    content_payload={"blocks": [{"type": "text", "text": "B" * 500}]},
                    call_id="call-1",
                    tool_name="browser.snapshot",
                ),
                _item(
                    "item-latest",
                    sequence_no=4,
                    kind=SessionItemKind.ASSISTANT_MESSAGE,
                    role="assistant",
                    content_payload={"blocks": [{"type": "text", "text": "C" * 500}]},
                ),
            ),
            max_chars=120,
        )

        included_ids = [
            message.metadata["session_item_id"] for message in transcript.messages
        ]
        self.assertNotIn("item-old", included_ids)
        self.assertIn("item-call", included_ids)
        self.assertIn("item-result", included_ids)
        self.assertIn("item-latest", included_ids)
        self.assertEqual(transcript.budget["source"], "session_items")
        self.assertTrue(transcript.budget["protocol_required_preserved"])


if __name__ == "__main__":
    unittest.main()
