from __future__ import annotations

from typing import Any

from crxzipple.modules.operations.application.read_models.channels_formatting import (
    display_text,
    join,
    text,
)
from crxzipple.modules.operations.application.read_models.channels_safe_access import (
    safe_tuple,
)


def contract_rows(
    *,
    event_contract_registry: Any | None,
    event_definition_registry: Any | None,
) -> tuple[dict[str, Any], ...]:
    rows: list[dict[str, Any]] = []
    for contract in safe_tuple(event_contract_registry, "list_topic_contracts"):
        if text(getattr(contract, "owner", None), "").lower() != "channels":
            continue
        rows.append(
            {
                "id": display_text(getattr(contract, "contract_id", None), ""),
                "type": "Topic Contract",
                "name": display_text(getattr(contract, "contract_id", None)),
                "pattern": display_text(getattr(contract, "topic_pattern", None)),
                "kind": join(getattr(contract, "kinds", ()) or ()),
                "status": "Registered",
                "tone": "success",
            }
        )
    for contract in safe_tuple(event_contract_registry, "list_route_contracts"):
        if text(getattr(contract, "owner", None), "").lower() != "channels":
            continue
        rows.append(
            {
                "id": display_text(getattr(contract, "contract_id", None), ""),
                "type": "Route Contract",
                "name": display_text(getattr(contract, "contract_id", None)),
                "pattern": display_text(getattr(contract, "source_topic_pattern", None)),
                "kind": text(getattr(contract, "target_kind", None)),
                "status": "Registered",
                "tone": "success",
            }
        )
    for definition in safe_tuple(event_definition_registry, "list_definitions"):
        if text(getattr(definition, "owner", None), "").lower() != "channels":
            continue
        rows.append(
            {
                "id": display_text(getattr(definition, "definition_id", None), ""),
                "type": "Definition",
                "name": display_text(getattr(definition, "event_name", None)),
                "pattern": join(
                    display_text(topic)
                    for topic in getattr(definition, "topics", ()) or ()
                ),
                "kind": text(getattr(definition, "publication_mode", None)),
                "status": "Registered",
                "tone": "success",
            }
        )
    for surface in safe_tuple(event_definition_registry, "list_surfaces"):
        if text(getattr(surface, "owner", None), "").lower() != "channels":
            continue
        rows.append(
            {
                "id": display_text(getattr(surface, "surface_id", None), ""),
                "type": "Surface",
                "name": display_text(getattr(surface, "surface_id", None)),
                "pattern": join(
                    display_text(topic)
                    for topic in getattr(surface, "topics", ()) or ()
                ),
                "kind": "surface",
                "status": "Registered",
                "tone": "success",
            }
        )
    return tuple(rows)
