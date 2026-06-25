from __future__ import annotations

from datetime import datetime

from crxzipple.modules.tool.domain import ToolWorkerRegistration, ToolWorkerStatus
from crxzipple.shared.time import coerce_utc_datetime


def worker_is_online(worker: ToolWorkerRegistration, *, now: datetime) -> bool:
    if worker.status is not ToolWorkerStatus.ONLINE:
        return False
    if worker.lease_expires_at is None:
        return True
    return coerce_utc_datetime(worker.lease_expires_at) > coerce_utc_datetime(now)


def online_workers(
    workers: list[ToolWorkerRegistration],
    *,
    now: datetime,
) -> list[ToolWorkerRegistration]:
    return [worker for worker in workers if worker_is_online(worker, now=now)]
