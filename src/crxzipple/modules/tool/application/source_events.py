from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from crxzipple.modules.tool.application.catalog_models import (
    ToolFunctionCatalogRecord,
    ToolSourceDiscoveryResult,
)
from crxzipple.modules.tool.domain.entities import ToolSource
from crxzipple.modules.tool.domain.value_objects import ToolSourceStatus
from crxzipple.shared.domain import Event


def source_status_event_name(status: ToolSourceStatus) -> str:
    if status is ToolSourceStatus.DISABLED:
        return "tool.source.disabled"
    if status is ToolSourceStatus.DELETED:
        return "tool.source.deleted"
    return "tool.source.restored"


def source_snapshot(source: ToolSource | None) -> dict[str, Any] | None:
    if source is None:
        return None
    return {
        "status": source.status.value,
        "revision": source.revision,
        "config_hash": source.config_hash,
        "last_discovery_status": source.last_discovery_status,
    }


def source_event(
    name: str,
    source: ToolSource,
    *,
    observed_at: datetime,
    previous: Mapping[str, Any] | None = None,
    discovery: ToolSourceDiscoveryResult | None = None,
    changed_fields: tuple[str, ...] = (),
) -> Event:
    payload: dict[str, Any] = {
        "source_id": source.source_id,
        "kind": source.kind.value,
        "display_name": source.display_name,
        "status": source.status.value,
        "revision": source.revision,
        "config_hash": source.config_hash,
    }
    if source.last_discovery_status:
        payload["discovery_status"] = source.last_discovery_status
    if previous is not None:
        payload["previous_status"] = previous.get("status")
        payload["previous_revision"] = previous.get("revision")
        payload["previous_config_hash"] = previous.get("config_hash")
        previous_discovery_status = previous.get("last_discovery_status")
        if previous_discovery_status:
            payload["previous_discovery_status"] = previous_discovery_status
    if discovery is not None:
        payload["discovery_status"] = discovery.status.value
        payload["function_count"] = len(discovery.candidates)
        payload["provider_backend_count"] = len(discovery.provider_backend_candidates)
        if discovery.error_message:
            payload["error_message"] = discovery.error_message
    if changed_fields:
        payload["changed_fields"] = changed_fields
    return Event(
        name=name,
        payload=payload,
        occurred_at=observed_at,
        ordering_key=source.source_id,
    )


def function_event(
    name: str,
    function: ToolFunctionCatalogRecord,
    *,
    observed_at: datetime,
    changed_fields: tuple[str, ...] = (),
) -> Event:
    payload: dict[str, Any] = {
        "function_id": function.function_id,
        "source_id": function.source_id,
        "stable_key": function.stable_key,
        "schema_hash": function.schema_hash,
        "status": function.status.value,
        "enabled": function.enabled,
        "revision": function.revision,
    }
    if changed_fields:
        payload["changed_fields"] = changed_fields
    return Event(
        name=name,
        payload=payload,
        occurred_at=observed_at,
        ordering_key=function.function_id,
    )


__all__ = [
    "function_event",
    "source_event",
    "source_snapshot",
    "source_status_event_name",
]
