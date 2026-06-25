from __future__ import annotations

from typing import Any

from crxzipple.modules.operations.application.read_models.daemon_common import (
    _normalized_filter,
    _search_blob,
    _text,
)
from crxzipple.modules.operations.application.read_models.daemon_models import (
    DaemonOperationsQuery,
)


def normalize_daemon_query(
    query: DaemonOperationsQuery | None,
) -> DaemonOperationsQuery:
    if query is None:
        return DaemonOperationsQuery()
    return DaemonOperationsQuery(
        status=_normalized_filter(query.status),
        service_key=_normalized_filter(query.service_key),
        service_group=_normalized_filter(query.service_group),
        search=query.search.strip() if isinstance(query.search, str) else "",
        limit=max(1, min(int(query.limit), 200)),
        offset=max(0, int(query.offset)),
    )


def filter_daemon_instances(
    instances: tuple[dict[str, Any], ...],
    query: DaemonOperationsQuery,
    *,
    service_by_key: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any], ...]:
    return _filter_records(instances, query, service_by_key=service_by_key)


def filter_daemon_leases(
    leases: tuple[dict[str, Any], ...],
    query: DaemonOperationsQuery,
    *,
    service_by_key: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any], ...]:
    return _filter_records(leases, query, service_by_key=service_by_key)


def filter_daemon_process_rows(
    process_rows: tuple[dict[str, Any], ...],
    query: DaemonOperationsQuery,
    *,
    service_by_key: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any], ...]:
    return _filter_records(process_rows, query, service_by_key=service_by_key)


def _filter_records(
    records: tuple[dict[str, Any], ...],
    query: DaemonOperationsQuery,
    *,
    service_by_key: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any], ...]:
    needle = query.search.lower()
    filtered: list[dict[str, Any]] = []
    for record in records:
        service_key = _text(record.get("service_key"), "")
        service = service_by_key.get(service_key, {})
        if query.service_key != "all" and service_key.lower() != query.service_key:
            continue
        if (
            query.service_group != "all"
            and _text(service.get("service_group"), "").lower() != query.service_group
        ):
            continue
        if query.status != "all" and _normalized_filter(record.get("status")) != query.status:
            continue
        if needle and needle not in _search_blob(record, service):
            continue
        filtered.append(record)
    return tuple(filtered)
