from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from enum import Enum
import logging
from typing import Any, Protocol

from crxzipple.modules.operations.application.event_contracts import (
    OPERATIONS_PROJECTION_INVALIDATED_EVENT,
)
from crxzipple.modules.operations.application.ports import OperationsEventPublishPort
from crxzipple.modules.operations.application.read_models import (
    AccessOperationsQuery,
    BrowserOperationsQuery,
    ChannelsOperationsQuery,
    ContextWorkspaceOperationsQuery,
    DaemonOperationsQuery,
    EventsOperationsQuery,
    LlmOperationsQuery,
    MemoryOperationsQuery,
    OperationsReadModelProvider,
    SkillsOperationsQuery,
    ToolOperationsQuery,
)
from crxzipple.shared.domain.events import Event
from crxzipple.shared.time import coerce_utc_datetime, format_datetime_utc

logger = logging.getLogger(__name__)
_TABLE_PROJECTION_LIMIT = 200

OPERATIONS_PROJECTION_MODULES: tuple[str, ...] = (
    "orchestration",
    "tool",
    "browser",
    "llm",
    "access",
    "channels",
    "memory",
    "context_workspace",
    "skills",
    "events",
    "daemon",
)
_PROJECTION_MODULE_PRIORITY = {
    module: index for index, module in enumerate(OPERATIONS_PROJECTION_MODULES)
}

_EVENT_MODULE_TO_PROJECTION_MODULES: dict[str, tuple[str, ...]] = {
    "orchestration": ("orchestration", "context_workspace", "events"),
    "dispatch": ("orchestration", "context_workspace", "events"),
    "tool": ("tool", "events"),
    "browser": ("browser", "daemon", "events"),
    "llm": ("llm", "events"),
    "access": ("access", "events"),
    "channels": ("channels", "events"),
    "channel": ("channels", "events"),
    "memory": ("memory", "events"),
    "context_workspace": ("context_workspace", "events"),
    "context": ("context_workspace", "events"),
    "skills": ("skills", "events"),
    "skill": ("skills", "events"),
    "events": ("events",),
    "event_relay": ("events",),
    "daemon": ("daemon", "browser", "events"),
    "process": ("daemon", "browser", "events"),
}

class OperationsProjectionWritePort(Protocol):
    def record_projection(
        self,
        *,
        module: str,
        kind: str,
        payload: dict[str, Any],
        query_key: str = "default",
        updated_at: datetime | None = None,
    ) -> None: ...

    def clear(
        self,
        *,
        module: str | None = None,
        kind: str | None = None,
    ) -> int: ...


class OperationsProjectionMaterializer:
    """Materializes operations-facing read models from a sidecar observer process."""

    def __init__(
        self,
        *,
        source_provider: OperationsReadModelProvider,
        projection_store: OperationsProjectionWritePort,
        events_service: OperationsEventPublishPort | None = None,
    ) -> None:
        self._source_provider = source_provider
        self._projection_store = projection_store
        self._events_service = events_service

    def materialize_all(self) -> int:
        return self.materialize_modules(OPERATIONS_PROJECTION_MODULES)

    def materialize_observed_modules(self, modules: Iterable[str]) -> int:
        targets: set[str] = set()
        for module in modules:
            normalized = module.strip().lower()
            targets.update(_EVENT_MODULE_TO_PROJECTION_MODULES.get(normalized, ()))
        return self.materialize_modules(_order_projection_modules(targets))

    def materialize_modules(self, modules: Iterable[str]) -> int:
        materialized = 0
        for module in _normalize_modules(modules):
            if module not in OPERATIONS_PROJECTION_MODULES:
                continue
            try:
                self._materialize_module(module)
            except Exception:
                logger.exception(
                    "failed to materialize operations projection",
                    extra={"module": module},
                )
                continue
            materialized += 1
        return materialized

    def _materialize_module(self, module: str) -> None:
        now = datetime.now(timezone.utc)
        page_payload = _json_ready(_module_page(self._source_provider, module))
        overview = self._source_provider.module_overview(module)
        overview_payload = _json_ready(overview) if overview is not None else {}
        detail_kinds = _module_detail_kinds(module)
        detail_projections = _extract_detail_projections(module, page_payload)
        table_projections, table_detail_projections = _module_table_projections(
            self._source_provider,
            module,
        )
        detail_projections = (*detail_projections, *table_detail_projections)
        page_payload["projection"] = {
            "source": "operations-observer",
            "materialized_at": format_datetime_utc(now),
        }
        if overview_payload:
            overview_payload["projection"] = {
                "source": "operations-observer",
                "materialized_at": format_datetime_utc(now),
            }
        for detail_kind in detail_kinds:
            self._projection_store.clear(module=module, kind=detail_kind)
        if table_projections:
            self._projection_store.clear(module=module, kind="table")
        for projection_kind, query_key, detail_payload in detail_projections:
            self._projection_store.record_projection(
                module=module,
                kind=projection_kind,
                query_key=query_key,
                payload=detail_payload,
                updated_at=now,
            )
        for query_key, table_payload in table_projections:
            self._projection_store.record_projection(
                module=module,
                kind="table",
                query_key=query_key,
                payload=table_payload,
                updated_at=now,
            )
        self._projection_store.record_projection(
            module=module,
            kind="page",
            payload=page_payload,
            updated_at=now,
        )
        if overview_payload:
            self._projection_store.record_projection(
                module=module,
                kind="overview",
                payload=overview_payload,
                updated_at=now,
            )
        self._publish_invalidation(
            module=module,
            updated_at=now,
            kinds=(
                "page",
                "overview",
                *(("table",) if table_projections else ()),
                *detail_kinds,
            ),
        )

    def _publish_invalidation(
        self,
        *,
        module: str,
        updated_at: datetime,
        kinds: tuple[str, ...],
    ) -> None:
        if self._events_service is None:
            return
        try:
            self._events_service.publish(
                Event(
                    name=OPERATIONS_PROJECTION_INVALIDATED_EVENT,
                    payload={
                        "module": module,
                        "kinds": list(dict.fromkeys(kinds)),
                        "query_key": "default",
                        "source": "operations-observer",
                        "updated_at": format_datetime_utc(updated_at),
                    },
                    occurred_at=updated_at,
                ),
            )
        except Exception:
            logger.exception(
                "failed to publish operations projection invalidation",
                extra={"module": module},
            )


