from __future__ import annotations

from typing import Any

from crxzipple.modules.operations.application.read_models.daemon_common import (
    _as_dict,
    _datetime_text,
    _first_text,
    _short_optional,
    _text,
)
from crxzipple.modules.operations.application.read_models.daemon_process_helpers import (
    _process_is_managed,
    _process_is_supervisor,
    _process_status_value,
    _service_key_from_session_key,
)


def daemon_process_sessions(
    *,
    process_service: Any | None,
    instances_by_process_id: dict[str, dict[str, Any]],
) -> tuple[Any, ...]:
    get_session = getattr(process_service, "get_session", None)
    if not callable(get_session):
        return ()
    sessions = []
    for process_id in instances_by_process_id:
        try:
            session = get_session(process_id=process_id)
        except Exception:
            continue
        sessions.append(session)
    return tuple(sessions)


def daemon_process_rows(
    *,
    process_sessions: tuple[Any, ...],
    instances_by_process_id: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any], ...]:
    rows: list[dict[str, Any]] = []
    observed_process_ids: set[str] = set()
    for session in process_sessions:
        process_id = _text(getattr(session, "id", None), "")
        if not process_id:
            continue
        observed_process_ids.add(process_id)
        row = _process_session_row(
            session,
            instance=instances_by_process_id.get(process_id),
        )
        rows.append(row)
    rows.extend(
        _missing_process_rows(
            instances_by_process_id=instances_by_process_id,
            observed_process_ids=observed_process_ids,
        )
    )
    return tuple(rows)


def daemon_instances_by_process_id(
    instances: tuple[dict[str, Any], ...],
) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for instance in instances:
        metadata = _as_dict(instance.get("metadata"))
        process_id = _text(metadata.get("process_id"), "")
        if process_id:
            indexed[process_id] = instance
    return indexed


def _process_session_row(
    session: Any,
    *,
    instance: dict[str, Any] | None,
) -> dict[str, Any]:
    metadata = _as_dict(getattr(session, "metadata", None))
    session_key = _text(getattr(session, "session_key", None))
    service_key = _first_text(
        metadata.get("daemon_service_key"),
        _service_key_from_session_key(session_key),
    )
    worker_id = _text(metadata.get("daemon_worker_id"))
    instance_id = _text((instance or {}).get("id"))
    status = _process_status_value(getattr(session, "status", None))
    row = {
        "process_id": _text(getattr(session, "id", None), ""),
        "service_key": service_key,
        "session_key": session_key,
        "status": status,
        "pid": _text(getattr(session, "pid", None)),
        "exit_code": _text(getattr(session, "exit_code", None)),
        "command": _text(getattr(session, "command", None)),
        "shell": _text(getattr(session, "shell", None)),
        "working_directory": _text(getattr(session, "working_directory", None)),
        "worker_id": worker_id,
        "instance_id": instance_id,
        "created_at": _datetime_text(getattr(session, "created_at", None)),
        "started_at": _datetime_text(getattr(session, "started_at", None)),
        "updated_at": _datetime_text(getattr(session, "updated_at", None)),
        "ended_at": _datetime_text(getattr(session, "ended_at", None)),
        "termination_requested_at": _datetime_text(
            getattr(session, "termination_requested_at", None),
        ),
        "stdout_tail": _short_optional(getattr(session, "stdout", ""), 120),
        "stderr_tail": _short_optional(getattr(session, "stderr", ""), 120),
        "metadata": metadata,
    }
    row["orphaned"] = (
        _process_is_managed(row)
        and status == "running"
        and instance_id == "-"
        and not _process_is_supervisor(row)
    )
    return row


def _missing_process_rows(
    *,
    instances_by_process_id: dict[str, dict[str, Any]],
    observed_process_ids: set[str],
) -> tuple[dict[str, Any], ...]:
    rows: list[dict[str, Any]] = []
    for process_id, instance in sorted(instances_by_process_id.items()):
        if process_id in observed_process_ids:
            continue
        metadata = _as_dict(instance.get("metadata"))
        rows.append(
            {
                "process_id": process_id,
                "service_key": _text(instance.get("service_key")),
                "session_key": _text(metadata.get("session_key")),
                "status": "missing",
                "pid": _text(instance.get("pid")),
                "exit_code": "-",
                "command": _text(metadata.get("command")),
                "shell": "-",
                "working_directory": "-",
                "worker_id": _text(instance.get("worker_id")),
                "instance_id": _text(instance.get("id")),
                "created_at": "-",
                "started_at": _text(instance.get("started_at")),
                "updated_at": _first_text(
                    instance.get("last_healthcheck_at"),
                    instance.get("started_at"),
                ),
                "ended_at": "-",
                "termination_requested_at": "-",
                "stdout_tail": "",
                "stderr_tail": _first_text(
                    instance.get("last_error"),
                    "process session was not found",
                ),
                "metadata": metadata,
                "process_missing": True,
                "orphaned": False,
            }
        )
    return tuple(rows)
