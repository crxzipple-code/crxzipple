from __future__ import annotations

from collections import Counter
from typing import Any

from crxzipple.modules.operations.application.read_models.models import (
    OperationsTableRowModel,
)
from crxzipple.modules.operations.application.read_models.presenters import (
    title_label,
)
from crxzipple.modules.operations.application.read_models.tool_source_catalog_labels import (
    source_health_tone,
)
from crxzipple.modules.operations.application.read_models.tool_source_common import (
    record_text,
    record_value,
)


def cli_process_health_rows(
    sources: tuple[Any, ...],
    *,
    functions: tuple[Any, ...],
) -> tuple[OperationsTableRowModel, ...]:
    cli_source_ids = {
        record_text(source, "source_id")
        for source in sources
        if record_value(source, "kind") == "cli"
    }
    cli_source_ids.update(
        record_text(function, "source_id")
        for function in functions
        if record_value(function, "runtime_kind") == "cli"
    )
    source_by_id = {record_text(source, "source_id"): source for source in sources}
    function_counts = Counter(
        record_text(function, "source_id")
        for function in functions
        if record_text(function, "source_id") in cli_source_ids
    )
    return tuple(
        OperationsTableRowModel(
            id=source_id,
            cells={
                "source": source_id,
                "status": title_label(
                    record_value(source_by_id.get(source_id), "status") or "unknown",
                ),
                "functions": str(function_counts[source_id]),
                "policy": "Guided CLI",
            },
            status=record_value(source_by_id.get(source_id), "status") or "unknown",
            tone=source_health_tone(
                record_value(source_by_id.get(source_id), "status") or "unknown",
                record_value(source_by_id.get(source_id), "last_discovery_status"),
            ),
        )
        for source_id in sorted(cli_source_ids)
        if source_id
    )
