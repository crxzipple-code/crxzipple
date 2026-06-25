from __future__ import annotations

from datetime import datetime
from typing import Any

from crxzipple.modules.operations.application.read_models.daemon_common import (
    _short,
    _status_label,
    _text,
)
from crxzipple.modules.operations.application.read_models.daemon_process_helpers import (
    _is_current_process_row,
    _process_binding_label,
    _process_output_marker,
    _process_tone,
)
from crxzipple.modules.operations.application.read_models.daemon_status_helpers import (
    _status_sort,
)
from crxzipple.modules.operations.application.read_models.models import (
    OperationsTableColumnModel,
    OperationsTableRowModel,
    OperationsTableSectionModel,
)


def daemon_processes_table(
    process_rows: tuple[dict[str, Any], ...],
    *,
    total: int,
    now: datetime,
) -> OperationsTableSectionModel:
    rows: list[OperationsTableRowModel] = []
    for item in sorted(
        process_rows,
        key=lambda row: (
            not _is_current_process_row(row, now=now),
            _status_sort(_text(row.get("status"), "")),
            _text(row.get("service_key"), ""),
            _text(row.get("updated_at"), ""),
            _text(row.get("process_id"), ""),
        ),
    ):
        status = _status_label(item.get("status"))
        rows.append(
            OperationsTableRowModel(
                id=_text(item.get("process_id"), ""),
                cells={
                    "process_id": _text(item.get("process_id")),
                    "service_key": _text(item.get("service_key")),
                    "session_key": _text(item.get("session_key")),
                    "status": status,
                    "pid": _text(item.get("pid")),
                    "exit_code": _text(item.get("exit_code")),
                    "instance_id": _text(item.get("instance_id")),
                    "binding": _process_binding_label(item),
                    "updated_at": _text(item.get("updated_at")),
                    "output": _process_output_marker(item),
                    "command": _short(item.get("command"), 120),
                    "worker_id": _text(item.get("worker_id")),
                    "started_at": _text(item.get("started_at")),
                    "ended_at": _text(item.get("ended_at")),
                    "working_directory": _text(item.get("working_directory")),
                },
                status=_text(item.get("status"), ""),
                tone=_process_tone(item),
            ),
        )
    return OperationsTableSectionModel(
        id="processes",
        title="Process Sessions",
        columns=(
            OperationsTableColumnModel("process_id", "Process ID"),
            OperationsTableColumnModel("service_key", "Service Key"),
            OperationsTableColumnModel("status", "Status"),
            OperationsTableColumnModel("pid", "PID"),
            OperationsTableColumnModel("exit_code", "Exit Code"),
            OperationsTableColumnModel("instance_id", "Instance ID"),
            OperationsTableColumnModel("binding", "Binding"),
            OperationsTableColumnModel("updated_at", "Updated At"),
            OperationsTableColumnModel("output", "Output"),
        ),
        rows=tuple(rows),
        total=total,
        empty_state="No process sessions observed.",
    )
