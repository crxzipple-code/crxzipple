from __future__ import annotations

from collections import Counter
from typing import Any

from crxzipple.modules.operations.application.read_models.events_observer_common import (
    columns,
    display,
    join,
)
from crxzipple.modules.operations.application.read_models.models import (
    OperationsTableRowModel,
    OperationsTableSectionModel,
)


def observer_coverage_table(
    observer_definitions: tuple[Any, ...],
    events: list[dict[str, Any]],
) -> OperationsTableSectionModel:
    event_counts = Counter(display(item.get("event_name")) for item in events)
    rows = []
    for definition in observer_definitions:
        source_names = tuple(getattr(definition, "source_event_names", ()) or ())
        observed = sum(event_counts[name] for name in source_names)
        rows.append(
            OperationsTableRowModel(
                id=display(getattr(definition, "observer_id", None)),
                cells={
                    "observer": display(getattr(definition, "observer_id", None)),
                    "owner": display(getattr(definition, "owner", None)),
                    "source_events": join(source_names),
                    "output_definitions": join(
                        getattr(definition, "output_definition_ids", ()) or ()
                    ),
                    "observed_inputs": str(observed),
                    "status": "Registered",
                },
                status="registered",
                tone="success",
            )
        )
    return OperationsTableSectionModel(
        id="observer_coverage",
        title="Observer Coverage",
        columns=columns(
            ("observer", "Observer"),
            ("owner", "Owner"),
            ("source_events", "Source Events"),
            ("output_definitions", "Output Definitions"),
            ("observed_inputs", "Observed Inputs"),
            ("status", "Status"),
        ),
        rows=tuple(rows),
        total=len(rows),
        view_all_route="/operations/events?tab=observer_coverage",
        empty_state="No observer coverage definitions registered.",
    )
