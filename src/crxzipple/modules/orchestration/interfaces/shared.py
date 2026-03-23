from __future__ import annotations

import json
from collections.abc import Callable, Mapping

from crxzipple.modules.orchestration.application import (
    AcceptOrchestrationRunInput,
    PrepareSessionRunInput,
)
from crxzipple.modules.orchestration.domain import (
    DeliveryTarget,
    InboundInstruction,
    OrchestrationQueuePolicy,
    OrchestrationRunStage,
    OrchestrationRunStatus,
)
from crxzipple.modules.session.domain import (
    DirectSessionScope,
    SessionResetPolicy,
    SessionRouteContext,
)


OrchestrationInterfaceErrorFactory = Callable[[str], Exception]


def parse_json_object(
    raw: str | None,
    *,
    option_name: str,
    error_factory: OrchestrationInterfaceErrorFactory,
) -> dict[str, object]:
    if raw is None or not raw.strip():
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise error_factory(f"{option_name} must be valid JSON: {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise error_factory(f"{option_name} must decode to a JSON object.")
    return dict(payload)


def parse_direct_scope(
    raw: str,
    *,
    option_name: str,
    error_factory: OrchestrationInterfaceErrorFactory,
) -> DirectSessionScope:
    try:
        return DirectSessionScope(raw)
    except ValueError as exc:
        values = ", ".join(scope.value for scope in DirectSessionScope)
        raise error_factory(f"{option_name} must be one of: {values}") from exc


def parse_run_status(
    raw: str | None,
    *,
    option_name: str,
    error_factory: OrchestrationInterfaceErrorFactory,
) -> OrchestrationRunStatus | None:
    if raw is None:
        return None
    try:
        return OrchestrationRunStatus(raw)
    except ValueError as exc:
        values = ", ".join(item.value for item in OrchestrationRunStatus)
        raise error_factory(f"{option_name} must be one of: {values}") from exc


def parse_queue_policy(
    raw: str | None,
    *,
    option_name: str,
    error_factory: OrchestrationInterfaceErrorFactory,
) -> OrchestrationQueuePolicy | None:
    if raw is None:
        return None
    try:
        return OrchestrationQueuePolicy(raw)
    except ValueError as exc:
        values = ", ".join(item.value for item in OrchestrationQueuePolicy)
        raise error_factory(f"{option_name} must be one of: {values}") from exc


def parse_run_stage(
    raw: str,
    *,
    option_name: str,
    error_factory: OrchestrationInterfaceErrorFactory,
) -> OrchestrationRunStage:
    try:
        return OrchestrationRunStage(raw)
    except ValueError as exc:
        values = ", ".join(
            stage.value
            for stage in (
                OrchestrationRunStage.RUNNING,
                OrchestrationRunStage.LLM,
                OrchestrationRunStage.TOOL,
                OrchestrationRunStage.FINALIZING,
            )
        )
        raise error_factory(f"{option_name} must be one of: {values}") from exc


def build_reset_policy(
    *,
    idle_minutes: int | None,
    daily_reset_hour_utc: int | None,
) -> SessionResetPolicy | None:
    if idle_minutes is None and daily_reset_hour_utc is None:
        return None
    return SessionResetPolicy(
        idle_minutes=idle_minutes,
        daily_reset_hour_utc=daily_reset_hour_utc,
    )


def build_inbound_instruction(
    *,
    source: str,
    content: str | None = None,
    metadata: Mapping[str, object] | None = None,
) -> InboundInstruction:
    return InboundInstruction(
        source=source,
        content=content,
        metadata=dict(metadata or {}),
    )


def build_delivery_target(
    *,
    interface_name: str | None,
    address: str | None = None,
    reply_to: str | None = None,
    metadata: Mapping[str, object] | None = None,
) -> DeliveryTarget | None:
    if interface_name is None:
        return None
    return DeliveryTarget(
        interface_name=interface_name,
        address=address,
        reply_to=reply_to,
        metadata=dict(metadata or {}),
    )


def build_session_route_context(
    *,
    agent_id: str,
    llm_id: str,
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
        llm_id=llm_id,
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
    content: str | None = None,
    inbound_metadata: Mapping[str, object] | None = None,
    delivery_interface: str | None = None,
    delivery_address: str | None = None,
    delivery_reply_to: str | None = None,
    delivery_metadata: Mapping[str, object] | None = None,
    run_id: str | None = None,
    queue_policy: OrchestrationQueuePolicy = OrchestrationQueuePolicy.FIFO,
    priority: int = 100,
    max_steps: int = 12,
    metadata: Mapping[str, object] | None = None,
) -> AcceptOrchestrationRunInput:
    return AcceptOrchestrationRunInput(
        run_id=run_id,
        inbound_instruction=build_inbound_instruction(
            source=source,
            content=content,
            metadata=inbound_metadata,
        ),
        delivery_target=build_delivery_target(
            interface_name=delivery_interface,
            address=delivery_address,
            reply_to=delivery_reply_to,
            metadata=delivery_metadata,
        ),
        queue_policy=queue_policy,
        priority=priority,
        max_steps=max_steps,
        metadata=dict(metadata or {}),
    )


def build_prepare_session_run_input(
    *,
    run_id: str,
    agent_id: str,
    llm_id: str,
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
    touch_activity: bool = True,
    reset_policy: SessionResetPolicy | None = None,
    priority: int | None = None,
    metadata: Mapping[str, object] | None = None,
) -> PrepareSessionRunInput:
    return PrepareSessionRunInput(
        run_id=run_id,
        context=build_session_route_context(
            agent_id=agent_id,
            llm_id=llm_id,
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
        touch_activity=touch_activity,
        reset_policy=reset_policy,
        priority=priority,
        metadata=dict(metadata or {}),
    )
