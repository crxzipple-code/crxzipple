from __future__ import annotations

from typing import Any

from crxzipple.modules.operations.application.read_models.daemon_common import (
    _short,
    _text,
)
from crxzipple.modules.operations.application.read_models.daemon_process_helpers import (
    _process_status_value,
)
from crxzipple.modules.operations.application.read_models.models import (
    OperationsTableColumnModel,
    OperationsTableRowModel,
    OperationsTableSectionModel,
)


def safe_process_output(process_service: Any | None, process_id: str) -> Any | None:
    method = getattr(process_service, "read_output", None)
    if not callable(method) or not process_id:
        return None
    try:
        return method(process_id=process_id, limit=1200)
    except Exception:
        return None


def process_output_payload(output: Any | None) -> dict[str, Any]:
    if output is None:
        return {}
    return {
        "status": _process_status_value(getattr(output, "status", None)),
        "exit_code": getattr(output, "exit_code", None),
        "stdout": getattr(output, "stdout", ""),
        "stderr": getattr(output, "stderr", ""),
        "stdout_offset": getattr(output, "stdout_offset", 0),
        "stderr_offset": getattr(output, "stderr_offset", 0),
        "next_stdout_offset": getattr(output, "next_stdout_offset", 0),
        "next_stderr_offset": getattr(output, "next_stderr_offset", 0),
    }


def process_output_table(
    process_row: dict[str, Any],
    output: Any | None,
) -> OperationsTableSectionModel:
    rows: list[OperationsTableRowModel] = []
    if output is not None:
        stdout = _text(getattr(output, "stdout", None), "")
        stderr = _text(getattr(output, "stderr", None), "")
        rows.extend(
            _process_output_row(
                stream="stdout",
                text=stdout,
                next_offset=_text(getattr(output, "next_stdout_offset", None)),
            ),
        )
        rows.extend(
            _process_output_row(
                stream="stderr",
                text=stderr,
                next_offset=_text(getattr(output, "next_stderr_offset", None)),
            ),
        )
    else:
        rows.extend(
            _process_output_row(
                stream="stdout",
                text=_text(process_row.get("stdout_tail"), ""),
                next_offset="-",
            ),
        )
        rows.extend(
            _process_output_row(
                stream="stderr",
                text=_text(process_row.get("stderr_tail"), ""),
                next_offset="-",
            ),
        )
    return OperationsTableSectionModel(
        id="process_output",
        title="Output",
        columns=(
            OperationsTableColumnModel("stream", "Stream"),
            OperationsTableColumnModel("bytes", "Bytes"),
            OperationsTableColumnModel("preview", "Preview"),
            OperationsTableColumnModel("next_offset", "Next Offset"),
        ),
        rows=tuple(rows),
        total=len(rows),
        empty_state="No process output observed.",
    )


def _process_output_row(
    *,
    stream: str,
    text: str,
    next_offset: str,
) -> tuple[OperationsTableRowModel, ...]:
    if not text:
        return ()
    return (
        OperationsTableRowModel(
            id=stream,
            cells={
                "stream": stream,
                "bytes": str(len(text.encode("utf-8"))),
                "preview": _short(text.replace("\n", " "), 240),
                "next_offset": next_offset,
            },
            status="observed",
            tone="danger" if stream == "stderr" else "info",
        ),
    )
