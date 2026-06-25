from __future__ import annotations

from typing import Any

from crxzipple.modules.operations.application.read_models.daemon_common import (
    _as_dict,
    _bool,
    _short,
    _status_label,
    _text,
    _yes_no,
)
from crxzipple.modules.operations.application.read_models.daemon_browser_helpers import (
    _browser_host_manifest_label,
    _is_browser_host_service,
)
from crxzipple.modules.operations.application.read_models.daemon_status_helpers import (
    _status_sort,
    _tone_for_status,
)
from crxzipple.modules.operations.application.read_models.models import (
    OperationsTableRowModel,
)


def instance_rows(
    instances: tuple[dict[str, Any], ...],
    *,
    service_by_key: dict[str, dict[str, Any]],
) -> tuple[OperationsTableRowModel, ...]:
    return tuple(
        instance_row(instance, service_by_key.get(_text(instance.get("service_key"), "")))
        for instance in sorted(
            instances,
            key=lambda item: (
                _status_sort(_text(item.get("status"), "")),
                _text(item.get("service_key"), ""),
                _text(item.get("id"), ""),
            ),
        )
    )


def instance_row(
    instance: dict[str, Any],
    service: dict[str, Any] | None,
) -> OperationsTableRowModel:
    status = _status_label(instance.get("status"))
    service_key = _text(instance.get("service_key"), "")
    return OperationsTableRowModel(
        id=_text(instance.get("id"), ""),
        cells={
            "instance_id": _text(instance.get("id")),
            "service_key": service_key,
            "display_name": _text((service or {}).get("display_name") or service_key),
            "runtime": instance_runtime_label(instance, service),
            "status": status,
            "pid": _text(instance.get("pid")),
            "worker_id": _text(instance.get("worker_id")),
            "endpoint": _text(instance.get("endpoint")),
            "started_at": _text(instance.get("started_at")),
            "last_healthcheck_at": _text(instance.get("last_healthcheck_at")),
            "env_drift": _yes_no(_bool(instance.get("env_drift_detected"))),
            "last_error": _short(instance.get("last_error"), 96),
            "action": "Open",
        },
        status=status,
        tone=_tone_for_status(status),
    )


def lease_rows(
    leases: tuple[dict[str, Any], ...],
    *,
    service_by_key: dict[str, dict[str, Any]],
) -> tuple[OperationsTableRowModel, ...]:
    rows: list[OperationsTableRowModel] = []
    for lease in sorted(
        leases,
        key=lambda item: (
            _status_sort(_text(item.get("status"), "")),
            _text(item.get("expires_at"), ""),
            _text(item.get("id"), ""),
        ),
    ):
        status = _status_label(lease.get("status"))
        service_key = _text(lease.get("service_key"), "")
        service = service_by_key.get(service_key, {})
        rows.append(
            OperationsTableRowModel(
                id=_text(lease.get("id"), ""),
                cells={
                    "lease_id": _text(lease.get("id")),
                    "service_key": service_key,
                    "display_name": _text(service.get("display_name") or service_key),
                    "instance_id": _text(lease.get("instance_id")),
                    "owner": f"{_text(lease.get('owner_kind'))}:{_text(lease.get('owner_id'))}",
                    "status": status,
                    "acquired_at": _text(lease.get("acquired_at")),
                    "heartbeat_at": _text(lease.get("heartbeat_at")),
                    "expires_at": _text(lease.get("expires_at")),
                    "action": "Open",
                },
                status=status,
                tone=_tone_for_status(status),
            )
        )
    return tuple(rows)


def instance_runtime_label(
    instance: dict[str, Any],
    service: dict[str, Any] | None,
) -> str:
    service_key = _text(instance.get("service_key"), "")
    metadata = _as_dict(instance.get("metadata"))
    if _is_browser_host_service(service_key):
        state = _browser_host_manifest_label(metadata)
        return f"Browser Host · {state}" if state != "-" else "Browser Host"
    role = _text((service or {}).get("role"), "")
    group = _text((service or {}).get("service_group"), "")
    if role != "-" and group != "-":
        return f"{_status_label(role)} · {group}"
    if role != "-":
        return _status_label(role)
    return "-"

