from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timezone
import logging
from typing import Any, Protocol

from crxzipple.modules.operations.application.event_contracts import (
    OPERATIONS_PROJECTION_INVALIDATED_EVENT,
)
from crxzipple.modules.operations.application.ports import OperationsEventPublishPort
from crxzipple.modules.operations.application.projection_materializer_details import (
    extract_detail_projections,
    module_detail_kinds,
    module_table_projections,
)
from crxzipple.modules.operations.application.projection_materializer_json import (
    json_ready,
)
from crxzipple.modules.operations.application.projection_materializer_pages import (
    module_page,
)
from crxzipple.modules.operations.application.projection_modules import (
    OPERATIONS_PROJECTION_MODULES,
    normalize_modules,
    projection_modules_for_observed_modules,
)
from crxzipple.modules.operations.application.read_models import (
    OperationsReadModelProvider,
)
from crxzipple.shared.domain.events import Event
from crxzipple.shared.time import format_datetime_utc

logger = logging.getLogger(__name__)

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
        return self.materialize_modules(projection_modules_for_observed_modules(modules))

    def materialize_modules(self, modules: Iterable[str]) -> int:
        materialized = 0
        for module in normalize_modules(modules):
            if module not in OPERATIONS_PROJECTION_MODULES:
                continue
            try:
                self._materialize_module(module)
            except Exception:
                logger.exception(
                    "failed to materialize operations projection",
                    extra={"operations_module": module},
                )
                continue
            materialized += 1
        return materialized

    def _materialize_module(self, module: str) -> None:
        now = datetime.now(timezone.utc)
        page_payload = json_ready(module_page(self._source_provider, module))
        overview = self._source_provider.module_overview(module)
        overview_payload = json_ready(overview) if overview is not None else {}
        detail_kinds = module_detail_kinds(module)
        detail_projections = extract_detail_projections(module, page_payload)
        table_projections, table_detail_projections = module_table_projections(
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
                extra={"operations_module": module},
            )
