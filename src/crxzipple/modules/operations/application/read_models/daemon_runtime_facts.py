from __future__ import annotations

from datetime import datetime
from typing import Any

from crxzipple.modules.daemon import DaemonNotFoundError, DaemonValidationError
from crxzipple.modules.operations.application.read_models.daemon_common import (
    _first_datetime,
    _seconds_since_datetime,
    _text,
)
from crxzipple.modules.operations.application.read_models.daemon_process_helpers import (
    _is_current_process_row,
)

_RECENT_DAEMON_HEALTH_SECONDS = 900.0


def safe_tuple(target: Any, method_name: str, *args: Any, **kwargs: Any) -> tuple[Any, ...]:
    method = getattr(target, method_name, None)
    if not callable(method):
        return ()
    try:
        value = method(*args, **kwargs)
    except Exception:
        return ()
    if value is None:
        return ()
    if isinstance(value, tuple):
        return value
    if isinstance(value, list):
        return tuple(value)
    if isinstance(value, set):
        return tuple(value)
    return ()


def safe_daemon_instances(daemon_manager: Any | None) -> tuple[Any, ...]:
    method = getattr(daemon_manager, "list_instances", None)
    if not callable(method):
        return ()
    try:
        value = method(refresh=False)
    except (DaemonValidationError, DaemonNotFoundError):
        return ()
    except Exception:
        return ()
    return tuple(value or ())


def current_daemon_instances(
    instances: tuple[dict[str, Any], ...],
    *,
    now: datetime,
) -> tuple[dict[str, Any], ...]:
    return tuple(instance for instance in instances if _is_current_instance(instance, now=now))


def _is_current_instance(instance: dict[str, Any], *, now: datetime) -> bool:
    del now
    status = _text(instance.get("status"), "").lower()
    return status != "stopped"


def current_daemon_process_rows(
    process_rows: tuple[dict[str, Any], ...],
    *,
    now: datetime,
) -> tuple[dict[str, Any], ...]:
    return tuple(row for row in process_rows if _is_current_process_row(row, now=now))


def current_daemon_leases(
    leases: tuple[dict[str, Any], ...],
    *,
    now: datetime,
) -> tuple[dict[str, Any], ...]:
    return tuple(lease for lease in leases if _is_current_lease(lease, now=now))


def _is_current_lease(lease: dict[str, Any], *, now: datetime) -> bool:
    status = _text(lease.get("status"), "").lower()
    if status == "active":
        return True
    updated_at = _first_datetime(
        lease.get("heartbeat_at"),
        lease.get("expires_at"),
        lease.get("acquired_at"),
    )
    return (
        updated_at is not None
        and _seconds_since_datetime(updated_at, now=now) <= _RECENT_DAEMON_HEALTH_SECONDS
    )


def group_by_key(
    records: tuple[dict[str, Any], ...],
    key: str,
) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        grouped.setdefault(_text(record.get(key), ""), []).append(record)
    return grouped


def daemon_service_groups(services: tuple[dict[str, Any], ...]) -> tuple[str, ...]:
    return tuple(sorted({_text(item.get("service_group"), "ungrouped") for item in services}))
