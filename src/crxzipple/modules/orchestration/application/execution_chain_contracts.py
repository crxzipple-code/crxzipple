from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from crxzipple.modules.orchestration.domain import (
    ExecutionChain,
    ExecutionChainRepository,
    ExecutionStep,
    ExecutionStepItemRepository,
    ExecutionStepRepository,
)
from crxzipple.shared.domain.aggregates import AggregateRoot


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
