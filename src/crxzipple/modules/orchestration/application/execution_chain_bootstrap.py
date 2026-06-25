from __future__ import annotations

from crxzipple.modules.orchestration.application.dispatch_owner_kinds import (
    ORCHESTRATION_STEP_DISPATCH_OWNER_KIND,
)
from crxzipple.modules.orchestration.application.execution_chain_common import (
    TERMINAL_STEP_STATUSES,
    active_step_of_kind,
    find_dispatch_step,
    find_dispatch_step_of_kind,
    find_step,
    next_step_index,
)
from crxzipple.modules.orchestration.application.execution_chain_contracts import (
    ORCHESTRATION_RUN_INTAKE_OWNER_KIND,
    ExecutionChainBootstrap,
    ExecutionChainLifecycleUnitOfWork,
    ExecutionDispatchStep,
)
from crxzipple.modules.orchestration.application.execution_chain_ids import (
    execution_chain_id,
    execution_step_correlation_key,
    execution_step_id,
)
from crxzipple.modules.orchestration.domain import (
    ExecutionChain,
    ExecutionOwnerReference,
    ExecutionStep,
    ExecutionStepKind,
    OrchestrationRun,
)


def ensure_intake_execution_chain(
    uow: ExecutionChainLifecycleUnitOfWork,
    *,
    run: OrchestrationRun,
    owner: ExecutionOwnerReference,
) -> ExecutionChainBootstrap:
    chain = uow.execution_chains.get_active_for_turn(run.id)
    if chain is None:
        chain = ExecutionChain.create(
            chain_id=execution_chain_id(run.id),
            turn_id=run.id,
        )
        step = ExecutionStep.create(
            step_id=execution_step_id(
                turn_id=run.id,
                step_index=0,
                kind=ExecutionStepKind.INTAKE,
            ),
            chain_id=chain.id,
            turn_id=run.id,
            step_index=0,
            kind=ExecutionStepKind.INTAKE,
            correlation_key=execution_step_correlation_key(
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

    intake_step = find_step(
        uow,
        turn_id=run.id,
        step_index=0,
        kind=ExecutionStepKind.INTAKE,
    )
    if intake_step is None:
        intake_step = ExecutionStep.create(
            step_id=execution_step_id(
                turn_id=run.id,
                step_index=0,
                kind=ExecutionStepKind.INTAKE,
            ),
            chain_id=chain.id,
            turn_id=run.id,
            step_index=0,
            kind=ExecutionStepKind.INTAKE,
            correlation_key=execution_step_correlation_key(
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
    if intake_step.status not in TERMINAL_STEP_STATUSES:
        intake_step.complete()
        uow.execution_steps.add(intake_step)
        uow.collect(intake_step)

    normalized_dispatch_task_id = (
        dispatch_task_id.strip()
        if dispatch_task_id is not None and dispatch_task_id.strip()
        else None
    )
    existing = (
        find_dispatch_step(uow, chain.id, normalized_dispatch_task_id)
        if normalized_dispatch_task_id is not None
        else None
    )
    next_index = next_step_index(uow, chain.id)
    existing = existing or find_step(
        uow,
        turn_id=run.id,
        step_index=next_index,
        kind=ExecutionStepKind.LLM,
    )
    if existing is not None:
        step = existing
    else:
        step = ExecutionStep.create(
            step_id=execution_step_id(
                turn_id=run.id,
                step_index=next_index,
                kind=ExecutionStepKind.LLM,
            ),
            chain_id=chain.id,
            turn_id=run.id,
            step_index=next_index,
            kind=ExecutionStepKind.LLM,
            correlation_key=execution_step_correlation_key(
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
    step = active_step_of_kind(
        uow,
        chain,
        ExecutionStepKind.LLM,
    )
    step = step or find_dispatch_step_of_kind(
        uow,
        chain.id,
        dispatch_task_id,
        ExecutionStepKind.LLM,
    )
    if step is None:
        step_index = next_step_index(uow, chain.id)
        step = ExecutionStep.create(
            step_id=execution_step_id(
                turn_id=run.id,
                step_index=step_index,
                kind=ExecutionStepKind.LLM,
            ),
            chain_id=chain.id,
            turn_id=run.id,
            step_index=step_index,
            kind=ExecutionStepKind.LLM,
            correlation_key=execution_step_correlation_key(
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
    if step.status not in TERMINAL_STEP_STATUSES:
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