def _module_page(provider: OperationsReadModelProvider, module: str) -> Any:
    if module == "orchestration":
        return provider.orchestration_page()
    if module == "tool":
        return provider.tool_page(ToolOperationsQuery(limit=50))
    if module == "browser":
        return provider.browser_page(BrowserOperationsQuery(limit=1000))
    if module == "llm":
        return provider.llm_page(LlmOperationsQuery(limit=50))
    if module == "access":
        return provider.access_page(AccessOperationsQuery(limit=1000))
    if module == "channels":
        return provider.channels_page(ChannelsOperationsQuery(limit=1000))
    if module == "memory":
        return provider.memory_page(MemoryOperationsQuery(limit=1000))
    if module == "context_workspace":
        return provider.context_workspace_page(
            ContextWorkspaceOperationsQuery(limit=1000),
        )
    if module == "skills":
        return provider.skills_page(SkillsOperationsQuery(limit=1000))
    if module == "events":
        return provider.events_page(EventsOperationsQuery(limit=1000))
    if module == "daemon":
        return provider.daemon_page(DaemonOperationsQuery(limit=1000))
    raise KeyError(module)


def _module_table_projections(
    provider: OperationsReadModelProvider,
    module: str,
) -> tuple[
    tuple[tuple[str, dict[str, Any]], ...],
    tuple[tuple[str, str, dict[str, Any]], ...],
]:
    if module == "tool":
        return _collect_paginated_table_projection(
            page_loader=lambda offset, limit: _json_ready(
                provider.tool_page(ToolOperationsQuery(limit=limit, offset=offset)),
            ),
            table_key="tool_runs",
            detail_payload_key="tool_run_details",
            detail_id_key="run_id",
            detail_kind="tool_run_detail",
        )
    if module == "llm":
        return _collect_paginated_table_projection(
            page_loader=lambda offset, limit: _json_ready(
                provider.llm_page(LlmOperationsQuery(limit=limit, offset=offset)),
            ),
            table_key="recent_invocations",
            detail_payload_key="invocation_details",
            detail_id_key="invocation_id",
            detail_kind="llm_invocation_detail",
        )
    return (), ()


def _collect_paginated_table_projection(
    *,
    page_loader,
    table_key: str,
    detail_payload_key: str,
    detail_id_key: str,
    detail_kind: str,
) -> tuple[
    tuple[tuple[str, dict[str, Any]], ...],
    tuple[tuple[str, str, dict[str, Any]], ...],
]:
    rows: list[dict[str, Any]] = []
    total = 0
    section_payload: dict[str, Any] | None = None
    detail_by_key: dict[str, dict[str, Any]] = {}
    offset = 0
    while True:
        page_payload = page_loader(offset, _TABLE_PROJECTION_LIMIT)
        if not isinstance(page_payload, dict):
            break
        section = page_payload.get(table_key)
        if not isinstance(section, dict):
            break
        if section_payload is None:
            section_payload = dict(section)
        page_rows = [
            row
            for row in section.get("rows", ())
            if isinstance(row, dict)
        ]
        total = max(_int_value(section.get("total")), len(rows) + len(page_rows))
        rows.extend(dict(row) for row in page_rows)
        for projection_kind, query_key, detail_payload in _extract_list_detail_projections(
            page_payload=page_payload,
            payload_key=detail_payload_key,
            id_key=detail_id_key,
            detail_kind=detail_kind,
        ):
            if projection_kind == detail_kind:
                detail_by_key[query_key] = detail_payload
        offset += _TABLE_PROJECTION_LIMIT
        if len(rows) >= total or len(page_rows) < _TABLE_PROJECTION_LIMIT:
            break
    details = tuple(
        (detail_kind, key, payload)
        for key, payload in detail_by_key.items()
    )
    if section_payload is None:
        return (), details
    section_payload["rows"] = rows
    section_payload["total"] = total
    return ((table_key, section_payload),), details


