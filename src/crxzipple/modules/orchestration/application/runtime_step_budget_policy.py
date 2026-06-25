from __future__ import annotations

from dataclasses import dataclass

from crxzipple.modules.orchestration.domain import OrchestrationRun


@dataclass(frozen=True, slots=True)
class RuntimeStepBudget:
    current_step: int
    max_steps: int
    remaining_steps: int
    status: str

    def to_payload(self) -> dict[str, object]:
        return {
            "current_step": self.current_step,
            "max_steps": self.max_steps,
            "remaining_steps": self.remaining_steps,
            "step_budget_status": self.status,
        }


class RuntimeStepBudgetPolicy:
    def for_run(self, run: OrchestrationRun) -> RuntimeStepBudget:
        remaining_steps = max(run.max_steps - run.current_step, 0)
        return RuntimeStepBudget(
            current_step=run.current_step,
            max_steps=run.max_steps,
            remaining_steps=remaining_steps,
            status=self.status_for_remaining_steps(remaining_steps),
        )

    @staticmethod
    def status_for_remaining_steps(remaining_steps: int) -> str:
        if remaining_steps <= 1:
            return "finalize_now"
        if remaining_steps <= 3:
            return "critical"
        if remaining_steps <= 6:
            return "constrained"
        return "available"
