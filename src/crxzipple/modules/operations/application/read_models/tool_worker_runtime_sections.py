from __future__ import annotations

from crxzipple.modules.operations.application.read_models.models import (
    OperationsTableColumnModel,
    OperationsTableRowModel,
    OperationsTableSectionModel,
)
from crxzipple.modules.operations.application.read_models.presenters import (
    display_value,
)
from crxzipple.modules.operations.application.read_models.tool_worker_projection import (
    worker_runtime_provider_label,
    worker_runtime_registrations,
)
from crxzipple.modules.tool.domain import ToolWorkerRegistration


def tool_worker_runtimes_section(
    worker: ToolWorkerRegistration,
) -> OperationsTableSectionModel:
    registrations = worker_runtime_registrations(worker)
    rows = tuple(
        OperationsTableRowModel(
            id=f"{worker.id}:{index}:{_display(registration.get('runtime_key'))}",
            cells={
                "runtime_key": _display(registration.get("runtime_key")),
                "provider": worker_runtime_provider_label(registration),
                "concurrency_key": _display(registration.get("concurrency_key")),
                "max_concurrency": _display(registration.get("max_concurrency")),
            },
            status="registered",
            tone="info",
        )
        for index, registration in enumerate(
            sorted(
                registrations,
                key=lambda item: (
                    _display(item.get("runtime_key")),
                    _display(item.get("concurrency_key")),
                ),
            ),
        )
    )
    return OperationsTableSectionModel(
        id="worker_runtimes",
        title="Worker Runtime Registry",
        columns=_columns(
            ("runtime_key", "Runtime Key"),
            ("provider", "Provider"),
            ("concurrency_key", "Concurrency Key"),
            ("max_concurrency", "Max Concurrency"),
        ),
        rows=rows,
        total=len(registrations),
        empty_state="No runtime registrations reported by this worker.",
    )


def _columns(*items: tuple[str, str]) -> tuple[OperationsTableColumnModel, ...]:
    return tuple(
        OperationsTableColumnModel(key=column_id, label=label)
        for column_id, label in items
    )


def _display(value: object | None) -> str:
    return display_value(value)
