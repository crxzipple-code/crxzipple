from __future__ import annotations

from datetime import datetime
from typing import Protocol

from crxzipple.modules.dispatch.domain.entities import DispatchTask
from crxzipple.modules.dispatch.domain.value_objects import DispatchTaskStatus


class DispatchTaskRepository(Protocol):
    def add(self, task: DispatchTask) -> None:
        ...

    def get(self, task_id: str) -> DispatchTask | None:
        ...

    def list(
        self,
        *,
        status: DispatchTaskStatus | None = None,
        owner_kind: str | None = None,
        lane_key: str | None = None,
    ) -> list[DispatchTask]:
        ...

    def claim_next_queued(
        self,
        *,
        owner_kind: str | None = None,
        worker_id: str,
        claim_token: str,
        lease_seconds: int | None = None,
    ) -> DispatchTask | None:
        ...

    def recover_abandoned(
        self,
        *,
        owner_kind: str | None = None,
        now: datetime | None = None,
    ) -> list[DispatchTask]:
        ...
