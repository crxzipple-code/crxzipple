from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Any, Protocol

from crxzipple.modules.orchestration.application.dispatch_owner_kinds import (
    ORCHESTRATION_STEP_DISPATCH_OWNER_KIND,
)
from crxzipple.modules.orchestration.domain import (
    ContinuationDecision,
    ExecutionChain,
    ExecutionChainRepository,
    ExecutionOwnerReference,
    ExecutionStep,
    ExecutionStepItem,
    ExecutionStepItemKind,
    ExecutionStepItemRepository,
    ExecutionStepItemStatus,
    ExecutionStepKind,
    ExecutionStepRepository,
    ExecutionStepStatus,
    ExecutionChainStatus,
    OrchestrationRun,
    PendingApprovalRequest,
)
from crxzipple.shared.domain.aggregates import AggregateRoot

MAX_EXECUTION_ID_LENGTH = 100

INTAKE_OWNER_KIND = "orchestration_ingress_request"
ORCHESTRATION_RUN_INTAKE_OWNER_KIND = "orchestration_run"


class ExecutionChainLifecycleUnitOfWork(Protocol):
    execution_chains: ExecutionChainRepository
    execution_steps: ExecutionStepRepository
    execution_step_items: ExecutionStepItemRepository

    def collect(self, aggregate: AggregateRoot[Any]) -> None:
        ...


@dataclass(frozen=True, slots=True)
class ExecutionChainBootstrap:
    chain: ExecutionChain
    intake_step: ExecutionStep


@dataclass(frozen=True, slots=True)
class ExecutionDispatchStep:
    chain: ExecutionChain
    step: ExecutionStep


def ensure_intake_execution_chain(
    uow: ExecutionChainLifecycleUnitOfWork,
    *,
    run: OrchestrationRun,
    owner: ExecutionOwnerReference,
) -> ExecutionChainBootstrap:
    chain = uow.execution_chains.get_active_for_turn(run.id)
    if chain is None:
        chain = ExecutionChain.create(
            chain_id=_execution_chain_id(run.id),
            turn_id=run.id,
        )
        step = ExecutionStep.create(
            step_id=_execution_step_id(
                turn_id=run.id,
                step_index=0,
                kind=ExecutionStepKind.INTAKE,
            ),
            chain_id=chain.id,
            turn_id=run.id,
            step_index=0,
            kind=ExecutionStepKind.INTAKE,
            correlation_key=_execution_step_correlation_key(
                turn_id=run.id,
                step_index=0,
                kind=ExecutionStepKind.INTAKE,
            ),
        )
        step.link_owner(owner)
        step.wait()
        chain.increment_step_count()
        chain.wait(active_step_id=step.id)
        uow.execution_chains.add(chain)
        uow.execution_steps.add(step)
        uow.collect(chain)
        uow.collect(step)
        return ExecutionChainBootstrap(chain=chain, intake_step=step)

    intake_step = _find_step(
        uow,
        turn_id=run.id,
        step_index=0,
        kind=ExecutionStepKind.INTAKE,
    )
    if intake_step is None:
        intake_step = ExecutionStep.create(
            step_id=_execution_step_id(
                turn_id=run.id,
                step_index=0,
                kind=ExecutionStepKind.INTAKE,
            ),
            chain_id=chain.id,
            turn_id=run.id,
            step_index=0,
            kind=ExecutionStepKind.INTAKE,
            correlation_key=_execution_step_correlation_key(
                turn_id=run.id,
                step_index=0,
                kind=ExecutionStepKind.INTAKE,
            ),
        )
        intake_step.link_owner(owner)
        intake_step.wait()
        chain.increment_step_count()
        chain.wait(active_step_id=intake_step.id)
        uow.execution_chains.add(chain)
        uow.execution_steps.add(intake_step)
        uow.collect(chain)
        uow.collect(intake_step)
    return ExecutionChainBootstrap(chain=chain, intake_step=intake_step)


