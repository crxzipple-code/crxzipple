from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone

from crxzipple.core.logger import get_logger
from crxzipple.modules.operations.application.observation_models import (
    OperationsObserverHeartbeat,
)
from crxzipple.modules.operations.application.observer_subscriptions import (
    OperationsObserverHeartbeatHandler,
    OperationsObserverMaintenanceHandler,
)

logger = get_logger(__name__)


class OperationsObserverRuntimeCallbacks:
    def __init__(
        self,
        *,
        runtime_name: str,
        subscription_count: Callable[[], int],
        heartbeat_handler: OperationsObserverHeartbeatHandler | None = None,
        maintenance_handler: OperationsObserverMaintenanceHandler | None = None,
    ) -> None:
        self._runtime_name = runtime_name
        self._subscription_count = subscription_count
        self._heartbeat_handler = heartbeat_handler
        self._maintenance_handler = maintenance_handler

    def record_heartbeat(
        self,
        *,
        worker_id: str,
        status: str,
        started_at: datetime | None = None,
        processed_events: int = 0,
        idle_cycles: int = 0,
        poll_interval_seconds: float | None = None,
        limit_per_subscription: int | None = None,
    ) -> None:
        if self._heartbeat_handler is None:
            return
        heartbeat = OperationsObserverHeartbeat(
            runtime_name=self._runtime_name,
            worker_id=worker_id,
            status=status,
            started_at=started_at,
            last_seen_at=datetime.now(timezone.utc),
            processed_events=max(int(processed_events), 0),
            idle_cycles=max(int(idle_cycles), 0),
            subscription_count=self._subscription_count(),
            poll_interval_seconds=poll_interval_seconds,
            limit_per_subscription=limit_per_subscription,
        )
        try:
            self._heartbeat_handler(heartbeat)
        except Exception:
            logger.exception(
                "operations observer heartbeat handler failed",
                extra={
                    "runtime_name": self._runtime_name,
                    "worker_id": worker_id,
                    "status": status,
                },
            )

    def run_maintenance(self) -> None:
        if self._maintenance_handler is None:
            return
        try:
            self._maintenance_handler()
        except Exception:
            logger.exception(
                "operations observer maintenance handler failed",
                extra={"runtime_name": self._runtime_name},
            )
