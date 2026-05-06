from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from enum import Enum
import logging
from typing import Any, Protocol

from crxzipple.modules.events import EventsApplicationService
from crxzipple.modules.operations.application.read_models import (
    AccessOperationsQuery,
    ChannelsOperationsQuery,
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

OPERATIONS_PROJECTION_MODULES: tuple[str, ...] = (
    "orchestration",
    "tool",
    "llm",
    "access",
    "channels",
    "memory",
    "skills",
    "events",
    "daemon",
)

_EVENT_MODULE_TO_PROJECTION_MODULES: dict[str, tuple[str, ...]] = {
    "orchestration": ("orchestration", "events"),
    "dispatch": ("orchestration", "events"),
    "tool": ("tool", "events"),
    "llm": ("llm", "events"),
    "access": ("access", "events"),
    "channels": ("channels", "events"),
    "channel": ("channels", "events"),
    "memory": ("memory", "events"),
    "skills": ("skills", "events"),
    "skill": ("skills", "events"),
    "events": ("events",),
    "event_relay": ("events",),
    "daemon": ("daemon", "events"),
    "process": ("daemon", "events"),
}

OPERATIONS_PROJECTION_INVALIDATED_EVENT = "operations.projection.invalidated"


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
        events_service: EventsApplicationService | None = None,
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
        return self.materialize_modules(sorted(targets))

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
        detail_kind = _module_detail_kind(module)
        detail_projections = _extract_detail_projections(module, page_payload)
        page_payload["projection"] = {
            "source": "operations-observer",
            "materialized_at": format_datetime_utc(now),
        }
        if overview_payload:
            overview_payload["projection"] = {
                "source": "operations-observer",
                "materialized_at": format_datetime_utc(now),
            }
        if detail_kind is not None:
            self._projection_store.clear(module=module, kind=detail_kind)
        for projection_kind, query_key, detail_payload in detail_projections:
            self._projection_store.record_projection(
                module=module,
                kind=projection_kind,
                query_key=query_key,
                payload=detail_payload,
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
        self._publish_invalidation(module=module, updated_at=now)

    def _publish_invalidation(self, *, module: str, updated_at: datetime) -> None:
        if self._events_service is None:
            return
        try:
            self._events_service.publish(
                Event(
                    name=OPERATIONS_PROJECTION_INVALIDATED_EVENT,
                    payload={
                        "module": module,
                        "kinds": ["page", "overview"],
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
        return provider.tool_page(ToolOperationsQuery(limit=1000))
    if module == "llm":
        return provider.llm_page(LlmOperationsQuery(limit=1000))
    if module == "access":
        return provider.access_page(AccessOperationsQuery(limit=1000))
    if module == "channels":
        return provider.channels_page(ChannelsOperationsQuery(limit=1000))
    if module == "memory":
        return provider.memory_page(MemoryOperationsQuery(limit=1000))
    if module == "skills":
        return provider.skills_page(SkillsOperationsQuery(limit=1000))
    if module == "events":
        return provider.events_page(EventsOperationsQuery(limit=1000))
    if module == "daemon":
        return provider.daemon_page(DaemonOperationsQuery(limit=1000))
    raise KeyError(module)


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
    return ()


def _module_detail_kind(module: str) -> str | None:
    if module == "tool":
        return "tool_run_detail"
    if module == "llm":
        return "llm_invocation_detail"
    return None


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


def _normalize_modules(modules: Iterable[str]) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            module.strip().lower()
            for module in modules
            if isinstance(module, str) and module.strip()
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
