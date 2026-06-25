from __future__ import annotations

from crxzipple.modules.orchestration.application.execution_chain_common import (
    TERMINAL_ITEM_STATUSES,
    TERMINAL_STEP_STATUSES,
    complete_step_if_all_items_terminal,
    next_item_index,
    next_step_index_after_pending,
)
from crxzipple.modules.orchestration.application.execution_chain_contracts import (
    ExecutionChainLifecycleUnitOfWork,
)
from crxzipple.modules.orchestration.application.execution_chain_ids import (
    approval_correlation_key,
    execution_step_id,
    execution_step_item_id,
)
from crxzipple.modules.orchestration.domain import (
    ExecutionOwnerReference,
    ExecutionStep,
    ExecutionStepItem,
    ExecutionStepItemKind,
    ExecutionStepKind,
    OrchestrationRun,
    PendingApprovalRequest,
)


def materialize_approval_execution_step(
    uow: ExecutionChainLifecycleUnitOfWork,
    *,
    run: OrchestrationRun,
    request: PendingApprovalRequest,
) -> ExecutionStep | None:
    chain = uow.execution_chains.get_active_for_turn(run.id)
    if chain is None:
        return None
    correlation_key = approval_correlation_key(
        turn_id=run.id,
        request_id=request.request_id,
    )
    step = uow.execution_steps.get_by_correlation_key(correlation_key)
    if step is None:
        step_index = next_step_index_after_pending(uow, chain)
        step = ExecutionStep.create(
            step_id=execution_step_id(
                turn_id=run.id,
                step_index=step_index,
                kind=ExecutionStepKind.APPROVAL,
            ),
            chain_id=chain.id,
            turn_id=run.id,
            step_index=step_index,
            kind=ExecutionStepKind.APPROVAL,
            correlation_key=correlation_key,
        )
        step.link_owner(
            ExecutionOwnerReference(
                owner_kind="approval_request",
                owner_id=request.request_id,
            ),
        )
        chain.increment_step_count()
        uow.execution_steps.add(step)
    _ensure_approval_request_item(
        uow,
        step=step,
        request=request,
    )
    if step.status not in TERMINAL_STEP_STATUSES:
        step.wait()
    chain.wait(active_step_id=step.id)
    uow.execution_steps.add(step)
    uow.execution_chains.add(chain)
    uow.collect(step)
    uow.collect(chain)
    return step


def mark_approval_request_step_item_terminal(
    uow: ExecutionChainLifecycleUnitOfWork,
    *,
    request_id: str,
    decision: str,
) -> ExecutionStepItem | None:
    normalized_request_id = request_id.strip()
    if not normalized_request_id:
        return None
    owner = ExecutionOwnerReference(
        owner_kind="approval_request",
        owner_id=normalized_request_id,
    )
    items = uow.execution_step_items.find_by_owner_reference(owner)
    if not items:
        return None
    item = items[-1]
    normalized_decision = decision.strip().lower()
    payload = {
        **(item.summary_payload or {}),
        "request_id": normalized_request_id,
        "decision": normalized_decision,
    }
    if item.status not in TERMINAL_ITEM_STATUSES:
        item.complete(summary_payload=payload)
        uow.execution_step_items.add(item)
        uow.collect(item)
    complete_step_if_all_items_terminal(uow, step_id=item.step_id)
    return item


def _ensure_approval_request_item(
    uow: ExecutionChainLifecycleUnitOfWork,
    *,
    step: ExecutionStep,
    request: PendingApprovalRequest,
) -> ExecutionStepItem:
    owner = ExecutionOwnerReference(
        owner_kind="approval_request",
        owner_id=request.request_id,
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
            kind=ExecutionStepItemKind.APPROVAL_REQUEST,
        ),
        step_id=step.id,
        chain_id=step.chain_id,
        turn_id=step.turn_id,
        item_index=item_index,
        kind=ExecutionStepItemKind.APPROVAL_REQUEST,
        owner=owner,
        correlation_key=request.request_id,
    )
    item.wait()
    item.summary_payload = request.to_payload()
    uow.execution_step_items.add(item)
    uow.collect(item)
    return item
