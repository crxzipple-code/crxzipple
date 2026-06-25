from __future__ import annotations

from typing import Protocol

from crxzipple.modules.dispatch.domain import DispatchTask, DispatchTaskStatus
from crxzipple.modules.orchestration.application.coordinators.continuation_tasks import (
    OrchestrationContinuationStatus,
    OrchestrationContinuationTask,
)
from crxzipple.modules.orchestration.domain import OrchestrationIngressRequest
from crxzipple.modules.orchestration.domain.value_objects import OrchestrationIngressStatus


class OrchestrationIngressRequestQueryPort(Protocol):
    def list_ingress_requests(
        self,
        *,
        status: OrchestrationIngressStatus | None = None,
    ) -> list[OrchestrationIngressRequest]: ...


class OrchestrationContinuationQueryPort(Protocol):
    def list_continuation_tasks(
        self,
        *,
        status: OrchestrationContinuationStatus | None = None,
    ) -> list[OrchestrationContinuationTask]: ...


class OrchestrationDispatchTaskQueryPort(Protocol):
    def list_dispatch_tasks(
        self,
        *,
        status: DispatchTaskStatus | None = None,
        owner_kind: str | None = None,
        lane_key: str | None = None,
    ) -> list[DispatchTask]: ...