def prepare_dispatch_execution_step(
    uow: ExecutionChainLifecycleUnitOfWork,
    *,
    run: OrchestrationRun,
    dispatch_task_id: str | None = None,
) -> ExecutionDispatchStep:
    bootstrap = ensure_intake_execution_chain(
        uow,
        run=run,
        owner=ExecutionOwnerReference(
            owner_kind=ORCHESTRATION_RUN_INTAKE_OWNER_KIND,
            owner_id=run.id,
        ),
    )
    chain = bootstrap.chain
    intake_step = bootstrap.intake_step
    if intake_step.status not in _TERMINAL_STEP_STATUSES:
        intake_step.complete()
        uow.execution_steps.add(intake_step)
        uow.collect(intake_step)

    normalized_dispatch_task_id = (
        dispatch_task_id.strip()
        if dispatch_task_id is not None and dispatch_task_id.strip()
        else None
    )
    existing = (
        _find_dispatch_step(uow, chain.id, normalized_dispatch_task_id)
        if normalized_dispatch_task_id is not None
        else None
    )
    next_index = _next_step_index(uow, chain.id)
    existing = existing or _find_step(
        uow,
        turn_id=run.id,
        step_index=next_index,
        kind=ExecutionStepKind.LLM,
    )
    if existing is not None:
        step = existing
    else:
        step = ExecutionStep.create(
            step_id=_execution_step_id(
                turn_id=run.id,
                step_index=next_index,
                kind=ExecutionStepKind.LLM,
            ),
            chain_id=chain.id,
            turn_id=run.id,
            step_index=next_index,
            kind=ExecutionStepKind.LLM,
            correlation_key=_execution_step_correlation_key(
                turn_id=run.id,
                step_index=next_index,
                kind=ExecutionStepKind.LLM,
            ),
        )
        chain.increment_step_count()
        uow.execution_steps.add(step)
        uow.collect(step)

    effective_dispatch_task_id = (
        normalized_dispatch_task_id or step.dispatch_task_id or step.id
    )
    if step.dispatch_task_id != effective_dispatch_task_id:
        step.assign_dispatch_task(effective_dispatch_task_id)
    step.link_owner(
        ExecutionOwnerReference(
            owner_kind=ORCHESTRATION_STEP_DISPATCH_OWNER_KIND,
            owner_id=effective_dispatch_task_id,
        ),
    )
    uow.execution_steps.add(step)
    uow.collect(step)
    chain.start(active_step_id=step.id)
    uow.execution_chains.add(chain)
    uow.collect(chain)
    return ExecutionDispatchStep(chain=chain, step=step)


def start_llm_execution_step(
    uow: ExecutionChainLifecycleUnitOfWork,
    *,
    run: OrchestrationRun,
    dispatch_task_id: str,
) -> ExecutionStep:
    chain = _active_or_bootstrapped_chain(uow, run)
    step = _active_step_of_kind(
        uow,
        chain,
        ExecutionStepKind.LLM,
    )
    step = step or _find_dispatch_step_of_kind(
        uow,
        chain.id,
        dispatch_task_id,
        ExecutionStepKind.LLM,
    )
    if step is None:
        step_index = _next_step_index(uow, chain.id)
        step = ExecutionStep.create(
            step_id=_execution_step_id(
                turn_id=run.id,
                step_index=step_index,
                kind=ExecutionStepKind.LLM,
            ),
            chain_id=chain.id,
            turn_id=run.id,
            step_index=step_index,
            kind=ExecutionStepKind.LLM,
            correlation_key=_execution_step_correlation_key(
                turn_id=run.id,
                step_index=step_index,
                kind=ExecutionStepKind.LLM,
            ),
        )
        chain.increment_step_count()
    step.assign_dispatch_task(dispatch_task_id)
    step.link_owner(
        ExecutionOwnerReference(
            owner_kind=ORCHESTRATION_STEP_DISPATCH_OWNER_KIND,
            owner_id=dispatch_task_id,
        ),
    )
    if step.status not in _TERMINAL_STEP_STATUSES:
        step.start()
    chain.start(active_step_id=step.id)
    uow.execution_steps.add(step)
    uow.execution_chains.add(chain)
    uow.collect(step)
    uow.collect(chain)
    return step


def current_dispatch_task_id(
    uow: ExecutionChainLifecycleUnitOfWork,
    *,
    run: OrchestrationRun,
) -> str | None:
    chain = uow.execution_chains.get_active_for_turn(run.id)
    if chain is None:
        return None
    if chain.active_step_id is not None:
        active_step = uow.execution_steps.get(chain.active_step_id)
        if (
            active_step is not None
            and active_step.dispatch_task_id is not None
            and active_step.dispatch_task_id.strip()
        ):
            return active_step.dispatch_task_id
    for step in reversed(uow.execution_steps.list_for_chain(chain.id)):
        if step.dispatch_task_id is not None and step.dispatch_task_id.strip():
            return step.dispatch_task_id
    return None


def require_current_dispatch_task_id(
    uow: ExecutionChainLifecycleUnitOfWork,
    *,
    run: OrchestrationRun,
) -> str:
    dispatch_task_id = current_dispatch_task_id(uow, run=run)
    if dispatch_task_id is None:
        raise RuntimeError(
            f"No orchestration dispatch execution step was found for run '{run.id}'.",
        )
    return dispatch_task_id


