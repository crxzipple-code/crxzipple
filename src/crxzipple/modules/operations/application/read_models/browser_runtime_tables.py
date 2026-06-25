from __future__ import annotations

from crxzipple.modules.operations.application.read_models.models import (
    OperationsTableColumnModel,
    OperationsTableRowModel,
    OperationsTableSectionModel,
)


def daemon_runtimes_table(
    rows: tuple[OperationsTableRowModel, ...],
    *,
    total: int,
) -> OperationsTableSectionModel:
    return OperationsTableSectionModel(
        id="daemon_runtimes",
        title="Browser Daemon Runtimes",
        columns=(
            OperationsTableColumnModel("service_key", "Service Key"),
            OperationsTableColumnModel("runtime", "Runtime"),
            OperationsTableColumnModel("status", "Status"),
            OperationsTableColumnModel("profile", "Profile"),
            OperationsTableColumnModel("endpoint", "Endpoint"),
            OperationsTableColumnModel("pid", "PID"),
            OperationsTableColumnModel("manifest", "Manifest"),
            OperationsTableColumnModel("required", "Requires"),
            OperationsTableColumnModel("proxy_egress", "Egress"),
        ),
        rows=rows,
        total=total,
        view_all_route="/operations/browser?tab=daemon",
        empty_state="No browser daemon runtimes registered.",
    )
