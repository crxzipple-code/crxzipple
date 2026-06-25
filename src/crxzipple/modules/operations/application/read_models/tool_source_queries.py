from __future__ import annotations

from typing import Any

from crxzipple.modules.operations.application.read_models.ports_tooling import (
    OperationsToolQueryPort,
)
from crxzipple.modules.operations.application.read_models.presenters import (
    display_value,
)
from crxzipple.modules.operations.application.read_models.tool_source_common import (
    record_text,
)


def safe_tool_sources(tool_service: OperationsToolQueryPort) -> tuple[Any, ...]:
    list_sources = getattr(tool_service, "list_sources", None)
    if not callable(list_sources):
        return ()
    try:
        return tuple(list_sources() or ())
    except Exception:
        return ()


def safe_tool_functions(tool_service: OperationsToolQueryPort) -> tuple[Any, ...]:
    list_functions = getattr(tool_service, "list_functions", None)
    if not callable(list_functions):
        return ()
    try:
        return tuple(list_functions() or ())
    except Exception:
        return ()


def safe_tool_provider_backends(
    tool_service: OperationsToolQueryPort,
) -> tuple[Any, ...]:
    list_provider_backends = getattr(tool_service, "list_provider_backends", None)
    if not callable(list_provider_backends):
        return ()
    try:
        return tuple(list_provider_backends() or ())
    except Exception:
        return ()


def safe_tool_provider_backend_readiness(
    tool_service: OperationsToolQueryPort,
    provider_backends: tuple[Any, ...],
) -> dict[str, dict[str, Any]]:
    check_readiness = getattr(tool_service, "check_provider_backend_readiness", None)
    if not callable(check_readiness):
        return {}
    readiness_by_backend_id: dict[str, dict[str, Any]] = {}
    for backend in provider_backends:
        backend_id = record_text(backend, "backend_id")
        if not backend_id:
            continue
        try:
            readiness = check_readiness(backend)
        except Exception:
            continue
        payload = _readiness_payload(readiness)
        if payload:
            readiness_by_backend_id[backend_id] = payload
    return readiness_by_backend_id


def safe_discovery_runs_by_source(
    tool_service: OperationsToolQueryPort,
    sources: tuple[Any, ...],
    *,
    limit: int,
) -> dict[str, tuple[Any, ...]]:
    list_runs = getattr(tool_service, "list_source_discovery_runs", None)
    if not callable(list_runs):
        return {}
    result: dict[str, tuple[Any, ...]] = {}
    for source in sources:
        source_id = record_text(source, "source_id")
        if not source_id:
            continue
        try:
            result[source_id] = tuple(list_runs(source_id, limit=limit) or ())
        except Exception:
            result[source_id] = ()
    return result


def _readiness_payload(readiness: Any) -> dict[str, Any]:
    if hasattr(readiness, "to_payload"):
        payload = readiness.to_payload()
        if isinstance(payload, dict):
            return dict(payload)
    return {
        "requirement": display_value(getattr(readiness, "requirement", None)),
        "ready": bool(getattr(readiness, "ready", False)),
        "setup_available": bool(getattr(readiness, "setup_available", False)),
        "status": display_value(getattr(getattr(readiness, "status", None), "value", None)),
        "reason": display_value(getattr(readiness, "reason", None)),
    }