def materialize_tool_batch_execution_step(
    uow: ExecutionChainLifecycleUnitOfWork,
    *,
    run: OrchestrationRun,
    llm_invocation_id: str,
    tool_run_links: tuple[dict[str, object], ...],
) -> ExecutionStep | None:
    normalized_invocation_id = llm_invocation_id.strip()
    if not normalized_invocation_id or not tool_run_links:
        return None
    chain = uow.execution_chains.get_active_for_turn(run.id)
    if chain is None:
        return None
    correlation_key = _tool_batch_correlation_key(
        turn_id=run.id,
        llm_invocation_id=normalized_invocation_id,
    )
    step = uow.execution_steps.get_by_correlation_key(correlation_key)
    if step is None:
        step_index = _next_step_index_after_pending(uow, chain)
        step = ExecutionStep.create(
            step_id=_execution_step_id(
                turn_id=run.id,
                step_index=step_index,
                kind=ExecutionStepKind.TOOL_BATCH,
            ),
            chain_id=chain.id,
            turn_id=run.id,
            step_index=step_index,
            kind=ExecutionStepKind.TOOL_BATCH,
            correlation_key=correlation_key,
        )
        step.link_owner(
            ExecutionOwnerReference(
                owner_kind="llm_invocation",
                owner_id=normalized_invocation_id,
            ),
        )
        chain.increment_step_count()
        uow.execution_steps.add(step)

    has_waiting_runs = False
    next_item_index = _next_item_index(uow, step.id)
    for link in tool_run_links:
        normalized = _normalize_tool_run_link(link)
        if normalized is None:
            continue
        _, created = _ensure_tool_call_item(
            uow,
            step=step,
            link=normalized,
            item_index=next_item_index,
        )
        if created:
            next_item_index += 1
        tool_run_item, created = _ensure_tool_run_item(
            uow,
            step=step,
            link=normalized,
            item_index=next_item_index,
        )
        if created:
            next_item_index += 1
        tool_result_item, created = _ensure_tool_result_item(
            uow,
            step=step,
            link=normalized,
            item_index=next_item_index,
        )
        if created:
            next_item_index += 1
        has_waiting_runs = has_waiting_runs or (
            tool_run_item.status is ExecutionStepItemStatus.WAITING
        )

    if has_waiting_runs:
        step.wait()
        chain.wait(active_step_id=step.id)
    elif step.status not in _TERMINAL_STEP_STATUSES:
        step.complete()
        chain.set_active_step(step.id)
    uow.execution_steps.add(step)
    uow.execution_chains.add(chain)
    uow.collect(step)
    uow.collect(chain)
    return step


