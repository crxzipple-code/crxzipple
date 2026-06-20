from __future__ import annotations

from crxzipple.modules.llm.application.tool_result_model_text import (
    render_tool_result_model_text,
)
from crxzipple.modules.tool.application.result_envelope import (
    TOOL_RESULT_ENVELOPE_METADATA_KEY,
)


def test_render_tool_result_model_text_omits_task_judgement_context() -> None:
    text = render_tool_result_model_text(
        {
            "details": {"body_removed_from_details": True},
            "metadata": {
                "artifact_ids": ["artifact-stdout"],
                TOOL_RESULT_ENVELOPE_METADATA_KEY: {
                    "status": "ok",
                    "summary": "Desktop site loaded but search did not produce fares.",
                    "task_evidence_status": "needs_followup",
                    "truncated": True,
                    "key_facts": {"current_url": "https://www.ceair.com/zh/cny/home"},
                    "provider_replay_payload": {
                        "stderr_excerpt": "ElementHandle.click: Element is not visible",
                    },
                    "failure_signatures": [
                        "ElementHandle.click: Element is not visible",
                    ],
                    "gaps": ["no flight list", "no price"],
                    "recommended_next_actions": [
                        "inspect mobile endpoint",
                        "capture network request",
                    ],
                    "omitted_chars": 1200,
                    "read_handles": [{"kind": "artifact", "id": "artifact-stdout"}],
                },
            },
        },
    )

    assert text is not None
    assert "failure_signatures: ElementHandle.click: Element is not visible" in text
    assert "provider_replay_payload:" in text
    assert "artifact_refs: artifact-stdout" in text
    assert "body_excerpt_policy: truncated, body_removed" in text
    assert "task_evidence_status:" not in text
    assert "open_gaps:" not in text
    assert "recommended_next_actions:" not in text


def test_render_tool_result_model_text_returns_none_for_plain_inline_result() -> None:
    assert render_tool_result_model_text({"content": [{"type": "text", "text": "ok"}]}) is None


def test_render_tool_result_model_text_does_not_infer_task_status() -> None:
    text = render_tool_result_model_text(
        {
            "status": "succeeded",
            "output_payload": {"exit_code": 0},
            "details": {
                "body_removed_from_details": True,
                "current_url": "https://www.ceair.com/zh/cny/home",
                "stderr_excerpt": "TimeoutError clicked search",
            },
            "metadata": {
                TOOL_RESULT_ENVELOPE_METADATA_KEY: {
                    "status": "ok",
                    "summary": "Search interaction timed out.",
                    "truncated": True,
                },
            },
        },
    )

    assert text is not None
    assert "summary: Search interaction timed out." in text
    assert "exit_code: 0" in text
    assert "current_url: https://www.ceair.com/zh/cny/home" in text
    assert "stderr_excerpt: TimeoutError clicked search" in text
    assert "task_evidence_status:" not in text
    assert "failure_signatures:" not in text
    assert "open_gaps:" not in text


def test_render_tool_result_model_text_keeps_explicit_details_without_truncation() -> None:
    text = render_tool_result_model_text(
        {
            "output_payload": {"exit_code": 1},
            "details": {
                "command": "node query.js",
                "stdout": "loaded home page",
                "stderr": "Error: missing fare list",
            },
            "metadata": {
                TOOL_RESULT_ENVELOPE_METADATA_KEY: {
                    "status": "error",
                    "summary": "Command ran but no fare list was obtained.",
                },
            },
        },
    )

    assert text is not None
    assert "summary: Command ran but no fare list was obtained." in text
    assert "command: node query.js" in text
    assert "exit_code: 1" in text
    assert "stdout_excerpt: loaded home page" in text
    assert "stderr_excerpt: Error: missing fare list" in text
    assert "body_excerpt_policy:" not in text


def test_render_tool_result_model_text_includes_structured_result_excerpt() -> None:
    text = render_tool_result_model_text(
        {
            "output_payload": {
                "data": {
                    "flights": [
                        {
                            "flight_no": "MU5801",
                            "origin": "KMG",
                            "destination": "SHA",
                            "price": 860,
                        },
                    ],
                },
            },
            "metadata": {
                TOOL_RESULT_ENVELOPE_METADATA_KEY: {
                    "status": "ok",
                    "summary": "Mobile shopping endpoint returned a candidate response.",
                },
            },
        },
    )

    assert text is not None
    assert "summary: Mobile shopping endpoint returned a candidate response." in text
    assert "result_excerpt:" in text
    assert "MU5801" in text
    assert "price" in text


def test_render_tool_result_model_text_does_not_duplicate_owner_visible_payload() -> None:
    text = render_tool_result_model_text(
        {
            "output_payload": {"data": {"hidden": "owner chose compact body"}},
            "metadata": {
                TOOL_RESULT_ENVELOPE_METADATA_KEY: {
                    "status": "ok",
                    "summary": "Owner supplied compact model-visible payload.",
                    "provider_replay_payload": {"summary": "compact facts only"},
                },
            },
        },
    )

    assert text is not None
    assert "provider_replay_payload:" in text
    assert "compact facts only" in text
    assert "result_excerpt:" not in text
    assert "owner chose compact body" not in text
