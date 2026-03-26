from __future__ import annotations

from dataclasses import dataclass
import time

from crxzipple.modules.agent.application import AgentApplicationService
from crxzipple.modules.agent.domain.entities import AgentProfile
from crxzipple.modules.agent.domain.exceptions import AgentNotFoundError
from crxzipple.modules.orchestration.application import (
    EnqueueOrchestrationRunInput,
    OrchestrationApplicationService,
)
from crxzipple.modules.orchestration.domain import (
    OrchestrationQueuePolicy,
    OrchestrationRun,
    OrchestrationRunStage,
    OrchestrationRunStatus,
)
from crxzipple.modules.orchestration.interfaces.shared import (
    build_accept_run_input,
    build_prepare_session_run_input,
)
from crxzipple.modules.session.domain import DirectSessionScope
from crxzipple.modules.tool.application.services import ToolApplicationService


@dataclass(frozen=True, slots=True)
class TurnSubmissionOptions:
    agent_id: str
    llm_id: str
    channel: str
    chat_type: str
    peer_id: str | None
    conversation_id: str | None
    thread_id: str | None
    account_id: str | None
    main_key: str
    direct_scope: DirectSessionScope
    source: str
    queue_policy: OrchestrationQueuePolicy
    priority: int
    max_steps: int


@dataclass(frozen=True, slots=True)
class ForegroundTurnOptions(TurnSubmissionOptions):
    wait_timeout_seconds: int
    poll_interval_seconds: float
    worker_id: str
    tool_worker_id: str


class ForegroundTurnTimeoutError(RuntimeError):
    pass


def terminal(run: OrchestrationRun) -> bool:
    return run.status in {
        OrchestrationRunStatus.COMPLETED,
        OrchestrationRunStatus.FAILED,
        OrchestrationRunStatus.CANCELLED,
    }


def resolve_profile(
    agent_service: AgentApplicationService,
    *,
    agent_id: str | None,
) -> tuple[AgentProfile | None, str | None]:
    if agent_id is not None:
        try:
            return agent_service.get_profile(agent_id), None
        except AgentNotFoundError as exc:
            return None, str(exc)

    profiles = [profile for profile in agent_service.list_profiles() if profile.enabled]
    if not profiles:
        return None, (
            "No enabled agent profiles are available. Register one first with `agent register-profile`."
        )
    if len(profiles) > 1:
        return None, "Multiple enabled agent profiles exist. Specify an agent id explicitly."
    return profiles[0], None


def build_submission_options(
    *,
    profile: AgentProfile,
    llm_id: str | None,
    channel: str,
    chat_type: str,
    peer_id: str | None,
    conversation_id: str | None,
    thread_id: str | None,
    account_id: str | None,
    main_key: str,
    direct_scope: DirectSessionScope | str,
    source: str,
    queue_policy: OrchestrationQueuePolicy | str,
    priority: int,
    max_steps: int | None,
) -> TurnSubmissionOptions:
    resolved_direct_scope = (
        direct_scope
        if isinstance(direct_scope, DirectSessionScope)
        else DirectSessionScope(direct_scope)
    )
    resolved_queue_policy = (
        queue_policy
        if isinstance(queue_policy, OrchestrationQueuePolicy)
        else OrchestrationQueuePolicy(queue_policy)
    )
    return TurnSubmissionOptions(
        agent_id=profile.id,
        llm_id=llm_id or profile.llm_routing_policy.default_llm_id,
        channel=channel,
        chat_type=chat_type,
        peer_id=peer_id,
        conversation_id=conversation_id,
        thread_id=thread_id,
        account_id=account_id,
        main_key=main_key,
        direct_scope=resolved_direct_scope,
        source=source,
        queue_policy=resolved_queue_policy,
        priority=priority,
        max_steps=max_steps or profile.execution_policy.max_turns,
    )


