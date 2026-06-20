from __future__ import annotations

import unittest

from crxzipple.modules.llm.domain import LlmInputItemKind, LlmMessageRole
from crxzipple.modules.llm.application.session_runtime_transcript import (
    RuntimeReplayWindowBuilder,
    build_current_inbound_runtime_transcript,
    build_session_fact_runtime_window,
)
from crxzipple.modules.orchestration.application.runtime_request_mode import RuntimeRequestMode
from crxzipple.modules.orchestration.application.runtime_request_report import RuntimeRequestReport
from crxzipple.modules.session.domain import (
    SessionItem,
    SessionItemKind,
    SessionItemPhase,
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
    phase: SessionItemPhase = SessionItemPhase.COMMENTARY,
) -> SessionItem:
    return SessionItem(
        id=item_id,
        session_key="session",
        session_id="active",
        sequence_no=sequence_no,
        role=role,
        kind=kind,
        phase=phase,
        content_payload=content_payload,
        call_id=call_id,
        tool_name=tool_name,
    )


class RuntimeTranscriptTestCase(unittest.TestCase):
    def test_current_inbound_runtime_transcript_projects_structured_user_message(
        self,
    ) -> None:
        transcript = build_current_inbound_runtime_transcript(
            {"blocks": [{"type": "text", "text": "check current weather"}]},
            source="user",
            source_id="run-1",
        )

        self.assertEqual(len(transcript.messages), 1)
        self.assertEqual(transcript.messages[0].role, LlmMessageRole.USER)
        self.assertEqual(
            transcript.messages[0].content,
            [{"type": "text", "text": "check current weather"}],
        )
        self.assertEqual(
            transcript.messages[0].metadata,
            {
                "runtime_request_block_kind": "current_inbound",
                "source": "user",
                "source_kind": "orchestration_run",
                "source_id": "run-1",
            },
        )
        self.assertEqual(len(transcript.input_items), 1)
        self.assertEqual(transcript.input_items[0].kind, LlmInputItemKind.MESSAGE)
        self.assertEqual(transcript.input_items[0].source, "current_inbound")
        self.assertEqual(transcript.report.message_count, 1)

    def test_current_inbound_runtime_transcript_handles_empty_content(
        self,
    ) -> None:
        transcript = build_current_inbound_runtime_transcript(
            {"blocks": []},
            source="user",
            source_id="run-1",
        )

        self.assertEqual(transcript.messages, ())
        self.assertEqual(transcript.input_items, ())
        self.assertEqual(transcript.report.message_count, 0)

    def test_runtime_replay_window_builder_matches_runtime_window_function_surface(
        self,
    ) -> None:
        items = (
            _item(
                "item-user",
                sequence_no=1,
                kind=SessionItemKind.USER_MESSAGE,
                role="user",
                content_payload={"blocks": [{"type": "text", "text": "hello"}]},
            ),
            _item(
                "item-assistant",
                sequence_no=2,
                kind=SessionItemKind.ASSISTANT_MESSAGE,
                role="assistant",
                content_payload={"text": "I will inspect."},
            ),
        )

        rendered = RuntimeReplayWindowBuilder().build_from_session_items(items)
        runtime_window = build_session_fact_runtime_window(items)

        self.assertEqual(rendered.messages, runtime_window.messages)
        self.assertEqual(rendered.input_items, runtime_window.input_items)
        self.assertEqual(
            rendered.report.tool_result_stats,
            runtime_window.report.tool_result_stats,
        )
        self.assertEqual(rendered.report.budget, runtime_window.report.budget)

    def test_runtime_request_report_payload_includes_tool_result_stats(self) -> None:
        report = RuntimeRequestReport(
            mode=RuntimeRequestMode.NORMAL_TURN,
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

    def test_protocol_only_replay_excludes_prior_turn_tool_pair_for_followup(
        self,
    ) -> None:
        transcript = build_session_fact_runtime_window(
            (
                _item(
                    "item-user-1",
                    sequence_no=1,
                    kind=SessionItemKind.USER_MESSAGE,
                    role="user",
                    content_payload={"blocks": [{"type": "text", "text": "use echo"}]},
                ),
                _item(
                    "item-call-1",
                    sequence_no=2,
                    kind=SessionItemKind.TOOL_CALL,
                    role="assistant",
                    content_payload={
                        "type": "function_call",
                        "call_id": "call-echo-history-1",
                        "name": "echo",
                        "arguments": {"message": "hello"},
                    },
                    call_id="call-echo-history-1",
                    tool_name="echo",
                ),
                _item(
                    "item-result-1",
                    sequence_no=3,
                    kind=SessionItemKind.TOOL_RESULT,
                    role="tool",
                    content_payload={
                        "tool_name": "echo",
                        "tool_call_id": "call-echo-history-1",
                        "content": [
                            {"type": "text", "text": "first tool answer"},
                        ],
                    },
                    call_id="call-echo-history-1",
                    tool_name="echo",
                ),
                _item(
                    "item-final-1",
                    sequence_no=4,
                    kind=SessionItemKind.ASSISTANT_MESSAGE,
                    role="assistant",
                    phase=SessionItemPhase.FINAL_ANSWER,
                    content_payload={"blocks": [{"type": "text", "text": "done"}]},
                ),
                _item(
                    "item-user-2",
                    sequence_no=5,
                    kind=SessionItemKind.USER_MESSAGE,
                    role="user",
                    content_payload={
                        "blocks": [{"type": "text", "text": "what happened?"}],
                    },
                ),
            ),
            include_non_protocol_history=False,
        )

        self.assertEqual(
            [item.metadata["session_item_id"] for item in transcript.input_items],
            ["item-user-2"],
        )
        self.assertEqual(
            [item.kind for item in transcript.input_items],
            [LlmInputItemKind.MESSAGE],
        )
        replay_payload = " ".join(str(item.payload) for item in transcript.input_items)
        self.assertNotIn("call-echo-history-1", replay_payload)
        self.assertNotIn("first tool answer", replay_payload)
        self.assertIn("what happened?", replay_payload)

    def test_replays_assistant_progress_tool_call_and_tool_result_items(self) -> None:
        transcript = build_session_fact_runtime_window(
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

        self.assertEqual(transcript.report.message_count, 3)
        self.assertEqual(transcript.messages[0].role, LlmMessageRole.ASSISTANT)
        self.assertEqual(
            transcript.messages[0].content,
            [{"type": "text", "text": "I will inspect the page."}],
        )
        self.assertEqual(transcript.messages[1].role, LlmMessageRole.ASSISTANT)
        self.assertEqual(transcript.messages[1].tool_call_id, "call-1")
        self.assertEqual(transcript.messages[2].role, LlmMessageRole.TOOL)
        self.assertEqual(transcript.messages[2].name, "search_docs")
        self.assertEqual(
            tuple(item.kind for item in transcript.input_items),
            (
                LlmInputItemKind.MESSAGE,
                LlmInputItemKind.FUNCTION_CALL,
                LlmInputItemKind.FUNCTION_CALL_OUTPUT,
            ),
        )
        self.assertEqual(transcript.input_items[1].source, "session_item")
        self.assertEqual(transcript.input_items[1].payload["call_id"], "call-1")
        self.assertEqual(transcript.input_items[1].payload["name"], "search_docs")
        self.assertEqual(
            transcript.input_items[1].payload["arguments"],
            {"query": "ddd"},
        )
        self.assertEqual(transcript.input_items[2].payload["call_id"], "call-1")
        self.assertEqual(
            transcript.input_items[2].payload["output"],
            [{"type": "text", "text": "done"}],
        )
        diagnostics = transcript.report.budget["tool_protocol_diagnostics"]
        self.assertEqual(diagnostics["orphan_tool_output_count"], 0)
        self.assertEqual(diagnostics["missing_tool_output_count"], 0)

    def test_includes_session_fact_items_without_session_visibility_filter(self) -> None:
        transcript = build_session_fact_runtime_window(
            (
                _item(
                    "item-hidden",
                    sequence_no=1,
                    kind=SessionItemKind.REASONING,
                    role="assistant",
                    content_payload={"text": "hidden reasoning"},
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

        self.assertEqual(transcript.report.message_count, 2)
        self.assertEqual(transcript.messages[0].role, LlmMessageRole.ASSISTANT)
        self.assertEqual(transcript.messages[1].role, LlmMessageRole.USER)
        self.assertEqual(
            transcript.messages[1].metadata["session_item_id"],
            "item-user",
        )

    def test_excludes_empty_reasoning_items_from_direct_history(self) -> None:
        transcript = build_session_fact_runtime_window(
            (
                _item(
                    "item-user",
                    sequence_no=1,
                    kind=SessionItemKind.USER_MESSAGE,
                    role="user",
                    content_payload={"blocks": [{"type": "text", "text": "hello"}]},
                ),
                _item(
                    "item-empty-reasoning",
                    sequence_no=2,
                    kind=SessionItemKind.REASONING,
                    role="assistant",
                    content_payload={"summary": [], "text": None},
                ),
                _item(
                    "item-assistant",
                    sequence_no=3,
                    kind=SessionItemKind.ASSISTANT_MESSAGE,
                    role="assistant",
                    content_payload={"text": "Need a date."},
                ),
            ),
        )

        self.assertEqual(
            [message.metadata["session_item_id"] for message in transcript.messages],
            ["item-user", "item-assistant"],
        )
        self.assertEqual(
            [item.kind for item in transcript.input_items],
            [LlmInputItemKind.MESSAGE, LlmInputItemKind.MESSAGE],
        )

    def test_excludes_empty_assistant_and_dedupes_adjacent_progress(self) -> None:
        transcript = build_session_fact_runtime_window(
            (
                _item(
                    "item-user",
                    sequence_no=1,
                    kind=SessionItemKind.USER_MESSAGE,
                    role="user",
                    content_payload={"text": "Find flights."},
                ),
                _item(
                    "item-empty-assistant",
                    sequence_no=2,
                    kind=SessionItemKind.ASSISTANT_MESSAGE,
                    role="assistant",
                    content_payload={"summary": [], "text": None},
                ),
                _item(
                    "item-progress-1",
                    sequence_no=3,
                    kind=SessionItemKind.ASSISTANT_MESSAGE,
                    role="assistant",
                    content_payload={"text": "I will inspect the official site."},
                ),
                _item(
                    "item-progress-2",
                    sequence_no=4,
                    kind=SessionItemKind.ASSISTANT_MESSAGE,
                    role="assistant",
                    content_payload={"text": "I will inspect the official site."},
                ),
                _item(
                    "item-final",
                    sequence_no=5,
                    kind=SessionItemKind.ASSISTANT_MESSAGE,
                    role="assistant",
                    phase=SessionItemPhase.FINAL_ANSWER,
                    content_payload={"text": "I found the route."},
                ),
            ),
        )

        self.assertEqual(
            [message.metadata["session_item_id"] for message in transcript.messages],
            ["item-user", "item-progress-1", "item-final"],
        )

    def test_protocol_only_replay_keeps_current_turn_reasoning_progress(self) -> None:
        transcript = build_session_fact_runtime_window(
            (
                _item(
                    "item-old-reasoning",
                    sequence_no=1,
                    kind=SessionItemKind.REASONING,
                    role="assistant",
                    content_payload={"text": "Old turn summary should stay out."},
                ),
                _item(
                    "item-user",
                    sequence_no=2,
                    kind=SessionItemKind.USER_MESSAGE,
                    role="user",
                    content_payload={
                        "blocks": [{"type": "text", "text": "Find the ticket."}],
                    },
                ),
                _item(
                    "item-reasoning",
                    sequence_no=3,
                    kind=SessionItemKind.REASONING,
                    role="assistant",
                    content_payload={
                        "text": "I found the mobile endpoint; next I will replay it.",
                    },
                ),
                _item(
                    "item-empty-reasoning",
                    sequence_no=4,
                    kind=SessionItemKind.REASONING,
                    role="assistant",
                    content_payload={"summary": []},
                ),
                _item(
                    "item-call",
                    sequence_no=5,
                    kind=SessionItemKind.TOOL_CALL,
                    role="assistant",
                    content_payload={
                        "type": "function_call",
                        "call_id": "call-1",
                        "tool_name": "exec",
                        "arguments": {"cmd": "python replay.py"},
                    },
                    call_id="call-1",
                    tool_name="exec",
                ),
                _item(
                    "item-result",
                    sequence_no=6,
                    kind=SessionItemKind.TOOL_RESULT,
                    role="tool",
                    content_payload={"blocks": [{"type": "text", "text": "blocked"}]},
                    call_id="call-1",
                    tool_name="exec",
                ),
            ),
            include_non_protocol_history=False,
        )

        included_ids = [
            message.metadata["session_item_id"] for message in transcript.messages
        ]
        self.assertEqual(
            included_ids,
            ["item-user", "item-reasoning", "item-call", "item-result"],
        )
        self.assertEqual(transcript.messages[1].role, LlmMessageRole.ASSISTANT)
        self.assertEqual(
            transcript.messages[1].content,
            [
                {
                    "type": "text",
                    "text": "I found the mobile endpoint; next I will replay it.",
                },
            ],
        )
        self.assertEqual(
            transcript.input_items[1].kind,
            LlmInputItemKind.REASONING,
        )
        self.assertEqual(transcript.input_items[1].source, "session_item")
        self.assertEqual(
            transcript.input_items[1].payload["content"],
            [
                {
                    "type": "text",
                    "text": "I found the mobile endpoint; next I will replay it.",
                },
            ],
        )

    def test_protocol_only_replay_excludes_prior_turn_tool_pairs(self) -> None:
        transcript = build_session_fact_runtime_window(
            (
                _item(
                    "item-old-user",
                    sequence_no=1,
                    kind=SessionItemKind.USER_MESSAGE,
                    role="user",
                    content_payload={
                        "blocks": [{"type": "text", "text": "Check weather tools."}],
                    },
                ),
                _item(
                    "item-old-call",
                    sequence_no=2,
                    kind=SessionItemKind.TOOL_CALL,
                    role="assistant",
                    content_payload={
                        "type": "function_call",
                        "call_id": "call-old",
                        "tool_name": "capability.search",
                        "arguments": {"query": "weather"},
                    },
                    call_id="call-old",
                    tool_name="capability.search",
                ),
                _item(
                    "item-old-result",
                    sequence_no=3,
                    kind=SessionItemKind.TOOL_RESULT,
                    role="tool",
                    content_payload={
                        "blocks": [{"type": "text", "text": "weather enabled"}],
                    },
                    call_id="call-old",
                    tool_name="capability.search",
                ),
                _item(
                    "item-current-user",
                    sequence_no=4,
                    kind=SessionItemKind.USER_MESSAGE,
                    role="user",
                    content_payload={
                        "blocks": [{"type": "text", "text": "Find the flight."}],
                    },
                ),
                _item(
                    "item-current-call",
                    sequence_no=5,
                    kind=SessionItemKind.TOOL_CALL,
                    role="assistant",
                    content_payload={
                        "type": "function_call",
                        "call_id": "call-current",
                        "tool_name": "browser.navigate",
                        "arguments": {"url": "https://example.test"},
                    },
                    call_id="call-current",
                    tool_name="browser.navigate",
                ),
                _item(
                    "item-current-result",
                    sequence_no=6,
                    kind=SessionItemKind.TOOL_RESULT,
                    role="tool",
                    content_payload={"blocks": [{"type": "text", "text": "loaded"}]},
                    call_id="call-current",
                    tool_name="browser.navigate",
                ),
            ),
            include_non_protocol_history=False,
        )

        included_ids = [
            item.metadata["session_item_id"] for item in transcript.input_items
        ]
        self.assertEqual(
            included_ids,
            ["item-current-user", "item-current-call", "item-current-result"],
        )
        rendered_payload = " ".join(str(item.payload) for item in transcript.input_items)
        self.assertNotIn("weather", rendered_payload)
        self.assertIn("Find the flight.", rendered_payload)

    def test_tool_result_envelope_renders_provider_visible_evidence_without_body(self) -> None:
        transcript = build_session_fact_runtime_window(
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
                            "browser_evidence": {},
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
        self.assertIn("tool_result:", text)
        self.assertIn("summary: large response captured", text)
        self.assertNotIn("evidence_path:", text)
        self.assertIn("artifact_refs: artifact-body", text)
        self.assertIn("body_excerpt_policy: truncated, body_removed", text)
        self.assertIn("full_result_refs: use artifact refs or read handles when needed", text)
        self.assertNotIn("BODY_SECRET_", text)
        self.assertEqual(transcript.report.tool_result_stats["tool_result_item_count"], 1)
        self.assertEqual(transcript.report.tool_result_stats["compacted_result_count"], 1)
        self.assertEqual(transcript.report.tool_result_stats["artifact_ref_count"], 1)

    def test_tool_result_replays_explicit_details_without_artifact_compaction(self) -> None:
        transcript = build_session_fact_runtime_window(
            (
                _item(
                    "item-call",
                    sequence_no=1,
                    kind=SessionItemKind.TOOL_CALL,
                    role="assistant",
                    content_payload={
                        "type": "function_call",
                        "call_id": "call-1",
                        "tool_name": "command.exec",
                        "arguments": {"cmd": "node query.js"},
                    },
                    call_id="call-1",
                    tool_name="command.exec",
                ),
                _item(
                    "item-tool",
                    sequence_no=2,
                    kind=SessionItemKind.TOOL_RESULT,
                    role="tool",
                    call_id="call-1",
                    tool_name="command.exec",
                    content_payload={
                        "status": "succeeded",
                        "output_payload": {"exit_code": 0},
                        "details": {
                            "command": "node query.js",
                            "current_url": "https://www.ceair.com/zh/cny/home",
                            "stdout": "home page loaded",
                            "stderr": "TimeoutError clicked search",
                        },
                        "metadata": {
                            TOOL_RESULT_ENVELOPE_METADATA_KEY: {
                                "status": "ok",
                                "summary": "Search timed out before fare list appeared.",
                            },
                        },
                    },
                ),
            ),
        )

        tool_message = transcript.messages[1]
        assert isinstance(tool_message.content, list)
        text = tool_message.content[0]["text"]
        self.assertIn("summary: Search timed out before fare list appeared.", text)
        self.assertIn("command: node query.js", text)
        self.assertIn("exit_code: 0", text)
        self.assertIn("current_url: https://www.ceair.com/zh/cny/home", text)
        self.assertIn("stdout_excerpt: home page loaded", text)
        self.assertIn("stderr_excerpt: TimeoutError clicked search", text)
        self.assertNotIn("task_evidence_status:", text)

    def test_budget_truncates_recent_text_but_preserves_protocol_required_items(self) -> None:
        transcript = build_session_fact_runtime_window(
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
        self.assertEqual(transcript.report.budget["source"], "session_items")
        self.assertTrue(transcript.report.budget["protocol_required_preserved"])
        self.assertTrue(transcript.report.budget["truncated"])
        self.assertEqual(transcript.report.budget["collapsed_item_count"], 1)
        self.assertEqual(transcript.report.budget["shortened_item_count"], 1)
        self.assertEqual(transcript.report.budget["collapsed_chars"], 500)
        self.assertEqual(transcript.report.budget["shortened_chars"], 380)
        self.assertEqual(transcript.report.budget["omitted_chars"], 880)
        self.assertEqual(
            [ref["item_id"] for ref in transcript.report.budget["shortened_refs"]],
            ["item-latest"],
        )
        latest_message = next(
            message
            for message in transcript.messages
            if message.metadata["session_item_id"] == "item-latest"
        )
        self.assertNotIn("provider_replay_truncation", latest_message.metadata)

    def test_full_history_replay_filters_broken_tool_protocol_items(self) -> None:
        transcript = build_session_fact_runtime_window(
            (
                _item(
                    "item-orphan",
                    sequence_no=1,
                    kind=SessionItemKind.TOOL_RESULT,
                    role="tool",
                    content_payload={"blocks": [{"type": "text", "text": "orphan"}]},
                    call_id="call-orphan",
                    tool_name="exec",
                ),
                _item(
                    "item-missing",
                    sequence_no=2,
                    kind=SessionItemKind.TOOL_CALL,
                    role="assistant",
                    content_payload={
                        "type": "function_call",
                        "call_id": "call-missing",
                        "tool_name": "exec",
                        "arguments": {"cmd": "pwd"},
                    },
                    call_id="call-missing",
                    tool_name="exec",
                ),
                _item(
                    "item-call-a",
                    sequence_no=3,
                    kind=SessionItemKind.TOOL_CALL,
                    role="assistant",
                    content_payload={
                        "type": "function_call",
                        "call_id": "call-dup",
                        "tool_name": "exec",
                        "arguments": {"cmd": "date"},
                    },
                    call_id="call-dup",
                    tool_name="exec",
                ),
                _item(
                    "item-call-b",
                    sequence_no=4,
                    kind=SessionItemKind.TOOL_CALL,
                    role="assistant",
                    content_payload={
                        "type": "function_call",
                        "call_id": "call-dup",
                        "tool_name": "exec",
                        "arguments": {"cmd": "date"},
                    },
                    call_id="call-dup",
                    tool_name="exec",
                ),
                _item(
                    "item-result",
                    sequence_no=5,
                    kind=SessionItemKind.TOOL_RESULT,
                    role="tool",
                    content_payload={"blocks": [{"type": "text", "text": "ok"}]},
                    call_id="call-dup",
                    tool_name="exec",
                ),
            ),
        )

        included_ids = [
            message.metadata["session_item_id"] for message in transcript.messages
        ]
        self.assertEqual(included_ids, ["item-call-a", "item-result"])
        source_diagnostics = transcript.report.budget["source_tool_protocol_diagnostics"]
        diagnostics = transcript.report.budget["tool_protocol_diagnostics"]
        normalization = transcript.report.budget["tool_protocol_normalization"]
        self.assertEqual(transcript.report.budget["orphan_tool_output_count"], 0)
        self.assertEqual(transcript.report.budget["missing_tool_output_count"], 0)
        self.assertEqual(transcript.report.budget["duplicate_tool_call_id_count"], 0)
        self.assertEqual(source_diagnostics["orphan_tool_output_count"], 1)
        self.assertEqual(source_diagnostics["missing_tool_output_count"], 1)
        self.assertEqual(source_diagnostics["duplicate_tool_call_ids"], ["call-dup"])
        self.assertEqual(diagnostics["orphan_tool_output_count"], 0)
        self.assertEqual(diagnostics["missing_tool_output_count"], 0)
        self.assertEqual(normalization["dropped_orphan_tool_output_count"], 1)
        self.assertEqual(normalization["dropped_missing_tool_output_count"], 1)
        self.assertEqual(normalization["dropped_duplicate_tool_call_id_count"], 1)

    def test_protocol_only_replay_reports_source_breaks_filtered_from_replay(self) -> None:
        transcript = build_session_fact_runtime_window(
            (
                _item(
                    "item-user",
                    sequence_no=1,
                    kind=SessionItemKind.USER_MESSAGE,
                    role="user",
                    content_payload={"blocks": [{"type": "text", "text": "continue"}]},
                ),
                _item(
                    "item-orphan",
                    sequence_no=2,
                    kind=SessionItemKind.TOOL_RESULT,
                    role="tool",
                    content_payload={"blocks": [{"type": "text", "text": "orphan"}]},
                    call_id="call-orphan",
                    tool_name="exec",
                ),
                _item(
                    "item-missing",
                    sequence_no=3,
                    kind=SessionItemKind.TOOL_CALL,
                    role="assistant",
                    content_payload={
                        "type": "function_call",
                        "call_id": "call-missing",
                        "tool_name": "exec",
                        "arguments": {"cmd": "pwd"},
                    },
                    call_id="call-missing",
                    tool_name="exec",
                ),
                _item(
                    "item-call",
                    sequence_no=4,
                    kind=SessionItemKind.TOOL_CALL,
                    role="assistant",
                    content_payload={
                        "type": "function_call",
                        "call_id": "call-ok",
                        "tool_name": "exec",
                        "arguments": {"cmd": "date"},
                    },
                    call_id="call-ok",
                    tool_name="exec",
                ),
                _item(
                    "item-result",
                    sequence_no=5,
                    kind=SessionItemKind.TOOL_RESULT,
                    role="tool",
                    content_payload={"blocks": [{"type": "text", "text": "ok"}]},
                    call_id="call-ok",
                    tool_name="exec",
                ),
            ),
            include_non_protocol_history=False,
        )

        included_ids = [
            message.metadata["session_item_id"] for message in transcript.messages
        ]
        self.assertEqual(included_ids, ["item-user", "item-call", "item-result"])
        source_diagnostics = transcript.report.budget["source_tool_protocol_diagnostics"]
        replay_diagnostics = transcript.report.budget["tool_protocol_diagnostics"]
        normalization = transcript.report.budget["tool_protocol_normalization"]
        self.assertEqual(source_diagnostics["orphan_tool_output_count"], 1)
        self.assertEqual(source_diagnostics["missing_tool_output_count"], 1)
        self.assertEqual(replay_diagnostics["orphan_tool_output_count"], 0)
        self.assertEqual(replay_diagnostics["missing_tool_output_count"], 0)
        self.assertEqual(normalization["dropped_orphan_tool_output_count"], 1)
        self.assertEqual(normalization["dropped_missing_tool_output_count"], 1)
        self.assertTrue(normalization["source_had_protocol_breaks"])
        self.assertFalse(normalization["replay_has_protocol_breaks"])


if __name__ == "__main__":
    unittest.main()
