from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import pytest


CODEX_FLIGHT_TRACE = Path(
    ".crxzipple/codex-flight-trace-20260615-084222/codex-exec-events.jsonl",
)


@dataclass(frozen=True, slots=True)
class CodexTraceSummary:
    event_counts: Counter[str]
    completed_item_counts: Counter[str]
    started_item_counts: Counter[str]


def _summarize_codex_trace(path: Path) -> CodexTraceSummary:
    event_counts: Counter[str] = Counter()
    completed_item_counts: Counter[str] = Counter()
    started_item_counts: Counter[str] = Counter()
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            if not line.strip():
                continue
            event = json.loads(line)
            event_type = event.get("type")
            if isinstance(event_type, str):
                event_counts[event_type] += 1
            item = event.get("item")
            if not isinstance(item, dict):
                continue
            item_type = item.get("type")
            if not isinstance(item_type, str):
                continue
            if event_type == "item.completed":
                completed_item_counts[item_type] += 1
            elif event_type == "item.started":
                started_item_counts[item_type] += 1
    return CodexTraceSummary(
        event_counts=event_counts,
        completed_item_counts=completed_item_counts,
        started_item_counts=started_item_counts,
    )


def test_codex_trace_summary_parser_counts_item_lifecycle(tmp_path: Path) -> None:
    trace_path = tmp_path / "codex-events.jsonl"
    trace_path.write_text(
        "\n".join(
            (
                json.dumps({"type": "thread.started", "thread_id": "thread-1"}),
                json.dumps({"type": "turn.started"}),
                json.dumps(
                    {
                        "type": "item.completed",
                        "item": {"id": "item-1", "type": "agent_message"},
                    },
                ),
                json.dumps(
                    {
                        "type": "item.started",
                        "item": {"id": "item-2", "type": "command_execution"},
                    },
                ),
                json.dumps(
                    {
                        "type": "item.completed",
                        "item": {"id": "item-2", "type": "command_execution"},
                    },
                ),
                json.dumps({"type": "turn.completed"}),
            ),
        ),
        encoding="utf-8",
    )

    summary = _summarize_codex_trace(trace_path)

    assert summary.event_counts == {
        "thread.started": 1,
        "turn.started": 1,
        "item.completed": 2,
        "item.started": 1,
        "turn.completed": 1,
    }
    assert summary.completed_item_counts == {
        "agent_message": 1,
        "command_execution": 1,
    }
    assert summary.started_item_counts == {"command_execution": 1}


def test_local_codex_flight_trace_matches_recorded_contract() -> None:
    if not CODEX_FLIGHT_TRACE.exists():
        pytest.skip(f"local Codex trace is not present: {CODEX_FLIGHT_TRACE}")

    summary = _summarize_codex_trace(CODEX_FLIGHT_TRACE)

    assert summary.event_counts == {
        "thread.started": 1,
        "turn.started": 1,
        "item.completed": 71,
        "item.started": 48,
        "turn.completed": 1,
    }
    assert summary.completed_item_counts == {
        "agent_message": 23,
        "command_execution": 42,
        "mcp_tool_call": 4,
        "web_search": 2,
    }
    assert summary.started_item_counts == {
        "command_execution": 42,
        "mcp_tool_call": 4,
        "web_search": 2,
    }
