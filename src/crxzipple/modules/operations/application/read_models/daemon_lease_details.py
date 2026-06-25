from __future__ import annotations

from typing import Any

from crxzipple.modules.operations.application.observation_models import OperationsObservedEvent
from crxzipple.modules.operations.application.read_models.daemon_common import (
    _status_label,
    _text,
)
from crxzipple.modules.operations.application.read_models.daemon_status_helpers import (
    _tone_for_status,
)
from crxzipple.modules.operations.application.read_models.daemon_detail_common import (
    matching_events,
    metadata_section,
)
from crxzipple.modules.operations.application.read_models.daemon_events import (
    daemon_events_table,
)
from crxzipple.modules.operations.application.read_models.daemon_models import (
    DaemonLeaseDetailModel,
)
from crxzipple.modules.operations.application.read_models.models import (
    OperationsKeyValueItemModel,
)


def daemon_lease_details(
    *,
    leases: tuple[dict[str, Any], ...],
    service_by_key: dict[str, dict[str, Any]],
    events: tuple[OperationsObservedEvent, ...],
) -> tuple[DaemonLeaseDetailModel, ...]:
    details: list[DaemonLeaseDetailModel] = []
    for lease in leases[:80]:
        lease_id = _text(lease.get("id"), "")
        service_key = _text(lease.get("service_key"), "")
        status = _status_label(lease.get("status"))
        details.append(
            DaemonLeaseDetailModel(
                lease_id=lease_id,
                title=f"{service_key} lease",
                status=status,
                tone=_tone_for_status(status),
                summary=(
                    OperationsKeyValueItemModel("Lease ID", lease_id),
                    OperationsKeyValueItemModel("Service Key", service_key),
                    OperationsKeyValueItemModel("Instance ID", _text(lease.get("instance_id"))),
                    OperationsKeyValueItemModel("Owner Kind", _text(lease.get("owner_kind"))),
                    OperationsKeyValueItemModel("Owner ID", _text(lease.get("owner_id"))),
                    OperationsKeyValueItemModel("Status", status, _tone_for_status(status)),
                    OperationsKeyValueItemModel("Acquired At", _text(lease.get("acquired_at"))),
                    OperationsKeyValueItemModel("Heartbeat At", _text(lease.get("heartbeat_at"))),
                    OperationsKeyValueItemModel("Expires At", _text(lease.get("expires_at"))),
                ),
                metadata=metadata_section(lease.get("metadata")),
                events=daemon_events_table(
                    matching_events(
                        events,
                        service_key=service_key,
                        entity_id=lease_id,
                    )
                ),
                raw_payload={
                    "lease": dict(lease),
                    "service": dict(service_by_key.get(service_key, {})),
                },
            )
        )
    return tuple(details)
