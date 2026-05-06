from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from threading import Event as StopEvent
from typing import Any
import time

from crxzipple.modules.agent.application import AgentApplicationService
from crxzipple.modules.agent.domain.entities import AgentProfile
from crxzipple.modules.agent.domain.exceptions import AgentNotFoundError
from crxzipple.modules.events import EventsApplicationService
from crxzipple.modules.events.domain import EventTopicWatch
from crxzipple.modules.orchestration.application.commands import (
    SubmitOrchestrationTurnInput,
)
from crxzipple.modules.orchestration.application.intake_commands import (
    AcceptOrchestrationRunInput,
)
from crxzipple.modules.orchestration.application.llm_resolver import (
    normalize_requested_llm_id,
)
from crxzipple.modules.orchestration.application.ports.runtime import (
    OrchestrationRunLookupPort,
    OrchestrationSchedulerSubmitPort,
)
from crxzipple.modules.orchestration.application.observers import turn_session_topic
from crxzipple.modules.orchestration.domain import (
    InboundInstruction,
    OrchestrationQueuePolicy,
    OrchestrationRun,
    OrchestrationRunStage,
    OrchestrationRunStatus,
    ReplyTarget,
)
from crxzipple.modules.session.domain import (
    DirectSessionScope,
    SessionResetPolicy,
    SessionRouteContext,
)
from crxzipple.shared.text_encoding import (
    repair_possible_utf8_latin1_mojibake_content,
)


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
class AwaitTurnOptions(TurnSubmissionOptions):
    wait_timeout_seconds: int
    poll_interval_seconds: float


class AwaitTurnTimeoutError(RuntimeError):
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
            "No enabled agent profiles are available. Register one first with "
            "`agent register-profile`."
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
    resolved_llm_id = normalize_requested_llm_id(
        requested_llm_id=llm_id,
        routing_policy=profile.llm_routing_policy,
    )
    return TurnSubmissionOptions(
        agent_id=profile.id,
        llm_id=resolved_llm_id,
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
) -> AwaitTurnOptions:
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
    return AwaitTurnOptions(
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
    )


def build_inbound_instruction(
    *,
    source: str,
    content: Any | None = None,
    metadata: Mapping[str, object] | None = None,
) -> InboundInstruction:
    normalized_source = source.strip()
    normalized_content = content
    if normalized_source.lower() == "web" and content is not None:
        normalized_content = repair_possible_utf8_latin1_mojibake_content(content)
    return InboundInstruction(
        source=normalized_source,
        content=normalized_content,
        metadata=dict(metadata or {}),
    )


def build_reply_target(
    *,
    interface_name: str | None,
    address: str | None = None,
    reply_to: str | None = None,
    metadata: Mapping[str, object] | None = None,
) -> ReplyTarget | None:
    if interface_name is None:
        return None
    return ReplyTarget(
        interface_name=interface_name,
        address=address,
        reply_to=reply_to,
        metadata=dict(metadata or {}),
    )


def build_session_route_context(
    *,
    agent_id: str,
    channel: str | None = None,
    chat_type: str = "direct",
    peer_id: str | None = None,
    conversation_id: str | None = None,
    thread_id: str | None = None,
    account_id: str | None = None,
    label: str | None = None,
    surface: str | None = None,
    main_key: str = "main",
    direct_scope: DirectSessionScope = DirectSessionScope.MAIN,
    status: str = "active",
    metadata: Mapping[str, object] | None = None,
) -> SessionRouteContext:
    return SessionRouteContext(
        agent_id=agent_id,
        channel=channel,
        chat_type=chat_type,
        peer_id=peer_id,
        conversation_id=conversation_id,
        thread_id=thread_id,
        account_id=account_id,
        label=label,
        surface=surface,
        main_key=main_key,
        direct_scope=direct_scope,
        status=status,
        metadata=dict(metadata or {}),
    )


def build_accept_run_input(
    *,
    source: str,
    content: Any | None = None,
    inbound_metadata: Mapping[str, object] | None = None,
    reply_interface: str | None = None,
    reply_address: str | None = None,
    reply_to: str | None = None,
    reply_metadata: Mapping[str, object] | None = None,
    run_id: str | None = None,
    queue_policy: OrchestrationQueuePolicy = OrchestrationQueuePolicy.FIFO,
    priority: int = 100,
    max_steps: int = 99,
    metadata: Mapping[str, object] | None = None,
) -> AcceptOrchestrationRunInput:
    return AcceptOrchestrationRunInput(
        run_id=run_id,
        inbound_instruction=build_inbound_instruction(
            source=source,
            content=content,
            metadata=inbound_metadata,
        ),
        reply_target=build_reply_target(
            interface_name=reply_interface,
            address=reply_address,
            reply_to=reply_to,
            metadata=reply_metadata,
        ),
        queue_policy=queue_policy,
        priority=priority,
        max_steps=max_steps,
        metadata=dict(metadata or {}),
    )


