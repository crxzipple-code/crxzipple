from __future__ import annotations

from collections.abc import Callable
from typing import Any

from crxzipple.modules.orchestration.application.coordinators import (
    RunIngressCoordinator,
)


class OrchestrationIngressSubmissionService:
    """Append orchestration ingress requests without owning scheduler processing."""

    def __init__(self, *, uow_factory: Callable[[], Any]) -> None:
        self._ingress = RunIngressCoordinator(uow_factory=uow_factory)

    def submit_turn(
        self,
        data,
        *,
        inline_worker_id: str | None = None,
    ):
        if inline_worker_id is not None:
            raise RuntimeError(
                "inline orchestration submission requires the scheduler runtime target.",
            )
        return self._ingress.submit_turn(data)

    def submit_bound_turn(
        self,
        data,
        *,
        inline_worker_id: str | None = None,
    ):
        if inline_worker_id is not None:
            raise RuntimeError(
                "inline orchestration submission requires the scheduler runtime target.",
            )
        return self._ingress.submit_bound_turn(data)


__all__ = ["OrchestrationIngressSubmissionService"]
