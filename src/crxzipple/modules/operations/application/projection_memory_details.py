from __future__ import annotations

from typing import Any


def extract_memory_space_detail_projections(
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
