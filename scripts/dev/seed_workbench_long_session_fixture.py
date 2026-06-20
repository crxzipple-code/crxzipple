#!/usr/bin/env python
"""Seed a Workbench long-session fixture through application services."""

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
from crxzipple.modules.session.domain import DirectSessionScope


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Seed many prepared runs in one Workbench session.",
    )
    parser.add_argument("run_prefix", help="Prefix for created run ids.")
    parser.add_argument(
        "--count",
        type=int,
        default=100,
        help="Number of runs to create.",
    )
    parser.add_argument(
        "--agent-id",
        default="assistant",
        help="Agent profile id for the prepared runs.",
    )
    parser.add_argument(
        "--llm-id",
        default="openai_codex.gpt-5.4-mini",
        help="Requested LLM id for the prepared runs.",
    )
    parser.add_argument(
        "--main-key",
        default="workbench-long-session-smoke",
        help="Session main key suffix.",
    )
    args = parser.parse_args()

    count = max(1, args.count)
    settings = load_settings()
    container = build_runtime_container(
        settings,
        target=AssemblyTarget.CLI_ADMIN,
        run_activation_tasks=False,
    )
    run_ids: list[str] = []
    session_key: str | None = None
    session_id: str | None = None
    try:
        intake_service = container.require(AppKey.ORCHESTRATION_INTAKE_SERVICE)
        for index in range(count):
            ordinal = index + 1
            run_id = f"{args.run_prefix}_{ordinal:04d}"
            intake_service.accept(
                AcceptOrchestrationRunInput(
                    inbound_instruction=InboundInstruction(
                        source="dev-workbench-long-session-smoke",
                        content=f"Workbench long-session fixture turn {ordinal}",
                    ),
                    run_id=run_id,
                    queue_policy=OrchestrationQueuePolicy.FIFO,
                    priority=100,
                    max_steps=99,
                    metadata={
                        "fixture": "workbench_long_session_smoke",
                        "fixture_ordinal": ordinal,
                    },
                ),
            )
            run = intake_service.prepare_session_run(
                PrepareSessionRunInput(
                    run_id=run_id,
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
                    metadata={
                        "fixture": "workbench_long_session_smoke",
                        "fixture_ordinal": ordinal,
                    },
                ),
            )
            run_ids.append(run.id)
            session_key = str(run.metadata["session_key"])
            session_id = run.active_session_id
    finally:
        container.close()

    payload: dict[str, Any] = {
        "run_prefix": args.run_prefix,
        "count": count,
        "first_run_id": run_ids[0],
        "latest_run_id": run_ids[-1],
        "session_key": session_key,
        "session_id": session_id,
        "llm_id": args.llm_id,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
