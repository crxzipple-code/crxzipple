#!/usr/bin/env python
"""Seed a request-preview SQL smoke fixture.

The fixture creates a prepared orchestration run through the orchestration
submission service, then appends synthetic model-visible session history through
the session application service. It is for local hot-path sampling only.
"""

from __future__ import annotations

import argparse
import json
from typing import Any

from crxzipple.core.config import load_settings
from crxzipple.interfaces.runtime_container import (
    AppKey,
    AssemblyTarget,
    build_runtime_container,
)
from crxzipple.modules.orchestration.application.intake_commands import (
    AcceptOrchestrationRunInput,
    PrepareSessionRunInput,
)
from crxzipple.modules.orchestration.application.turn_submission import (
    build_session_route_context,
)
from crxzipple.modules.orchestration.domain import (
    InboundInstruction,
    OrchestrationQueuePolicy,
)
from crxzipple.modules.session.application import (
    AppendSessionItemInput,
    AppendSessionItemsInput,
)
from crxzipple.modules.session.domain import (
    DirectSessionScope,
    SessionItemKind,
    SessionItemPhase,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Seed a prepared run plus synthetic session history.",
    )
    parser.add_argument("run_id", help="Run id to create.")
    parser.add_argument(
        "--agent-id",
        default="assistant",
        help="Agent profile id for the prepared run.",
    )
    parser.add_argument(
        "--llm-id",
        default="openai_codex.gpt-5.4-mini",
        help="Requested LLM id for the prepared run.",
    )
    parser.add_argument(
        "--history-pairs",
        type=int,
        default=0,
        help="Number of synthetic user/assistant history pairs to append.",
    )
    parser.add_argument(
        "--tool-pairs",
        type=int,
        default=0,
        help="Number of synthetic current-turn tool call/result pairs to append.",
    )
    parser.add_argument(
        "--main-key",
        default="sql-smoke",
        help="Session main key suffix.",
    )
    parser.add_argument(
        "--content",
        default="Request preview SQL smoke current user message.",
        help="Inbound content for the created run.",
    )
    args = parser.parse_args()

    settings = load_settings()
    container = build_runtime_container(
        settings,
        target=AssemblyTarget.CLI_ADMIN,
        run_activation_tasks=False,
    )
    try:
        intake_service = container.require(AppKey.ORCHESTRATION_INTAKE_SERVICE)
        intake_service.accept(
            AcceptOrchestrationRunInput(
                inbound_instruction=InboundInstruction(
                    source="dev-sql-smoke",
                    content=args.content,
                ),
                run_id=args.run_id,
                queue_policy=OrchestrationQueuePolicy.FIFO,
                priority=100,
                max_steps=99,
                metadata={"fixture": "request_preview_sql_smoke"},
            ),
        )
        run = intake_service.prepare_session_run(
            PrepareSessionRunInput(
                run_id=args.run_id,
                context=build_session_route_context(
                    agent_id=args.agent_id,
                    channel="webchat",
                    chat_type="direct",
                    peer_id=None,
                    conversation_id=None,
                    thread_id=None,
                    account_id=None,
                    main_key=args.main_key,
                    direct_scope=DirectSessionScope.MAIN,
                ),
                requested_llm_id=args.llm_id,
                metadata={"fixture": "request_preview_sql_smoke"},
            ),
        )
        session_key = str(run.metadata["session_key"])
        session_id = run.active_session_id
        if session_id is None:
            raise RuntimeError(f"Run {run.id} has no active_session_id")
        appended_history = _append_history(
            container=container,
            session_key=session_key,
            session_id=session_id,
            pair_count=max(0, args.history_pairs),
        )
        appended_tools = _append_tool_pairs(
            container=container,
            session_key=session_key,
            session_id=session_id,
            pair_count=max(0, args.tool_pairs),
        )
    finally:
        container.close()

    payload: dict[str, Any] = {
        "run_id": run.id,
        "session_key": session_key,
        "session_id": session_id,
        "history_pairs": max(0, args.history_pairs),
        "tool_pairs": max(0, args.tool_pairs),
        "appended_item_count": appended_history + appended_tools,
        "appended_history_item_count": appended_history,
        "appended_tool_item_count": appended_tools,
        "llm_id": args.llm_id,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def _append_history(
    *,
    container: object,
    session_key: str,
    session_id: str,
    pair_count: int,
) -> int:
    if pair_count <= 0:
        return 0
    items: list[AppendSessionItemInput] = []
    for index in range(pair_count):
        items.append(
            AppendSessionItemInput(
                session_key=session_key,
                session_id=session_id,
                kind=SessionItemKind.USER_MESSAGE,
                role="user",
                phase=SessionItemPhase.UNKNOWN,
                content_payload={
                    "text": f"historical user message {index + 1}",
                },
                source_module="dev",
                source_kind="request_preview_sql_smoke_fixture",
                source_id=f"history-user-{index + 1}",
            ),
        )
        items.append(
            AppendSessionItemInput(
                session_key=session_key,
                session_id=session_id,
                kind=SessionItemKind.ASSISTANT_MESSAGE,
                role="assistant",
                phase=SessionItemPhase.FINAL_ANSWER,
                content_payload={
                    "text": f"historical assistant answer {index + 1}",
                },
                source_module="dev",
                source_kind="request_preview_sql_smoke_fixture",
                source_id=f"history-assistant-{index + 1}",
            ),
        )
    container.require(AppKey.SESSION_SERVICE).append_items(
        AppendSessionItemsInput(items=tuple(items)),
    )
    return len(items)


def _append_tool_pairs(
    *,
    container: object,
    session_key: str,
    session_id: str,
    pair_count: int,
) -> int:
    if pair_count <= 0:
        return 0
    items: list[AppendSessionItemInput] = []
    for index in range(pair_count):
        ordinal = index + 1
        call_id = f"call-sql-smoke-{ordinal}"
        tool_name = "fixture.echo"
        items.append(
            AppendSessionItemInput(
                session_key=session_key,
                session_id=session_id,
                kind=SessionItemKind.TOOL_CALL,
                role="assistant",
                phase=SessionItemPhase.UNKNOWN,
                content_payload={
                    "arguments": {
                        "index": ordinal,
                        "query": f"fixture tool query {ordinal}",
                    },
                    "tool_name": tool_name,
                },
                source_module="llm",
                source_kind="request_preview_sql_smoke_fixture",
                source_id=f"tool-call-{ordinal}",
                provider_item_id=f"provider-call-sql-smoke-{ordinal}",
                provider_item_type="function_call",
                call_id=call_id,
                tool_name=tool_name,
            ),
        )
        items.append(
            AppendSessionItemInput(
                session_key=session_key,
                session_id=session_id,
                kind=SessionItemKind.TOOL_RESULT,
                role="tool",
                phase=SessionItemPhase.UNKNOWN,
                content_payload={
                    "tool_call_id": call_id,
                    "tool_name": tool_name,
                    "status": "succeeded",
                    "content": [
                        {
                            "type": "text",
                            "text": f"fixture tool result {ordinal}",
                        },
                    ],
                },
                source_module="tool",
                source_kind="request_preview_sql_smoke_fixture",
                source_id=f"tool-result-{ordinal}",
                provider_item_id=f"provider-result-sql-smoke-{ordinal}",
                provider_item_type="function_call_output",
                call_id=call_id,
                tool_name=tool_name,
                metadata={"tool_status": "succeeded"},
            ),
        )
    container.require(AppKey.SESSION_SERVICE).append_items(
        AppendSessionItemsInput(items=tuple(items)),
    )
    return len(items)


if __name__ == "__main__":
    raise SystemExit(main())
