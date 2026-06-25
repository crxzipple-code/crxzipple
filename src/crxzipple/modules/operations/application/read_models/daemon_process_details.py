from __future__ import annotations

from typing import Any

from crxzipple.modules.operations.application.read_models.daemon_common import (
    _first_text,
    _short,
    _status_label,
    _text,
)
from crxzipple.modules.operations.application.read_models.daemon_process_helpers import (
    _process_binding_label,
    _process_binding_tone,
    _process_tone,
)
from crxzipple.modules.operations.application.read_models.daemon_detail_common import (
    metadata_section,
)
from crxzipple.modules.operations.application.read_models.daemon_models import (
    DaemonProcessDetailModel,
)
from crxzipple.modules.operations.application.read_models.daemon_process_output_details import (
    process_output_payload,
    process_output_table,
    safe_process_output,
)
from crxzipple.modules.operations.application.read_models.models import (
    OperationsKeyValueItemModel,
)


def daemon_process_details(
    *,
    process_rows: tuple[dict[str, Any], ...],
    process_service: Any | None,
) -> tuple[DaemonProcessDetailModel, ...]:
    details: list[DaemonProcessDetailModel] = []
    for item in process_rows[:80]:
        process_id = _text(item.get("process_id"), "")
        output = safe_process_output(process_service, process_id)
        status = _status_label(item.get("status"))
        details.append(
            DaemonProcessDetailModel(
                process_id=process_id,
                title=_first_text(item.get("service_key"), item.get("session_key"), process_id),
                status=status,
                tone=_process_tone(item),
                summary=(
                    OperationsKeyValueItemModel("Process ID", process_id),
                    OperationsKeyValueItemModel("Service Key", _text(item.get("service_key"))),
                    OperationsKeyValueItemModel("Session Key", _text(item.get("session_key"))),
                    OperationsKeyValueItemModel("Status", status, _process_tone(item)),
                    OperationsKeyValueItemModel("PID", _text(item.get("pid"))),
                    OperationsKeyValueItemModel("Exit Code", _text(item.get("exit_code"))),
                    OperationsKeyValueItemModel("Instance ID", _text(item.get("instance_id"))),
                    OperationsKeyValueItemModel(
                        "Binding",
                        _process_binding_label(item),
                        _process_binding_tone(item),
                    ),
                    OperationsKeyValueItemModel("Started At", _text(item.get("started_at"))),
                    OperationsKeyValueItemModel("Updated At", _text(item.get("updated_at"))),
                    OperationsKeyValueItemModel("Ended At", _text(item.get("ended_at"))),
                    OperationsKeyValueItemModel("Command", _short(item.get("command"), 180)),
                    OperationsKeyValueItemModel(
                        "Working Directory",
                        _text(item.get("working_directory")),
                    ),
                ),
                metadata=metadata_section(item.get("metadata")),
                output=process_output_table(item, output),
                raw_payload={
                    "process": dict(item),
                    "output": process_output_payload(output),
                },
            )
        )
    return tuple(details)
