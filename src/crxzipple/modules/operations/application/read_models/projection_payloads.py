from __future__ import annotations

from copy import deepcopy
from typing import Any, Protocol

from crxzipple.modules.operations.application.observation_models import OperationsProjection
from crxzipple.modules.operations.application.projections import (
    OPERATIONS_PROJECTION_MODULES,
)
from crxzipple.modules.operations.application.read_models.projection_detail_payloads import (
    strip_deferred_detail_payloads,
)
from crxzipple.modules.operations.application.read_models.projection_table_filters import (
    apply_related_projection_filters,
    apply_table_projection_filters,
)

PROJECTED_MODULES = frozenset(OPERATIONS_PROJECTION_MODULES)


class OperationsProjectionReadPort(Protocol):
    def get_projection(
        self,
        *,
        module: str,
        kind: str,
        query_key: str = "default",
    ) -> OperationsProjection | None: ...


class OperationsProjectionUnavailableError(RuntimeError):
    """Raised when a projection exists conceptually but is not materialized."""


class OperationsProjectionNotFoundError(LookupError):
    """Raised when a requested projection module or detail does not exist."""


def list_module_overview_payloads(
    projection_store: OperationsProjectionReadPort,
) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for module in OPERATIONS_PROJECTION_MODULES:
        projection = projection_store.get_projection(module=module, kind="overview")
        if projection is None:
            continue
        payloads.append(deepcopy(projection.payload))
    if not payloads:
        raise OperationsProjectionUnavailableError(
            "Operations projections are not materialized yet. "
            "Start or run the operations-observer worker.",
        )
    return payloads


def module_overview_payload(
    projection_store: OperationsProjectionReadPort,
    module: str,
) -> dict[str, Any]:
    return module_projection_payload(projection_store, module=module, kind="overview")


def module_page_payload(
    projection_store: OperationsProjectionReadPort,
    *,
    module: str,
    table: str | None = None,
    filters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = module_projection_payload(projection_store, module=module, kind="page")
    normalized_module = module.strip().lower()
    if table is not None and filters is not None:
        _replace_table_from_projection(
            projection_store,
            payload,
            module=normalized_module,
            table=table,
        )
        apply_table_projection_filters(payload, table=table, filters=filters)
        apply_related_projection_filters(
            payload,
            module=normalized_module,
            primary_table=table,
            filters=filters,
        )
    strip_deferred_detail_payloads(payload, module=normalized_module, kind="page")
    return payload


def module_projection_payload(
    projection_store: OperationsProjectionReadPort,
    *,
    module: str,
    kind: str,
) -> dict[str, Any]:
    normalized_module = module.strip().lower()
    if normalized_module not in PROJECTED_MODULES:
        raise OperationsProjectionNotFoundError(
            f"Operations projection for module '{module}' is not available.",
        )
    projection = projection_store.get_projection(
        module=normalized_module,
        kind=kind,
    )
    if projection is None:
        raise OperationsProjectionUnavailableError(
            "Operations projection is not materialized yet. "
            "Start or run the operations-observer worker.",
        )
    payload = deepcopy(projection.payload)
    payload["projection_freshness"] = {
        "module": projection.module,
        "kind": projection.kind,
        "query_key": projection.query_key,
        "updated_at": projection.to_payload()["updated_at"],
    }
    return payload


def detail_projection_payload(
    projection_store: OperationsProjectionReadPort,
    *,
    module: str,
    kind: str,
    query_key: str,
) -> dict[str, Any]:
    projection = projection_store.get_projection(
        module=module.strip().lower(),
        kind=kind,
        query_key=query_key,
    )
    if projection is None:
        raise OperationsProjectionNotFoundError(
            f"Operations detail '{query_key}' is not available.",
        )
    return deepcopy(projection.payload)


def _replace_table_from_projection(
    projection_store: OperationsProjectionReadPort,
    payload: dict[str, Any],
    *,
    module: str,
    table: str,
) -> None:
    projection = projection_store.get_projection(
        module=module.strip().lower(),
        kind="table",
        query_key=table,
    )
    if projection is None:
        return
    table_payload = deepcopy(projection.payload)
    if isinstance(table_payload, dict):
        payload[table] = table_payload

