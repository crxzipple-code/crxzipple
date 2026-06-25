from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class WorkbenchOwnerFactSource:
    module: str
    facts: tuple[str, ...]
    read_path: str


@dataclass(slots=True)
class OwnerCallCounter:
    target: Any
    owner: str
    calls: list[str] = field(default_factory=list)

    def __getattr__(self, name: str) -> Any:
        value = getattr(self.target, name)
        if not callable(value):
            return value

        def counted(*args: object, **kwargs: object) -> object:
            self.calls.append(f"{self.owner}.{name}")
            return value(*args, **kwargs)

        return counted


def counted_owner(
    target: Any | None,
    *,
    owner: str,
) -> OwnerCallCounter | None:
    if target is None:
        return None
    return OwnerCallCounter(target=target, owner=owner)


def owner_call_count(
    *counters: OwnerCallCounter | None,
) -> int:
    return sum(len(counter.calls) for counter in counters if counter is not None)


def owner_call_sources(
    *counters: OwnerCallCounter | None,
) -> tuple[str, ...]:
    values: list[str] = []
    seen: set[str] = set()
    for counter in counters:
        if counter is None:
            continue
        for call in counter.calls:
            if call in seen:
                continue
            seen.add(call)
            values.append(call)
    return tuple(values)


def workbench_run_owner_fact_sources() -> tuple[WorkbenchOwnerFactSource, ...]:
    return (
        WorkbenchOwnerFactSource(
            module="orchestration",
            facts=(
                "runs",
                "session_runs",
                "execution_chains",
                "execution_steps",
                "execution_step_items",
                "continuation_decisions",
                "approval_requests",
            ),
            read_path="OrchestrationRunQueryPort",
        ),
        WorkbenchOwnerFactSource(
            module="tool",
            facts=("tool_runs", "tool_results", "tool_run_artifacts"),
            read_path="WorkbenchToolQueryPort",
        ),
        WorkbenchOwnerFactSource(
            module="llm",
            facts=("invocations", "response_items", "request_render_refs"),
            read_path="WorkbenchLlmQueryPort",
        ),
        WorkbenchOwnerFactSource(
            module="session",
            facts=("session_items",),
            read_path="WorkbenchSessionQueryPort",
        ),
        WorkbenchOwnerFactSource(
            module="artifacts",
            facts=("artifact_refs", "artifact_previews"),
            read_path="WorkbenchArtifactQueryPort",
        ),
        WorkbenchOwnerFactSource(
            module="agent",
            facts=("agent_profile",),
            read_path="WorkbenchAgentQueryPort",
        ),
    )


def processed_item_count(*values: object) -> int:
    total = 0
    for value in values:
        if value is None:
            continue
        if isinstance(value, dict):
            total += len(value)
            continue
        try:
            total += len(value)  # type: ignore[arg-type]
        except TypeError:
            total += 1
    return total
