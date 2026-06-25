from __future__ import annotations

from crxzipple.modules.orchestration.application.execution_chain_common import (
    TERMINAL_STEP_STATUSES,
    active_step_of_kind,
    next_item_index,
)
from crxzipple.modules.orchestration.application.execution_chain_contracts import (
    ExecutionChainLifecycleUnitOfWork,
)
from crxzipple.modules.orchestration.application.execution_chain_ids import (
    execution_step_item_id,
)
from crxzipple.modules.orchestration.application.execution_chain_session_items import (
    ensure_session_item_execution_item,
)
from crxzipple.modules.orchestration.domain import (
    ContinuationDecision,
    ExecutionOwnerReference,
    ExecutionStep,
    ExecutionStepItem,
    ExecutionStepItemKind,
    ExecutionStepKind,
    OrchestrationRun,
)


def complete_llm_execution_step(
    uow: ExecutionChainLifecycleUnitOfWork,
    *,
    run: OrchestrationRun,
    llm_invocation_id: str,
    assistant_progress_item_ids: tuple[str, ...] = (),
    summary_payload: dict[str, object] | None = None,
    continuation_payload: dict[str, object] | None = None,
) -> ExecutionStep | None:
    normalized_invocation_id = llm_invocation_id.strip()
    if not normalized_invocation_id:
        return None
    chain = uow.execution_chains.get_active_for_turn(run.id)
    if chain is None:
        return None
    step = active_step_of_kind(
        uow,
        chain,
        ExecutionStepKind.LLM,
    )
    if step is None:
        return None
    _ensure_llm_invocation_item(
        uow,
        step=step,
        llm_invocation_id=normalized_invocation_id,
        summary_payload=summary_payload,
    )
    if continuation_payload:
        _ensure_continuation_decision_item(
            uow,
            step=step,
            llm_invocation_id=normalized_invocation_id,
            summary_payload=continuation_payload,
        )
    item_index_cursor = next_item_index(uow, step.id)
    for item_id in assistant_progress_item_ids:
        _, created = ensure_session_item_execution_item(
            uow,
            step=step,
            session_item_id=item_id,
            item_index=item_index_cursor,
            summary_payload={
                **(summary_payload or {}),
                "message_role": "assistant",
                "llm_invocation_id": normalized_invocation_id,
                "message_kind": "assistant_progress",
                "assistant_progress_item_ids": [item_id],
            },
        )
        if created:
            item_index_cursor += 1
    if step.status not in TERMINAL_STEP_STATUSES:
        step.complete()
        uow.execution_steps.add(step)
        uow.collect(step)
    chain.set_active_step(step.id)
    uow.execution_chains.add(chain)
    uow.collect(chain)
    return step


def record_failed_llm_execution_item(
    uow: ExecutionChainLifecycleUnitOfWork,
    *,
    run: OrchestrationRun,
    llm_invocation_id: str,
    message: str,
    code: str,
    summary_payload: dict[str, object] | None = None,
    details: dict[str, object] | None = None,
) -> ExecutionStepItem | None:
    chain = uow.execution_chains.get_active_for_turn(run.id)
    if chain is None or chain.active_step_id is None:
        return None
    step = uow.execution_steps.get(chain.active_step_id)
    if step is None or step.kind is not ExecutionStepKind.LLM:
        return None
    normalized_llm_invocation_id = llm_invocation_id.strip()
    if not normalized_llm_invocation_id:
        return None
    owner = ExecutionOwnerReference(
        owner_kind="llm_invocation",
        owner_id=normalized_llm_invocation_id,
    )
    existing = uow.execution_step_items.find_by_owner_reference(owner)
    item = next(
        (candidate for candidate in existing if candidate.step_id == step.id),
        None,
    )
    if item is None:
        item_index = next_item_index(uow, step.id)
        item = ExecutionStepItem.create(
            item_id=execution_step_item_id(
                step_id=step.id,
                item_index=item_index,
                kind=ExecutionStepItemKind.LLM_INVOCATION,
            ),
            step_id=step.id,
            chain_id=step.chain_id,
            turn_id=step.turn_id,
            item_index=item_index,
            kind=ExecutionStepItemKind.LLM_INVOCATION,
            owner=owner,
            correlation_key=normalized_llm_invocation_id,
        )
    item.summary_payload = {
        **(item.summary_payload or {}),
        "llm_invocation_id": normalized_llm_invocation_id,
        **(summary_payload or {}),
    }
    item.fail(message=message, code=code, details=details)
    uow.execution_step_items.add(item)
    uow.collect(item)
    return item


def _ensure_llm_invocation_item(
    uow: ExecutionChainLifecycleUnitOfWork,
    *,
    step: ExecutionStep,
    llm_invocation_id: str,
    summary_payload: dict[str, object] | None,
) -> ExecutionStepItem:
    owner = ExecutionOwnerReference(
        owner_kind="llm_invocation",
        owner_id=llm_invocation_id,
    )
    existing = uow.execution_step_items.find_by_owner_reference(owner)
    for item in existing:
        if item.step_id == step.id:
            return item
    item_index = next_item_index(uow, step.id)
    item = ExecutionStepItem.create(
        item_id=execution_step_item_id(
            step_id=step.id,
            item_index=item_index,
            kind=ExecutionStepItemKind.LLM_INVOCATION,
        ),
        step_id=step.id,
        chain_id=step.chain_id,
        turn_id=step.turn_id,
        item_index=item_index,
        kind=ExecutionStepItemKind.LLM_INVOCATION,
        owner=owner,
        correlation_key=llm_invocation_id,
    )
    item.complete(
        summary_payload={
            "llm_invocation_id": llm_invocation_id,
            **(summary_payload or {}),
        },
    )
    uow.execution_step_items.add(item)
    uow.collect(item)
    return item


def _ensure_continuation_decision_item(
    uow: ExecutionChainLifecycleUnitOfWork,
    *,
    step: ExecutionStep,
    llm_invocation_id: str,
    summary_payload: dict[str, object],
) -> ExecutionStepItem:
    owner_id = f"{llm_invocation_id}:continuation"
    decision = ContinuationDecision.from_payload(
        llm_invocation_id=llm_invocation_id,
        continuation_id=owner_id,
        payload=summary_payload,
    )
    owner = ExecutionOwnerReference(
        owner_kind="llm_continuation",
        owner_id=owner_id,
    )
    existing = uow.execution_step_items.find_by_owner_reference(owner)
    for item in existing:
        if item.step_id == step.id:
            return item
    item_index = next_item_index(uow, step.id)
    item = ExecutionStepItem.create(
        item_id=execution_step_item_id(
            step_id=step.id,
            item_index=item_index,
            kind=ExecutionStepItemKind.CONTINUATION_DECISION,
        ),
        step_id=step.id,
        chain_id=step.chain_id,
        turn_id=step.turn_id,
        item_index=item_index,
        kind=ExecutionStepItemKind.CONTINUATION_DECISION,
        owner=owner,
        correlation_key=owner_id,
    )
    item.complete(summary_payload=decision.to_payload())
    uow.execution_step_items.add(item)
    uow.collect(item)
    return item
