from __future__ import annotations

from crxzipple.modules.orchestration.application.execution_chain_common import (
    TERMINAL_CHAIN_STATUSES,
    TERMINAL_STEP_STATUSES,
    next_item_index,
    next_step_index,
    next_step_index_after_pending,
    normalized_optional_text,
)
from crxzipple.modules.orchestration.application.execution_chain_contracts import (
    ExecutionChainLifecycleUnitOfWork,
)
from crxzipple.modules.orchestration.application.execution_chain_ids import (
    execution_step_id,
    final_response_correlation_key,
    resume_correlation_key,
)
from crxzipple.modules.orchestration.application.execution_chain_session_items import (
    ensure_session_item_execution_item,
)
from crxzipple.modules.orchestration.domain import (
    ExecutionChain,
    ExecutionOwnerReference,
    ExecutionStep,
    ExecutionStepKind,
    OrchestrationRun,
)


def fail_active_execution_step(
    uow: ExecutionChainLifecycleUnitOfWork,
    *,
    run: OrchestrationRun,
    message: str,
    code: str,
    details: dict[str, object] | None = None,
) -> ExecutionStep | None:
    chain = uow.execution_chains.get_active_for_turn(run.id)
    if chain is None:
        return None
    step = (
        uow.execution_steps.get(chain.active_step_id)
        if chain.active_step_id is not None
        else None
    )
    if step is not None and step.status not in TERMINAL_STEP_STATUSES:
        step.fail(message=message, code=code, details=details)
        uow.execution_steps.add(step)
        uow.collect(step)
    if chain.status not in TERMINAL_CHAIN_STATUSES:
        chain.fail(message=message, code=code, details=details)
        uow.execution_chains.add(chain)
        uow.collect(chain)
    return step


def cancel_active_execution_step(
    uow: ExecutionChainLifecycleUnitOfWork,
    *,
    run: OrchestrationRun,
) -> ExecutionStep | None:
    chain = uow.execution_chains.get_active_for_turn(run.id)
    if chain is None:
        return None
    step = (
        uow.execution_steps.get(chain.active_step_id)
        if chain.active_step_id is not None
        else None
    )
    if step is not None and step.status not in TERMINAL_STEP_STATUSES:
        step.cancel()
        uow.execution_steps.add(step)
        uow.collect(step)
    if chain.status not in TERMINAL_CHAIN_STATUSES:
        chain.cancel()
        uow.execution_chains.add(chain)
        uow.collect(chain)
    return step


def complete_execution_chain(
    uow: ExecutionChainLifecycleUnitOfWork,
    *,
    run: OrchestrationRun,
) -> ExecutionChain | None:
    chain = uow.execution_chains.get_active_for_turn(run.id)
    if chain is None:
        return None
    chain.complete()
    uow.execution_chains.add(chain)
    uow.collect(chain)
    return chain


def materialize_resume_execution_step(
    uow: ExecutionChainLifecycleUnitOfWork,
    *,
    run: OrchestrationRun,
    reason: str | None = None,
) -> ExecutionStep | None:
    chain = uow.execution_chains.get_active_for_turn(run.id)
    if chain is None:
        return None
    source_step_id = chain.active_step_id or "none"
    normalized_reason = normalized_optional_text(reason) or "resume"
    correlation_key = resume_correlation_key(
        turn_id=run.id,
        source_step_id=source_step_id,
        reason=normalized_reason,
    )
    step = uow.execution_steps.get_by_correlation_key(correlation_key)
    if step is None:
        step_index = next_step_index(uow, chain.id)
        step = ExecutionStep.create(
            step_id=execution_step_id(
                turn_id=run.id,
                step_index=step_index,
                kind=ExecutionStepKind.TOOL_RESUME,
            ),
            chain_id=chain.id,
            turn_id=run.id,
            step_index=step_index,
            kind=ExecutionStepKind.TOOL_RESUME,
            correlation_key=correlation_key,
        )
        step.link_owner(
            ExecutionOwnerReference(
                owner_kind="orchestration_resume",
                owner_id=f"{source_step_id}:{normalized_reason}",
            ),
        )
        chain.increment_step_count()
    if step.status not in TERMINAL_STEP_STATUSES:
        step.complete()
    chain.start(active_step_id=step.id)
    uow.execution_steps.add(step)
    uow.execution_chains.add(chain)
    uow.collect(step)
    uow.collect(chain)
    return step


def materialize_final_response_execution_step(
    uow: ExecutionChainLifecycleUnitOfWork,
    *,
    run: OrchestrationRun,
    llm_invocation_id: str | None,
    assistant_session_item_ids: tuple[str, ...] = (),
    summary_payload: dict[str, object] | None = None,
) -> ExecutionStep | None:
    chain = uow.execution_chains.get_active_for_turn(run.id)
    if chain is None:
        return None
    normalized_invocation_id = normalized_optional_text(llm_invocation_id)
    normalized_item_ids = tuple(
        item_id.strip()
        for item_id in assistant_session_item_ids
        if item_id is not None and item_id.strip()
    )
    if normalized_invocation_id is None and not normalized_item_ids:
        return None
    correlation_key = final_response_correlation_key(
        turn_id=run.id,
        owner_id=normalized_invocation_id or ":".join(normalized_item_ids),
    )
    step = uow.execution_steps.get_by_correlation_key(correlation_key)
    if step is None:
        step_index = next_step_index_after_pending(uow, chain)
        step = ExecutionStep.create(
            step_id=execution_step_id(
                turn_id=run.id,
                step_index=step_index,
                kind=ExecutionStepKind.FINAL_RESPONSE,
            ),
            chain_id=chain.id,
            turn_id=run.id,
            step_index=step_index,
            kind=ExecutionStepKind.FINAL_RESPONSE,
            correlation_key=correlation_key,
        )
        step.link_owner(
            ExecutionOwnerReference(
                owner_kind=(
                    "llm_invocation"
                    if normalized_invocation_id is not None
                    else "session_item"
                ),
                owner_id=normalized_invocation_id or normalized_item_ids[-1],
            ),
        )
        chain.increment_step_count()
        uow.execution_steps.add(step)
    item_index_cursor = next_item_index(uow, step.id)
    for item_id in normalized_item_ids:
        _, created = ensure_session_item_execution_item(
            uow,
            step=step,
            session_item_id=item_id,
            item_index=item_index_cursor,
            summary_payload={
                "item_role": "assistant",
                "llm_invocation_id": normalized_invocation_id,
                **(summary_payload or {}),
            },
        )
        if created:
            item_index_cursor += 1
    if step.status not in TERMINAL_STEP_STATUSES:
        step.complete()
    chain.set_active_step(step.id)
    uow.execution_steps.add(step)
    uow.execution_chains.add(chain)
    uow.collect(step)
    uow.collect(chain)
    return step
