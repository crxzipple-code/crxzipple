from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True, slots=True)
class SessionRuntimeRunRecord:
    id: str
    status: str
    stage: str | None = None
    current_step: int | None = None
    max_steps: int | None = None
    waiting_reason: str | None = None
    prompt_mode: str | None = None
    worker_id: str | None = None
    session_key: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)
    queued_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class SubmitSessionBoundTurnInput:
    agent_id: str
    session_key: str
    active_session_id: str
    source: str
    metadata: dict[str, object] = field(default_factory=dict)
    inbound_metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SubmitSessionSpawnTurnInput:
    agent_id: str
    child_main_key: str
    text: str
    source: str
    spawn_metadata: dict[str, object] = field(default_factory=dict)


class SessionRuntimeControlPort(Protocol):
    def submit_bound_turn(
        self,
        data: SubmitSessionBoundTurnInput,
        *,
        inline_worker_id: str | None = None,
    ) -> SessionRuntimeRunRecord:
        ...

    def submit_spawn_turn(
        self,
        data: SubmitSessionSpawnTurnInput,
        *,
        inline_worker_id: str | None = None,
    ) -> SessionRuntimeRunRecord:
        ...

    def list_runs(self) -> tuple[SessionRuntimeRunRecord, ...]:
        ...

    def cancel_session_tree(
        self,
        session_key: str,
        *,
        reason: str | None = None,
    ) -> dict[str, object]:
        ...


__all__ = [
    "SessionRuntimeControlPort",
    "SessionRuntimeRunRecord",
    "SubmitSessionBoundTurnInput",
    "SubmitSessionSpawnTurnInput",
]