def build_submit_turn_input(
    *,
    source: str,
    content: Any | None = None,
    agent_id: str,
    llm_id: str | None,
    inbound_metadata: Mapping[str, object] | None = None,
    reply_interface: str | None = None,
    reply_address: str | None = None,
    reply_to: str | None = None,
    reply_metadata: Mapping[str, object] | None = None,
    run_id: str | None = None,
    channel: str | None = None,
    chat_type: str = "direct",
    peer_id: str | None = None,
    conversation_id: str | None = None,
    thread_id: str | None = None,
    account_id: str | None = None,
    label: str | None = None,
    surface: str | None = None,
    main_key: str = "main",
    direct_scope: DirectSessionScope = DirectSessionScope.MAIN,
    status: str = "active",
    session_metadata: Mapping[str, object] | None = None,
    queue_policy: OrchestrationQueuePolicy = OrchestrationQueuePolicy.FIFO,
    priority: int = 100,
    max_steps: int = 99,
    touch_activity: bool = True,
    reset_policy: SessionResetPolicy | None = None,
    metadata: Mapping[str, object] | None = None,
) -> SubmitOrchestrationTurnInput:
    return SubmitOrchestrationTurnInput(
        accept_input=build_accept_run_input(
            source=source,
            content=content,
            inbound_metadata=inbound_metadata,
            reply_interface=reply_interface,
            reply_address=reply_address,
            reply_to=reply_to,
            reply_metadata=reply_metadata,
            run_id=run_id,
            queue_policy=queue_policy,
            priority=priority,
            max_steps=max_steps,
            metadata=metadata,
        ),
        context=build_session_route_context(
            agent_id=agent_id,
            channel=channel,
            chat_type=chat_type,
            peer_id=peer_id,
            conversation_id=conversation_id,
            thread_id=thread_id,
            account_id=account_id,
            label=label,
            surface=surface,
            main_key=main_key,
            direct_scope=direct_scope,
            status=status,
            metadata=session_metadata,
        ),
        requested_llm_id=llm_id,
        touch_activity=touch_activity,
        reset_policy=reset_policy,
        prepare_metadata=dict(metadata or {}),
        enqueue_queue_policy=queue_policy,
        enqueue_priority=priority,
    )


def submit_turn(
    scheduler_service: OrchestrationSchedulerSubmitPort,
    *,
    content: Any,
    options: TurnSubmissionOptions,
    run_id: str | None = None,
    inline_worker_id: str | None = None,
    reply_interface: str | None = None,
    reply_address: str | None = None,
    reply_to: str | None = None,
    reply_metadata: dict[str, object] | None = None,
) -> OrchestrationRun:
    return scheduler_service.submit_turn(
        SubmitOrchestrationTurnInput(
            accept_input=build_accept_run_input(
                source=options.source,
                content=content,
                run_id=run_id,
                reply_interface=reply_interface,
                reply_address=reply_address,
                reply_to=reply_to,
                reply_metadata=reply_metadata,
                queue_policy=options.queue_policy,
                priority=options.priority,
                max_steps=options.max_steps,
            ),
            context=build_session_route_context(
                agent_id=options.agent_id,
                channel=options.channel,
                chat_type=options.chat_type,
                peer_id=options.peer_id,
                conversation_id=options.conversation_id,
                thread_id=options.thread_id,
                account_id=options.account_id,
                main_key=options.main_key,
                direct_scope=options.direct_scope,
            ),
            requested_llm_id=options.llm_id,
            enqueue_queue_policy=options.queue_policy,
            enqueue_priority=options.priority,
        ),
        inline_worker_id=inline_worker_id,
    )


def submit_and_wait_for_turn(
    scheduler_service: OrchestrationSchedulerSubmitPort,
    run_lookup: OrchestrationRunLookupPort,
    events_service: EventsApplicationService | None,
    *,
    content: Any,
    options: AwaitTurnOptions,
) -> OrchestrationRun:
    run = submit_turn(
        scheduler_service,
        content=content,
        options=options,
        inline_worker_id=None,
    )
    deadline = time.monotonic() + options.wait_timeout_seconds
    wait_stopper = StopEvent()
    while time.monotonic() < deadline:
        run = run_lookup.get_run(run.id)
        if terminal(run):
            return run
        if run.stage is OrchestrationRunStage.WAITING_FOR_CONFIRMATION:
            return run

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        wait_timeout = min(options.poll_interval_seconds, remaining)
        session_key = run.session_key.strip() if isinstance(run.session_key, str) else ""
        if events_service is None or not session_key:
            time.sleep(wait_timeout)
            continue
        events_service.wait_for_event_topics(
            (
                EventTopicWatch(
                    topic=turn_session_topic(session_key),
                    after_cursor=events_service.snapshot_event_topic(
                        turn_session_topic(session_key),
                    ),
                ),
            ),
            timeout_seconds=wait_timeout,
            stop_event=wait_stopper,
        )

    raise AwaitTurnTimeoutError(
        f"Turn timed out after {options.wait_timeout_seconds} seconds.",
    )


def extract_output_text(run: OrchestrationRun) -> str | None:
    if run.result_payload is None:
        return None
    payload_output = run.result_payload.get("output_text")
    if isinstance(payload_output, str) and payload_output.strip():
        return payload_output
    return None
