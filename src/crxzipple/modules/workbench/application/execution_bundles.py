from __future__ import annotations

from dataclasses import dataclass

from crxzipple.modules.orchestration.application.ports import OrchestrationRunQueryPort
from crxzipple.modules.orchestration.domain import ExecutionStep, ExecutionStepItem


@dataclass(frozen=True, slots=True)
class ExecutionStepBundle:
    step: ExecutionStep
    items: tuple[ExecutionStepItem, ...]


def execution_step_bundles(
    run_query: OrchestrationRunQueryPort,
    turn_id: str,
) -> tuple[ExecutionStepBundle, ...]:
    try:
        chains = run_query.list_execution_chains(turn_id)
    except Exception:
        return ()
    bundles: list[ExecutionStepBundle] = []
    for chain in chains:
        try:
            steps = run_query.list_execution_steps(chain.id)
        except Exception:
            continue
        for step in steps:
            try:
                items = tuple(run_query.list_execution_step_items(step.id))
            except Exception:
                items = ()
            bundles.append(ExecutionStepBundle(step=step, items=items))
    return tuple(
        sorted(
            bundles,
            key=lambda bundle: (
                bundle.step.created_at,
                bundle.step.chain_id,
                bundle.step.step_index,
                bundle.step.id,
            ),
        ),
    )