def build_turn_options(
    *,
    profile: AgentProfile,
    llm_id: str | None,
    channel: str,
    chat_type: str,
    peer_id: str | None,
    conversation_id: str | None,
    thread_id: str | None,
    account_id: str | None,
    main_key: str,
    direct_scope: DirectSessionScope | str,
    source: str,
    queue_policy: OrchestrationQueuePolicy | str,
    priority: int,
    max_steps: int | None,
    wait_timeout_seconds: int,
    poll_interval_seconds: float,
    worker_id: str,
    tool_worker_id: str,
) -> ForegroundTurnOptions:
    submission = build_submission_options(
        profile=profile,
        llm_id=llm_id,
        channel=channel,
        chat_type=chat_type,
        peer_id=peer_id,
        conversation_id=conversation_id,
        thread_id=thread_id,
        account_id=account_id,
        main_key=main_key,
        direct_scope=direct_scope,
        source=source,
        queue_policy=queue_policy,
        priority=priority,
        max_steps=max_steps,
    )
    return ForegroundTurnOptions(
        agent_id=submission.agent_id,
        llm_id=submission.llm_id,
        channel=submission.channel,
        chat_type=submission.chat_type,
        peer_id=submission.peer_id,
        conversation_id=submission.conversation_id,
        thread_id=submission.thread_id,
        account_id=submission.account_id,
        main_key=submission.main_key,
        direct_scope=submission.direct_scope,
        source=submission.source,
        queue_policy=submission.queue_policy,
        priority=submission.priority,
        max_steps=submission.max_steps,
        wait_timeout_seconds=wait_timeout_seconds,
        poll_interval_seconds=poll_interval_seconds,
        worker_id=worker_id,
        tool_worker_id=tool_worker_id,
    )


def submit_turn(
    orchestration_service: OrchestrationApplicationService,
    *,
    content: str,
    options: TurnSubmissionOptions,
) -> OrchestrationRun:
    accepted = orchestration_service.accept(
        build_accept_run_input(
            source=options.source,
            content=content,
            queue_policy=options.queue_policy,
            priority=options.priority,
            max_steps=options.max_steps,
        ),
    )
    prepared = orchestration_service.prepare_session_run(
        build_prepare_session_run_input(
            run_id=accepted.id,
            agent_id=options.agent_id,
            llm_id=options.llm_id,
            channel=options.channel,
            chat_type=options.chat_type,
            peer_id=options.peer_id,
            conversation_id=options.conversation_id,
            thread_id=options.thread_id,
            account_id=options.account_id,
            main_key=options.main_key,
            direct_scope=options.direct_scope,
            priority=options.priority,
        ),
    )
    return orchestration_service.enqueue(
        EnqueueOrchestrationRunInput(
            run_id=prepared.id,
            queue_policy=options.queue_policy,
            priority=options.priority,
        ),
    )


def run_foreground_turn(
    orchestration_service: OrchestrationApplicationService,
    tool_service: ToolApplicationService,
    *,
    content: str,
    options: ForegroundTurnOptions,
) -> OrchestrationRun:
    run = submit_turn(
        orchestration_service,
        content=content,
        options=options,
    )

    deadline = time.monotonic() + options.wait_timeout_seconds
    while time.monotonic() < deadline:
        run = orchestration_service.get_run(run.id)
        if terminal(run):
            return run
        if run.stage is OrchestrationRunStage.WAITING_FOR_CONFIRMATION:
            return run

        progressed = False
        processed_run = orchestration_service.process_next_queued_run(
            worker_id=options.worker_id,
        )
        if processed_run is not None:
            progressed = True
        run = orchestration_service.get_run(run.id)
        if terminal(run):
            return run
        if run.stage is OrchestrationRunStage.WAITING_FOR_CONFIRMATION:
            return run

        processed_tool_run = tool_service.process_next_queued_run(
            worker_id=options.tool_worker_id,
        )
        if processed_tool_run is not None:
            progressed = True
        run = orchestration_service.get_run(run.id)
        if terminal(run):
            return run
        if run.stage is OrchestrationRunStage.WAITING_FOR_CONFIRMATION:
            return run

        if not progressed:
            time.sleep(options.poll_interval_seconds)

    raise ForegroundTurnTimeoutError(
        f"Turn timed out after {options.wait_timeout_seconds} seconds.",
    )


def extract_output_text(run: OrchestrationRun) -> str | None:
    if run.result_payload is None:
        return None
    payload_output = run.result_payload.get("output_text")
    if isinstance(payload_output, str) and payload_output.strip():
        return payload_output
    return None
