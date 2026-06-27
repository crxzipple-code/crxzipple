from __future__ import annotations

from crxzipple.modules.tool.application.service_support import (
    ExecuteToolInput,
    PreparedToolRunRequest,
    ToolExecutionTarget,
    build_tool_from_function,
)
from crxzipple.modules.tool.application.provider_backend_service import (
    ToolProviderBackendResolver,
)
from crxzipple.modules.tool.domain.exceptions import (
    ToolExecutionNotAllowedError,
    ToolExecutionNotSupportedError,
    ToolNotFoundError,
)
from crxzipple.modules.tool.domain.value_objects import (
    ToolFunctionStatus,
    ToolSourceStatus,
)


def prepare_run_request(
    data: ExecuteToolInput,
    *,
    uow_factory,
    provider_backend_resolver: ToolProviderBackendResolver,
    access_readiness: object | None,
    runtime_readiness: object | None,
) -> PreparedToolRunRequest:
    target = ToolExecutionTarget(
        mode=data.mode,
        strategy=data.strategy,
        environment=data.environment,
    )
    source_revision = None
    with uow_factory() as uow:
        function = uow.tool_functions.get(data.tool_id)
        if function is None:
            raise ToolNotFoundError(f"Tool '{data.tool_id}' was not found.")
        ensure_function_executable(uow, function, tool_id=data.tool_id)
        source = uow.tool_sources.get(function.source_id)
        source_revision = source.revision if source is not None else None
        provider_backend = provider_backend_resolver.resolve_for_function(
            function=function,
            repository=uow.tool_provider_backends,
        )
        provider_backend_payload = (
            provider_backend.to_payload()
            if provider_backend is not None
            else None
        )
        tool = build_tool_from_function(function)
    if not tool.enabled:
        raise ToolExecutionNotAllowedError(
            f"Tool '{tool.id}' is disabled and cannot be executed.",
            code="tool_disabled",
            detail={
                "tool_id": getattr(tool, "id", data.tool_id),
                "category": "catalog",
                "enabled": False,
            },
        )
    if not tool.supports(target):
        raise ToolExecutionNotSupportedError(
            f"Tool '{tool.id}' does not support {target.mode.value}/{target.strategy.value}/{target.environment.value}.",
        )
    ensure_tool_access_ready(access_readiness, tool, data=data)
    ensure_tool_runtime_ready(runtime_readiness, tool, data=data)
    return PreparedToolRunRequest(
        data=data,
        target=target,
        tool=tool,
        function=function,
        source_revision=source_revision,
        provider_backend_payload=provider_backend_payload,
    )


def ensure_function_executable(
    uow,
    function,
    *,
    tool_id: str,
) -> None:
    source = uow.tool_sources.get(function.source_id)
    if source is None:
        raise ToolExecutionNotAllowedError(
            f"Tool '{tool_id}' source '{function.source_id}' is not available.",
            code="tool_source_not_available",
            detail={
                "tool_id": tool_id,
                "function_id": function.function_id,
                "source_id": function.source_id,
                "category": "catalog",
            },
        )
    if source.status is not ToolSourceStatus.ACTIVE:
        raise ToolExecutionNotAllowedError(
            f"Tool '{tool_id}' source '{source.source_id}' is {source.status.value}.",
            code="tool_source_not_executable",
            detail={
                "tool_id": tool_id,
                "function_id": function.function_id,
                "source_id": source.source_id,
                "category": "catalog",
                "source_status": source.status.value,
            },
        )
    if function.status is not ToolFunctionStatus.ACTIVE:
        raise ToolExecutionNotAllowedError(
            f"Tool '{tool_id}' catalog function is {function.status.value}.",
            code="tool_function_not_executable",
            detail={
                "tool_id": tool_id,
                "function_id": function.function_id,
                "source_id": function.source_id,
                "category": "catalog",
                "function_status": function.status.value,
                "enabled": function.enabled,
            },
        )
    if not function.enabled:
        raise ToolExecutionNotAllowedError(
            f"Tool '{tool_id}' catalog function is disabled.",
            code="tool_function_disabled",
            detail={
                "tool_id": tool_id,
                "function_id": function.function_id,
                "source_id": function.source_id,
                "category": "catalog",
                "function_status": function.status.value,
                "enabled": False,
            },
        )


def ensure_tool_access_ready(
    access_readiness: object | None,
    tool: object,
    *,
    data: ExecuteToolInput,
) -> None:
    if access_readiness is None:
        return
    readiness = access_readiness.check_tool_access(tool)
    if readiness.ready:
        return
    blocking_checks = tuple(check for check in readiness.checks if not check.ready)
    requirement_summary = ", ".join(
        dict.fromkeys(
            check.binding_id or check.requirement
            for check in blocking_checks
            if (check.binding_id or check.requirement)
        ),
    )
    message = (
        f"Tool '{getattr(tool, 'id', data.tool_id)}' requires access setup"
        f" ({readiness.status}): {readiness.reason}"
        + (f" Required: {requirement_summary}." if requirement_summary else ".")
    )
    raise ToolExecutionNotAllowedError(
        message,
        code="access_not_ready",
        detail={
            "tool_id": getattr(tool, "id", data.tool_id),
            "category": "access",
            "readiness": readiness_payload(readiness),
        },
    )


def ensure_tool_runtime_ready(
    runtime_readiness: object | None,
    tool: object,
    *,
    data: ExecuteToolInput,
) -> None:
    if runtime_readiness is None:
        return
    execution_context = data.execution_context
    workspace_dir = (
        execution_context.get_str("workspace_dir")
        if execution_context is not None
        else None
    )
    readiness = runtime_readiness.check_tool_runtime(
        tool,
        workspace_dir=workspace_dir,
    )
    if readiness.ready:
        return
    blocking_checks = tuple(check for check in readiness.checks if not check.ready)
    requirement_summary = ", ".join(
        dict.fromkeys(
            check.requirement
            for check in blocking_checks
            if check.requirement
        ),
    )
    message = (
        f"Tool '{getattr(tool, 'id', data.tool_id)}' requires runtime setup"
        f" ({readiness.status}): {readiness.reason}"
        + (f" Required: {requirement_summary}." if requirement_summary else ".")
    )
    raise ToolExecutionNotAllowedError(
        message,
        code="tool_runtime_not_ready",
        detail={
            "tool_id": getattr(tool, "id", data.tool_id),
            "category": "runtime",
            "readiness": readiness_payload(readiness),
        },
    )


def readiness_payload(readiness: object) -> dict[str, object]:
    to_payload = getattr(readiness, "to_payload", None)
    if callable(to_payload):
        payload = to_payload()
        if isinstance(payload, dict):
            return dict(payload)
    return {
        "ready": bool(getattr(readiness, "ready", False)),
        "status": str(getattr(readiness, "status", "unknown")),
        "reason": str(getattr(readiness, "reason", "")),
        "setup_available": False,
        "checks": [],
    }
