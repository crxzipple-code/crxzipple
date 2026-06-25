from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

from crxzipple.modules.access.interfaces.inventory import collect_access_inventory
from crxzipple.modules.operations.application.read_models.access_target_projection import (
    search_blob,
    target_label,
    target_metadata,
    target_worst_status,
)
from crxzipple.modules.operations.application.read_models.access_values import (
    bool_value,
    dict_value,
    normalized_filter,
    string_values,
    text,
)
from crxzipple.modules.operations.application.read_models.access_models import (
    AccessOperationsQuery,
)


def collect_inventory(
    provider: Any,
    *,
    query: AccessOperationsQuery,
) -> dict[str, Any]:
    if provider.access_service is None:
        return {
            "ready": False,
            "targets": [],
            "counts": {"total": 0, "ready": 0, "blocked": 0},
        }
    container = AccessInventoryContainer(
        access_service=provider.access_service,
        settings_query_service=provider.settings_query_service,
        settings=SimpleNamespace(environment=provider.settings_environment),
    )
    try:
        return dict(
            collect_access_inventory(
                container,
                include_ready=query.include_ready,
                include_disabled=query.include_disabled,
            )
        )
    except Exception:
        return {
            "ready": False,
            "targets": [],
            "counts": {"total": 0, "ready": 0, "blocked": 0},
        }


@dataclass(slots=True)
class AccessInventoryContainer:
    access_service: Any
    settings_query_service: Any | None
    settings: Any

    def require(self, key: str) -> Any:
        values = {
            "access.service": self.access_service,
            "settings.query_service": self.settings_query_service,
            "core.settings": self.settings,
        }
        return values[key]


def filter_targets(
    targets: tuple[dict[str, Any], ...],
    query: AccessOperationsQuery,
) -> tuple[dict[str, Any], ...]:
    needle = query.search.lower()
    filtered: list[dict[str, Any]] = []
    for target in targets:
        status = target_worst_status(target)
        metadata = target_metadata(target)
        if query.status != "all":
            if query.status == "blocked" and bool_value(target.get("ready")):
                continue
            if query.status == "ready" and not bool_value(target.get("ready")):
                continue
            if query.status not in {"blocked", "ready"} and normalized_filter(status) != query.status:
                continue
        if query.kind != "all" and normalized_filter(metadata.get("asset_kind")) != query.kind:
            continue
        usage_types = {
            normalized_filter(item)
            for item in string_values(metadata.get("usage_types"))
        }
        if query.usage_type != "all" and query.usage_type not in usage_types:
            continue
        if needle and needle not in search_blob(target):
            continue
        filtered.append(target)
    filtered.sort(
        key=lambda item: (
            bool_value(item.get("ready")),
            target_label(item).lower(),
            text(item.get("resource_id"), ""),
        )
    )
    return tuple(filtered)


def target_dicts(inventory: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    targets = inventory.get("targets")
    if isinstance(targets, tuple):
        return tuple(dict_value(item) for item in targets)
    if isinstance(targets, list):
        return tuple(dict_value(item) for item in targets)
    return ()