def materialize_approval_execution_step(
    uow: ExecutionChainLifecycleUnitOfWork,
    *,
    run: OrchestrationRun,
    request: PendingApprovalRequest,
) -> ExecutionStep | None:
    chain = uow.execution_chains.get_active_for_turn(run.id)
    if chain is None:
        return None
    correlation_key = _approval_correlation_key(
        turn_id=run.id,
        request_id=request.request_id,
    )
    step = uow.execution_steps.get_by_correlation_key(correlation_key)
    if step is None:
        step_index = _next_step_index_after_pending(uow, chain)
        step = ExecutionStep.create(
            step_id=_execution_step_id(
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
    if step.status not in _TERMINAL_STEP_STATUSES:
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
    if item.status not in _TERMINAL_ITEM_STATUSES:
        item.complete(summary_payload=payload)
        uow.execution_step_items.add(item)
        uow.collect(item)
    _complete_step_if_all_items_terminal(uow, step_id=item.step_id)
    return item


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
    step = _active_step_of_kind(
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
    next_item_index = _next_item_index(uow, step.id)
    for item_id in assistant_progress_item_ids:
        _, created = _ensure_session_item_execution_item(
            uow,
            step=step,
            session_item_id=item_id,
            item_index=next_item_index,
            summary_payload={
                **(summary_payload or {}),
                "message_role": "assistant",
                "llm_invocation_id": normalized_invocation_id,
                "message_kind": "assistant_progress",
                "assistant_progress_item_ids": [item_id],
            },
        )
        if created:
            next_item_index += 1
    if step.status not in _TERMINAL_STEP_STATUSES:
        step.complete()
        uow.execution_steps.add(step)
        uow.collect(step)
    chain.set_active_step(step.id)
    uow.execution_chains.add(chain)
    uow.collect(chain)
    return step


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
    if step is not None and step.status not in _TERMINAL_STEP_STATUSES:
        step.fail(message=message, code=code, details=details)
        uow.execution_steps.add(step)
        uow.collect(step)
    if chain.status not in _TERMINAL_CHAIN_STATUSES:
        chain.fail(message=message, code=code, details=details)
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
        item_index = _next_item_index(uow, step.id)
        item = ExecutionStepItem.create(
            item_id=_execution_step_item_id(
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
    if step is not None and step.status not in _TERMINAL_STEP_STATUSES:
        step.cancel()
        uow.execution_steps.add(step)
        uow.collect(step)
    if chain.status not in _TERMINAL_CHAIN_STATUSES:
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
    normalized_reason = _normalized_optional_text(reason) or "resume"
    correlation_key = _resume_correlation_key(
        turn_id=run.id,
        source_step_id=source_step_id,
        reason=normalized_reason,
    )
    step = uow.execution_steps.get_by_correlation_key(correlation_key)
    if step is None:
        step_index = _next_step_index(uow, chain.id)
        step = ExecutionStep.create(
            step_id=_execution_step_id(
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
    if step.status not in _TERMINAL_STEP_STATUSES:
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
    normalized_invocation_id = _normalized_optional_text(llm_invocation_id)
    normalized_item_ids = tuple(
        item_id.strip()
        for item_id in assistant_session_item_ids
        if item_id is not None and item_id.strip()
    )
    if normalized_invocation_id is None and not normalized_item_ids:
        return None
    correlation_key = _final_response_correlation_key(
        turn_id=run.id,
        owner_id=normalized_invocation_id or ":".join(normalized_item_ids),
    )
    step = uow.execution_steps.get_by_correlation_key(correlation_key)
    if step is None:
        step_index = _next_step_index_after_pending(uow, chain)
        step = ExecutionStep.create(
            step_id=_execution_step_id(
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
    next_item_index = _next_item_index(uow, step.id)
    for item_id in normalized_item_ids:
        _, created = _ensure_session_item_execution_item(
            uow,
            step=step,
            session_item_id=item_id,
            item_index=next_item_index,
            summary_payload={
                "item_role": "assistant",
                "llm_invocation_id": normalized_invocation_id,
                **(summary_payload or {}),
            },
        )
        if created:
            next_item_index += 1
    if step.status not in _TERMINAL_STEP_STATUSES:
        step.complete()
    chain.set_active_step(step.id)
    uow.execution_steps.add(step)
    uow.execution_chains.add(chain)
    uow.collect(step)
    uow.collect(chain)
    return step


def mark_tool_run_step_item_terminal(
    uow: ExecutionChainLifecycleUnitOfWork,
    *,
    tool_run_id: str,
    status: str,
    summary_payload: dict[str, object] | None = None,
    error_message: str | None = None,
) -> ExecutionStepItem | None:
    normalized_tool_run_id = tool_run_id.strip()
    if not normalized_tool_run_id:
        return None
    owner = ExecutionOwnerReference(
        owner_kind="tool_run",
        owner_id=normalized_tool_run_id,
    )
    items = uow.execution_step_items.find_by_owner_reference(owner)
    if not items:
        return None
    item = items[-1]
    if item.status not in _TERMINAL_ITEM_STATUSES:
        normalized_status = status.strip().lower()
        payload = {
            **(item.summary_payload or {}),
            "tool_run_id": normalized_tool_run_id,
            "status": normalized_status,
            **(summary_payload or {}),
        }
        step = uow.execution_steps.get(item.step_id)
        chain = uow.execution_chains.get(item.chain_id)
        if _is_late_tool_result_target(step=step, chain=chain):
            item.summary_payload = payload
            item.mark_late_observed()
            uow.execution_step_items.add(item)
            uow.collect(item)
            return item
        if normalized_status == "succeeded":
            item.complete(summary_payload=payload)
        else:
            item.fail(
                message=(
                    error_message.strip()
                    if error_message is not None and error_message.strip()
                    else f"Tool run ended with status '{normalized_status}'."
                ),
                code=f"tool_run_{normalized_status or 'terminal'}",
                details=payload,
            )
            item.summary_payload = payload
        uow.execution_step_items.add(item)
        uow.collect(item)
    _complete_step_if_all_items_terminal(uow, step_id=item.step_id)
    return item


def _active_or_bootstrapped_chain(
    uow: ExecutionChainLifecycleUnitOfWork,
    run: OrchestrationRun,
) -> ExecutionChain:
    chain = uow.execution_chains.get_active_for_turn(run.id)
    if chain is not None:
        return chain
    return ensure_intake_execution_chain(
        uow,
        run=run,
        owner=ExecutionOwnerReference(
            owner_kind=ORCHESTRATION_RUN_INTAKE_OWNER_KIND,
            owner_id=run.id,
        ),
    ).chain


def _ensure_tool_call_item(
    uow: ExecutionChainLifecycleUnitOfWork,
    *,
    step: ExecutionStep,
    link: dict[str, object],
    item_index: int,
) -> tuple[ExecutionStepItem, bool]:
    tool_call_id = str(link["tool_call_id"])
    owner = ExecutionOwnerReference(owner_kind="tool_call", owner_id=tool_call_id)
    existing = uow.execution_step_items.find_by_owner_reference(owner)
    for item in existing:
        if item.step_id == step.id:
            return item, False
    item = ExecutionStepItem.create(
        item_id=_execution_step_item_id(
            step_id=step.id,
            item_index=item_index,
            kind=ExecutionStepItemKind.TOOL_CALL,
        ),
        step_id=step.id,
        chain_id=step.chain_id,
        turn_id=step.turn_id,
        item_index=item_index,
        kind=ExecutionStepItemKind.TOOL_CALL,
        owner=owner,
        correlation_key=tool_call_id,
    )
    item.complete(summary_payload=_tool_call_summary(link))
    uow.execution_step_items.add(item)
    uow.collect(item)
    return item, True


def materialize_tool_result_session_item_items(
    uow: ExecutionChainLifecycleUnitOfWork,
    *,
    run: OrchestrationRun,
    tool_result_item_links: tuple[tuple[str, str], ...],
) -> tuple[ExecutionStepItem, ...]:
    created_or_existing: list[ExecutionStepItem] = []
    for tool_run_id, session_item_id in tool_result_item_links:
        normalized_tool_run_id = tool_run_id.strip()
        normalized_session_item_id = session_item_id.strip()
        if not normalized_tool_run_id or not normalized_session_item_id:
            continue
        tool_run_items = uow.execution_step_items.find_by_owner_reference(
            ExecutionOwnerReference(
                owner_kind="tool_run",
                owner_id=normalized_tool_run_id,
            ),
        )
        tool_run_item = next(
            (
                item
                for item in reversed(tool_run_items)
                if item.turn_id == run.id
            ),
            None,
        )
        if tool_run_item is None:
            continue
        step = uow.execution_steps.get(tool_run_item.step_id)
        if step is None:
            continue
        summary = (
            dict(tool_run_item.summary_payload)
            if isinstance(tool_run_item.summary_payload, dict)
            else {}
        )
        link = {
            **summary,
            "tool_run_id": normalized_tool_run_id,
            "result_session_item_id": normalized_session_item_id,
        }
        if _normalize_tool_run_link(link) is None:
            continue
        item, _ = _ensure_tool_result_item(
            uow,
            step=step,
            link=link,
            item_index=_next_item_index(uow, step.id),
        )
        if item is not None:
            created_or_existing.append(item)
    return tuple(created_or_existing)


def _ensure_tool_run_item(
    uow: ExecutionChainLifecycleUnitOfWork,
    *,
    step: ExecutionStep,
    link: dict[str, object],
    item_index: int,
) -> tuple[ExecutionStepItem, bool]:
    tool_run_id = str(link["tool_run_id"])
    owner = ExecutionOwnerReference(owner_kind="tool_run", owner_id=tool_run_id)
    existing = uow.execution_step_items.find_by_owner_reference(owner)
    for item in existing:
        if item.step_id == step.id:
            return item, False
    item = ExecutionStepItem.create(
        item_id=_execution_step_item_id(
            step_id=step.id,
            item_index=item_index,
            kind=ExecutionStepItemKind.TOOL_RUN,
        ),
        step_id=step.id,
        chain_id=step.chain_id,
        turn_id=step.turn_id,
        item_index=item_index,
        kind=ExecutionStepItemKind.TOOL_RUN,
        owner=owner,
        correlation_key=str(link["tool_call_id"]),
    )
    if bool(link.get("background")):
        item.wait()
    else:
        item.complete(summary_payload=_tool_run_summary(link))
    if item.status is ExecutionStepItemStatus.WAITING:
        item.summary_payload = _tool_run_summary(link)
    uow.execution_step_items.add(item)
    uow.collect(item)
    return item, True


def _ensure_tool_result_item(
    uow: ExecutionChainLifecycleUnitOfWork,
    *,
    step: ExecutionStep,
    link: dict[str, object],
    item_index: int,
) -> tuple[ExecutionStepItem | None, bool]:
    result_session_item_id = _normalized_optional_text(
        _optional_text(link.get("result_session_item_id")),
    )
    if result_session_item_id is None:
        return None, False
    owner = ExecutionOwnerReference(
        owner_kind="session_item",
        owner_id=result_session_item_id,
    )
    existing = uow.execution_step_items.find_by_owner_reference(owner)
    for item in existing:
        if item.step_id == step.id and item.kind is ExecutionStepItemKind.TOOL_RESULT:
            return item, False
    item = ExecutionStepItem.create(
        item_id=_execution_step_item_id(
            step_id=step.id,
            item_index=item_index,
            kind=ExecutionStepItemKind.TOOL_RESULT,
        ),
        step_id=step.id,
        chain_id=step.chain_id,
        turn_id=step.turn_id,
        item_index=item_index,
        kind=ExecutionStepItemKind.TOOL_RESULT,
        owner=owner,
        correlation_key=str(link["tool_call_id"]),
    )
    item.payload_ref = {
        "kind": "session_item",
        "tool_run_id": str(link["tool_run_id"]),
        "session_item_id": result_session_item_id,
    }
    item.complete(
        summary_payload=_tool_result_summary(
            link,
            result_session_item_id=result_session_item_id,
        ),
    )
    uow.execution_step_items.add(item)
    uow.collect(item)
    return item, True


def _ensure_session_item_execution_item(
    uow: ExecutionChainLifecycleUnitOfWork,
    *,
    step: ExecutionStep,
    session_item_id: str,
    item_index: int,
    summary_payload: dict[str, object] | None = None,
) -> tuple[ExecutionStepItem, bool]:
    normalized_item_id = session_item_id.strip()
    owner = ExecutionOwnerReference(
        owner_kind="session_item",
        owner_id=normalized_item_id,
    )
    existing = uow.execution_step_items.find_by_owner_reference(owner)
    for item in existing:
        if item.step_id == step.id and item.kind is ExecutionStepItemKind.SESSION_MESSAGE:
            return item, False
    item = ExecutionStepItem.create(
        item_id=_execution_step_item_id(
            step_id=step.id,
            item_index=item_index,
            kind=ExecutionStepItemKind.SESSION_MESSAGE,
        ),
        step_id=step.id,
        chain_id=step.chain_id,
        turn_id=step.turn_id,
        item_index=item_index,
        kind=ExecutionStepItemKind.SESSION_MESSAGE,
        owner=owner,
        correlation_key=normalized_item_id,
    )
    item.payload_ref = {
        "kind": "session_item",
        "session_item_id": normalized_item_id,
    }
    item.complete(
        summary_payload={
            "session_item_id": normalized_item_id,
            **(summary_payload or {}),
        },
    )
    uow.execution_step_items.add(item)
    uow.collect(item)
    return item, True


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
    item_index = _next_item_index(uow, step.id)
    item = ExecutionStepItem.create(
        item_id=_execution_step_item_id(
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


def _complete_step_if_all_items_terminal(
    uow: ExecutionChainLifecycleUnitOfWork,
    *,
    step_id: str,
) -> None:
    step = uow.execution_steps.get(step_id)
    if step is None:
        return
    items = uow.execution_step_items.list_for_step(step.id)
    if not items:
        return
    if any(item.status not in _TERMINAL_ITEM_STATUSES for item in items):
        return
    if step.status not in _TERMINAL_STEP_STATUSES:
        step.complete()
        uow.execution_steps.add(step)
        uow.collect(step)
    chain = uow.execution_chains.get(step.chain_id)
    if chain is not None:
        chain.set_active_step(step.id)
        uow.execution_chains.add(chain)
        uow.collect(chain)


def _is_late_tool_result_target(
    *,
    step: ExecutionStep | None,
    chain: ExecutionChain | None,
) -> bool:
    if step is None or chain is None:
        return False
    if step.status in _TERMINAL_STEP_STATUSES:
        return True
    return chain.status in _TERMINAL_CHAIN_STATUSES


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
    item_index = _next_item_index(uow, step.id)
    item = ExecutionStepItem.create(
        item_id=_execution_step_item_id(
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
    item_index = _next_item_index(uow, step.id)
    item = ExecutionStepItem.create(
        item_id=_execution_step_item_id(
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


def _normalize_tool_run_link(
    link: dict[str, object],
) -> dict[str, object] | None:
    tool_call_id = _normalized_optional_text(_optional_text(link.get("tool_call_id")))
    tool_run_id = _normalized_optional_text(_optional_text(link.get("tool_run_id")))
    tool_name = _normalized_optional_text(_optional_text(link.get("tool_name")))
    if tool_call_id is None or tool_run_id is None or tool_name is None:
        return None
    normalized = dict(link)
    normalized["tool_call_id"] = tool_call_id
    normalized["tool_run_id"] = tool_run_id
    normalized["tool_name"] = tool_name
    return normalized


def _tool_call_summary(link: dict[str, object]) -> dict[str, object]:
    return {
        key: value
        for key, value in {
        "tool_call_id": link.get("tool_call_id"),
        "tool_name": link.get("tool_name"),
        "tool_id": link.get("tool_id"),
        "call_session_item_id": link.get("call_session_item_id"),
        "mode": link.get("mode"),
        "strategy": link.get("strategy"),
        "environment": link.get("environment"),
        }.items()
        if value is not None
    }


def _tool_run_summary(link: dict[str, object]) -> dict[str, object]:
    return {
        key: value
        for key, value in {
            "tool_run_id": link.get("tool_run_id"),
            "tool_call_id": link.get("tool_call_id"),
            "tool_name": link.get("tool_name"),
            "tool_id": link.get("tool_id"),
            "status": link.get("status"),
            "result_session_item_id": link.get("result_session_item_id"),
            "background": bool(link.get("background")),
            "mode": link.get("mode"),
            "strategy": link.get("strategy"),
            "environment": link.get("environment"),
            "tool_execution_plan": _tool_execution_plan_summary(link),
            "tool_lifecycle": _tool_lifecycle_summary(link),
        }.items()
        if value is not None
    }


def _tool_result_summary(
    link: dict[str, object],
    *,
    result_session_item_id: str | None,
) -> dict[str, object]:
    return {
        key: value
        for key, value in {
            "tool_run_id": link.get("tool_run_id"),
            "tool_call_id": link.get("tool_call_id"),
            "tool_name": link.get("tool_name"),
            "tool_id": link.get("tool_id"),
            "result_session_item_id": result_session_item_id,
            "tool_execution_plan": _tool_execution_plan_summary(link),
            "tool_lifecycle": _tool_lifecycle_summary(link),
        }.items()
        if value is not None
    }


def _tool_execution_plan_summary(link: dict[str, object]) -> dict[str, object] | None:
    raw = link.get("tool_execution_plan")
    if not isinstance(raw, dict):
        return None
    payload = {
        key: raw[key]
        for key in (
            "tool_call_id",
            "tool_name",
            "tool_id",
            "mode",
            "strategy",
            "environment",
            "resource_policy",
            "arguments_digest",
        )
        if key in raw
    }
    return payload or None


def _tool_lifecycle_summary(link: dict[str, object]) -> dict[str, object] | None:
    raw = link.get("tool_lifecycle")
    if not isinstance(raw, dict):
        return None
    payload = {
        key: raw[key]
        for key in (
            "superseded",
            "superseded_by_tool_call_id",
            "replaced_by_tool_call_id",
            "replacement_tool_call_id",
            "supersedes_tool_call_id",
            "supersedes_tool_run_id",
            "supersedes_result_session_item_id",
            "lifecycle_status",
            "evidence_lifecycle_status",
            "evidence_lifecycle",
        )
        if key in raw
    }
    return payload or None


def _next_item_index(
    uow: ExecutionChainLifecycleUnitOfWork,
    step_id: str,
) -> int:
    items = uow.execution_step_items.list_for_step(step_id)
    if not items:
        return 0
    return max(item.item_index for item in items) + 1


def _active_step_of_kind(
    uow: ExecutionChainLifecycleUnitOfWork,
    chain: ExecutionChain,
    kind: ExecutionStepKind,
) -> ExecutionStep | None:
    if chain.active_step_id is None:
        return None
    step = uow.execution_steps.get(chain.active_step_id)
    if step is None or step.kind is not kind:
        return None
    if step.status in _TERMINAL_STEP_STATUSES:
        return None
    return step


def _find_dispatch_step_of_kind(
    uow: ExecutionChainLifecycleUnitOfWork,
    chain_id: str,
    dispatch_task_id: str,
    kind: ExecutionStepKind,
) -> ExecutionStep | None:
    for step in uow.execution_steps.list_for_chain(chain_id):
        if (
            step.kind is kind
            and step.dispatch_task_id == dispatch_task_id
            and step.status not in _TERMINAL_STEP_STATUSES
        ):
            return step
    return None


def _find_step(
    uow: ExecutionChainLifecycleUnitOfWork,
    *,
    turn_id: str,
    step_index: int,
    kind: ExecutionStepKind,
) -> ExecutionStep | None:
    return uow.execution_steps.get_by_correlation_key(
        _execution_step_correlation_key(
            turn_id=turn_id,
            step_index=step_index,
            kind=kind,
        ),
    )


def _next_step_index(
    uow: ExecutionChainLifecycleUnitOfWork,
    chain_id: str,
) -> int:
    steps = uow.execution_steps.list_for_chain(chain_id)
    if not steps:
        return 0
    return max(step.step_index for step in steps) + 1


def _next_step_index_after_pending(
    uow: ExecutionChainLifecycleUnitOfWork,
    chain: ExecutionChain,
) -> int:
    return max(_next_step_index(uow, chain.id), chain.step_count)


def _find_dispatch_step(
    uow: ExecutionChainLifecycleUnitOfWork,
    chain_id: str,
    dispatch_task_id: str,
) -> ExecutionStep | None:
    for step in uow.execution_steps.list_for_chain(chain_id):
        if (
            step.kind is ExecutionStepKind.LLM
            and step.dispatch_task_id == dispatch_task_id
            and step.status not in _TERMINAL_STEP_STATUSES
        ):
            return step
    return None


def _tool_batch_correlation_key(
    *,
    turn_id: str,
    llm_invocation_id: str,
) -> str:
    return f"{turn_id}:tool_batch:{llm_invocation_id}"


def _approval_correlation_key(
    *,
    turn_id: str,
    request_id: str,
) -> str:
    return f"{turn_id}:approval:{request_id}"


def _resume_correlation_key(
    *,
    turn_id: str,
    source_step_id: str,
    reason: str,
) -> str:
    return f"{turn_id}:resume:{source_step_id}:{reason}"


def _final_response_correlation_key(
    *,
    turn_id: str,
    owner_id: str,
) -> str:
    return f"{turn_id}:final_response:{owner_id}"


def _execution_chain_id(turn_id: str) -> str:
    return _bounded_id("chain", turn_id)


def _execution_step_id(
    *,
    turn_id: str,
    step_index: int,
    kind: ExecutionStepKind,
) -> str:
    return _bounded_id("step", f"{turn_id}:{step_index}:{kind.value}")


def _execution_step_item_id(
    *,
    step_id: str,
    item_index: int,
    kind: ExecutionStepItemKind,
) -> str:
    return _bounded_id("item", f"{step_id}:{item_index}:{kind.value}")


def _execution_step_correlation_key(
    *,
    turn_id: str,
    step_index: int,
    kind: ExecutionStepKind,
) -> str:
    return f"{turn_id}:{step_index}:{kind.value}"


def _bounded_id(prefix: str, value: str) -> str:
    raw = f"{prefix}:{value}"
    if len(raw) <= MAX_EXECUTION_ID_LENGTH:
        return raw
    digest = sha256(raw.encode("utf-8")).hexdigest()
    return f"{prefix}:{digest}"


def _optional_text(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _normalized_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


_TERMINAL_STEP_STATUSES = frozenset(
    {
        ExecutionStepStatus.COMPLETED,
        ExecutionStepStatus.FAILED,
        ExecutionStepStatus.CANCELLED,
    },
)

_TERMINAL_CHAIN_STATUSES = frozenset(
    {
        ExecutionChainStatus.COMPLETED,
        ExecutionChainStatus.FAILED,
        ExecutionChainStatus.CANCELLED,
    },
)

_TERMINAL_ITEM_STATUSES = frozenset(
    {
        ExecutionStepItemStatus.COMPLETED,
        ExecutionStepItemStatus.FAILED,
        ExecutionStepItemStatus.CANCELLED,
        ExecutionStepItemStatus.LATE_OBSERVED,
        ExecutionStepItemStatus.LATE_IGNORED,
    },
)


__all__ = [
    "ExecutionChainBootstrap",
    "ExecutionDispatchStep",
    "INTAKE_OWNER_KIND",
    "cancel_active_execution_step",
    "complete_execution_chain",
    "complete_llm_execution_step",
    "ensure_intake_execution_chain",
    "fail_active_execution_step",
    "mark_approval_request_step_item_terminal",
    "mark_tool_run_step_item_terminal",
    "materialize_approval_execution_step",
    "materialize_final_response_execution_step",
    "materialize_resume_execution_step",
    "materialize_tool_batch_execution_step",
    "materialize_tool_result_session_item_items",
    "prepare_dispatch_execution_step",
    "start_llm_execution_step",
]
