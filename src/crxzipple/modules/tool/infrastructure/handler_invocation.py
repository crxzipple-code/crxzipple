from __future__ import annotations

import inspect
from typing import Any, Callable

from crxzipple.modules.tool.domain import ToolExecutionContext


def invoke_tool_handler(
    handler: Callable[..., Any],
    arguments: dict[str, Any],
    execution_context: ToolExecutionContext | None,
) -> Any:
    try:
        signature = inspect.signature(handler)
    except (TypeError, ValueError):
        return handler(arguments)

    positional_params = [
        parameter
        for parameter in signature.parameters.values()
        if parameter.kind
        in (
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        )
    ]
    has_varargs = any(
        parameter.kind is inspect.Parameter.VAR_POSITIONAL
        for parameter in signature.parameters.values()
    )
    if has_varargs or len(positional_params) >= 2:
        return handler(arguments, execution_context)
    return handler(arguments)
