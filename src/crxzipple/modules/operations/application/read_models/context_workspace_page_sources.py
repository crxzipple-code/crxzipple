from __future__ import annotations

from typing import Any

from crxzipple.modules.context_workspace.application import (
    BuildContextObservationSliceInput,
)
from crxzipple.modules.context_workspace.domain import ContextWorkspaceNotFoundError
from crxzipple.modules.operations.application.read_models.context_workspace_rows import (
    operations_slice_row,
)
from crxzipple.modules.operations.application.read_models.ports_context import (
    OperationsContextObservationSnapshotPort,
    OperationsContextSliceBuilderPort,
    OperationsContextTreePort,
    OperationsContextWorkspacePort,
)


def safe_list_workspaces(
    service: OperationsContextWorkspacePort | None,
    *,
    limit: int,
    offset: int,
) -> tuple[tuple[Any, ...], str | None]:
    if service is None:
        return (), "Context Workspace service is not available."
    try:
        return tuple(service.list_workspaces(limit=limit, offset=offset)), None
    except Exception as exc:
        return (), str(exc)


def safe_tree_views(
    service: OperationsContextTreePort | None,
    workspaces: tuple[Any, ...],
) -> tuple[tuple[Any, ...], str | None]:
    if service is None:
        return (), "Context Tree service is not available."
    views: list[Any] = []
    for workspace in workspaces:
        session_key = _text(getattr(workspace, "session_key", ""))
        if not session_key:
            continue
        try:
            views.append(service.list_tree(session_key))
        except Exception as exc:
            return tuple(views), str(exc)
    return tuple(views), None


def safe_list_snapshots(
    service: OperationsContextObservationSnapshotPort | None,
    *,
    limit: int,
    offset: int,
) -> tuple[tuple[Any, ...], str | None]:
    if service is None:
        return (), "Context observation snapshot service is not available."
    try:
        return tuple(service.list_recent_snapshots(limit=limit, offset=offset)), None
    except Exception as exc:
        return (), str(exc)


def safe_operations_slice_rows(
    builder: OperationsContextSliceBuilderPort | None,
    workspaces: tuple[Any, ...],
    snapshots: tuple[Any, ...],
    *,
    limit: int,
) -> tuple[tuple[dict[str, str], ...], str | None]:
    if builder is None:
        return (), "Context Slice Builder service is not available."
    latest_run_by_session = _latest_run_by_session(snapshots)
    rows: list[dict[str, str]] = []
    for workspace in workspaces:
        session_key = _text(getattr(workspace, "session_key", ""))
        if not session_key:
            continue
        run_id = latest_run_by_session.get(session_key, "")
        try:
            context_slice = builder.build_slice(
                data=BuildContextObservationSliceInput(
                    session_key=session_key,
                    run_id=run_id,
                    audience="operations_projection",
                    metadata={"surface": "operations"},
                ),
            )
        except ContextWorkspaceNotFoundError:
            continue
        except Exception as exc:
            return tuple(rows), str(exc)
        rows.append(operations_slice_row(context_slice, session_key=session_key))
        if len(rows) >= limit:
            break
    return tuple(rows), None


def _latest_run_by_session(snapshots: tuple[Any, ...]) -> dict[str, str]:
    result: dict[str, str] = {}
    for snapshot in snapshots:
        session_key = _text(getattr(snapshot, "session_key", ""))
        run_id = _text(getattr(snapshot, "run_id", ""))
        if session_key and run_id and session_key not in result:
            result[session_key] = run_id
    return result


def _text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value).strip()