def _extract_detail_projections(
    module: str,
    page_payload: dict[str, Any],
) -> tuple[tuple[str, str, dict[str, Any]], ...]:
    if module == "tool":
        return _extract_list_detail_projections(
            page_payload=page_payload,
            payload_key="tool_run_details",
            id_key="run_id",
            detail_kind="tool_run_detail",
        )
    if module == "llm":
        return _extract_list_detail_projections(
            page_payload=page_payload,
            payload_key="invocation_details",
            id_key="invocation_id",
            detail_kind="llm_invocation_detail",
        )
    if module == "memory":
        return (
            *_extract_list_detail_projections(
                page_payload=page_payload,
                payload_key="file_details",
                id_key="file_id",
                detail_kind="memory_file_detail",
            ),
            *_extract_memory_space_detail_projections(page_payload),
        )

    return ()


def _module_detail_kinds(module: str) -> tuple[str, ...]:
    if module == "tool":
        return ("tool_run_detail",)
    if module == "llm":
        return ("llm_invocation_detail",)
    if module == "memory":
        return ("memory_file_detail", "memory_space_detail")
    return ()


def _extract_memory_space_detail_projections(
    page_payload: dict[str, Any],
) -> tuple[tuple[str, str, dict[str, Any]], ...]:
    stores = page_payload.get("memory_stores")
    if not isinstance(stores, dict):
        return ()
    rows = stores.get("rows")
    if not isinstance(rows, list):
        return ()
    details: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        cells = row.get("cells")
        if not isinstance(cells, dict):
            continue
        space_id = str(cells.get("space_id") or "").strip()
        if not space_id:
            continue
        detail = details.setdefault(
            space_id,
            {
                "space_id": space_id,
                "agents": [],
                "status": row.get("status") or cells.get("status") or "unknown",
                "tone": row.get("tone") or "neutral",
                "stores": [],
            },
        )
        agent_id = str(cells.get("agent") or row.get("id") or "").strip()
        if agent_id:
            detail["agents"].append(agent_id)
        detail["stores"].append(dict(cells))
    return tuple(
        ("memory_space_detail", space_id, payload)
        for space_id, payload in sorted(details.items())
    )


def _extract_list_detail_projections(
    *,
    page_payload: dict[str, Any],
    payload_key: str,
    id_key: str,
    detail_kind: str,
) -> tuple[tuple[str, str, dict[str, Any]], ...]:
    details = page_payload.get(payload_key)
    page_payload[payload_key] = []
    if not isinstance(details, list):
        return ()
    projections: list[tuple[str, str, dict[str, Any]]] = []
    for item in details:
        if not isinstance(item, dict):
            continue
        query_key = str(item.get(id_key) or "").strip()
        if not query_key:
            continue
        projections.append((detail_kind, query_key, dict(item)))
    return tuple(projections)


def _int_value(value: Any) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return 0
    return 0


def _normalize_modules(modules: Iterable[str]) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            module.strip().lower()
            for module in modules
            if isinstance(module, str) and module.strip()
        ),
    )


def _order_projection_modules(modules: Iterable[str]) -> tuple[str, ...]:
    return tuple(
        sorted(
            _normalize_modules(modules),
            key=lambda module: _PROJECTION_MODULE_PRIORITY.get(
                module,
                len(_PROJECTION_MODULE_PRIORITY),
            ),
        ),
    )


def _json_ready(value: Any) -> Any:
    if is_dataclass(value):
        return _json_ready(asdict(value))
    if isinstance(value, datetime):
        return format_datetime_utc(coerce_utc_datetime(value))
    if isinstance(value, Enum):
        return _json_ready(value.value)
    if isinstance(value, Mapping):
        return {
            str(key): _json_ready(item)
            for key, item in value.items()
            if isinstance(key, str | int | float | bool)
        }
    if isinstance(value, tuple | list | set | frozenset):
        return [_json_ready(item) for item in value]
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    raw_value = getattr(value, "value", None)
    if isinstance(raw_value, str | int | float | bool):
        return raw_value
    return str(value)
