from __future__ import annotations

from crxzipple.modules.orchestration.application.execution_chain_contracts import (
    ExecutionChainLifecycleUnitOfWork,
)
from crxzipple.modules.orchestration.application.execution_chain_ids import (
    execution_step_correlation_key,
)
from crxzipple.modules.orchestration.domain import (
    ExecutionChain,
    ExecutionChainStatus,
    ExecutionStep,
    ExecutionStepItemStatus,
    ExecutionStepKind,
    ExecutionStepStatus,
)


TERMINAL_STEP_STATUSES = frozenset(
    {
        ExecutionStepStatus.COMPLETED,
        ExecutionStepStatus.FAILED,
        ExecutionStepStatus.CANCELLED,
    },
)

TERMINAL_CHAIN_STATUSES = frozenset(
    {
        ExecutionChainStatus.COMPLETED,
        ExecutionChainStatus.FAILED,
        ExecutionChainStatus.CANCELLED,
    },
)

TERMINAL_ITEM_STATUSES = frozenset(
    {
        ExecutionStepItemStatus.COMPLETED,
        ExecutionStepItemStatus.FAILED,
        ExecutionStepItemStatus.CANCELLED,
        ExecutionStepItemStatus.LATE_OBSERVED,
        ExecutionStepItemStatus.LATE_IGNORED,
    },
)


def optional_text(value: object) -> str | None:
    return value if isinstance(value, str) else None


def normalized_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def next_item_index(
    uow: ExecutionChainLifecycleUnitOfWork,
    step_id: str,
) -> int:
    items = uow.execution_step_items.list_for_step(step_id)
    if not items:
        return 0
    return max(item.item_index for item in items) + 1


def next_step_index(
    uow: ExecutionChainLifecycleUnitOfWork,
    chain_id: str,
) -> int:
    steps = uow.execution_steps.list_for_chain(chain_id)
    if not steps:
        return 0
    return max(step.step_index for step in steps) + 1


def next_step_index_after_pending(
    uow: ExecutionChainLifecycleUnitOfWork,
    chain: ExecutionChain,
) -> int:
    return max(next_step_index(uow, chain.id), chain.step_count)


def active_step_of_kind(
    uow: ExecutionChainLifecycleUnitOfWork,
    chain: ExecutionChain,
    kind: ExecutionStepKind,
) -> ExecutionStep | None:
    if chain.active_step_id is None:
        return None
    step = uow.execution_steps.get(chain.active_step_id)
    if step is None or step.kind is not kind:
        return None
    if step.status in TERMINAL_STEP_STATUSES:
        return None
    return step


def find_dispatch_step_of_kind(
    uow: ExecutionChainLifecycleUnitOfWork,
    chain_id: str,
    dispatch_task_id: str,
    kind: ExecutionStepKind,
) -> ExecutionStep | None:
    for step in uow.execution_steps.list_for_chain(chain_id):
        if (
            step.kind is kind
            and step.dispatch_task_id == dispatch_task_id
            and step.status not in TERMINAL_STEP_STATUSES
        ):
            return step
    return None


def find_step(
    uow: ExecutionChainLifecycleUnitOfWork,
    *,
    turn_id: str,
    step_index: int,
    kind: ExecutionStepKind,
) -> ExecutionStep | None:
    return uow.execution_steps.get_by_correlation_key(
        execution_step_correlation_key(
            turn_id=turn_id,
            step_index=step_index,
            kind=kind,
        ),
    )


def find_dispatch_step(
    uow: ExecutionChainLifecycleUnitOfWork,
    chain_id: str,
    dispatch_task_id: str,
) -> ExecutionStep | None:
    for step in uow.execution_steps.list_for_chain(chain_id):
        if (
            step.kind is ExecutionStepKind.LLM
            and step.dispatch_task_id == dispatch_task_id
            and step.status not in TERMINAL_STEP_STATUSES
        ):
            return step
    return None


def complete_step_if_all_items_terminal(
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
    if any(item.status not in TERMINAL_ITEM_STATUSES for item in items):
        return
    if step.status not in TERMINAL_STEP_STATUSES:
        step.complete()
        uow.execution_steps.add(step)
        uow.collect(step)
    chain = uow.execution_chains.get(step.chain_id)
    if chain is not None:
        chain.set_active_step(step.id)
        uow.execution_chains.add(chain)
        uow.collect(chain)


def is_late_tool_result_target(
    *,
    step: ExecutionStep | None,
    chain: ExecutionChain | None,
) -> bool:
    if step is None or chain is None:
        return False
    if step.status in TERMINAL_STEP_STATUSES:
        return True
    return chain.status in TERMINAL_CHAIN_STATUSES
