from __future__ import annotations

from datetime import datetime
from typing import Any

from crxzipple.modules.operations.application.read_models.daemon_common import (
    _as_dict,
    _bool,
    _first_datetime,
    _seconds_since_datetime,
    _text,
)
from crxzipple.modules.operations.application.read_models.daemon_status_helpers import (
    _tone_for_status,
)

_RECENT_PROCESS_HEALTH_SECONDS = 300.0


def _is_current_process_row(row: dict[str, Any], *, now: datetime) -> bool:
    status = _text(row.get("status"), "").lower()
    if status == "running":
        return True
    if status == "missing":
        updated_at = _first_datetime(row.get("updated_at"), row.get("started_at"))
        return (
            updated_at is not None
            and _seconds_since_datetime(updated_at, now=now)
            <= _RECENT_PROCESS_HEALTH_SECONDS
        )
    ended_at = _first_datetime(row.get("ended_at"))
    if ended_at is None:
        return status in {"starting", "stopping", "queued"}
    return _seconds_since_datetime(ended_at, now=now) <= _RECENT_PROCESS_HEALTH_SECONDS


def _process_tone(process: dict[str, Any]) -> str:
    if _bool(process.get("process_missing")):
        return "danger"
    if _bool(process.get("orphaned")):
        return "warning"
    return _tone_for_status(process.get("status"))


def _process_binding_label(process: dict[str, Any]) -> str:
    if _bool(process.get("process_missing")):
        return "Missing Session"
    if _bool(process.get("orphaned")):
        return "Unbound"
    return "Bound"


def _process_binding_tone(process: dict[str, Any]) -> str:
    if _bool(process.get("process_missing")):
        return "danger"
    if _bool(process.get("orphaned")):
        return "warning"
    return "success"


def _process_is_managed(process: dict[str, Any]) -> bool:
    service_key = _text(process.get("service_key"), "")
    session_key = _text(process.get("session_key"), "")
    if _process_is_supervisor(process):
        return False
    return service_key not in {"", "-"} or session_key.startswith("daemon:")


def _process_is_supervisor(process: dict[str, Any]) -> bool:
    service_key = _text(process.get("service_key"), "")
    session_key = _text(process.get("session_key"), "")
    return service_key == "supervisor" or session_key == "daemon:supervisor"


def _process_output_marker(process: dict[str, Any]) -> str:
    markers: list[str] = []
    if _text(process.get("stdout_tail"), ""):
        markers.append("stdout")
    if _text(process.get("stderr_tail"), ""):
        markers.append("stderr")
    metadata = _as_dict(process.get("metadata"))
    if not markers and (
        _text(metadata.get("stdout_path"), "")
        or _text(metadata.get("stderr_path"), "")
    ):
        markers.append("logs")
    return ", ".join(markers) if markers else "-"


def _service_key_from_session_key(session_key: str) -> str:
    prefix = "daemon:"
    if session_key.startswith(prefix):
        return session_key.removeprefix(prefix)
    return "-"


def _process_status_value(value: Any) -> str:
    raw = getattr(value, "value", value)
    return _text(raw, "unknown").lower()
