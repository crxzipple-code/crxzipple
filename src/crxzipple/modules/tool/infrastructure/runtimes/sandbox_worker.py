from __future__ import annotations

import asyncio
import json
import sys
from typing import Any

from crxzipple.core.config import load_settings
from crxzipple.core.logger import configure_logging, get_logger
from crxzipple.modules.tool.application.activation import ToolPackageApplyContext
from crxzipple.modules.tool.domain import ToolExecutionContext, ToolRunResult
from crxzipple.modules.tool.domain.exceptions import ToolExecutionNotSupportedError
from crxzipple.modules.tool.infrastructure.handler_invocation import (
    invoke_tool_handler,
)
from crxzipple.modules.tool.infrastructure.runtimes.registry import ToolRuntimeRegistry
from crxzipple.modules.tool.infrastructure.tool_packages import (
    apply_tool_package_plans,
    discover_tool_package_plans,
)

logger = get_logger(__name__)


def main(argv: list[str] | None = None) -> int:
    args = argv or sys.argv[1:]
    if len(args) != 1:
        print(
            "usage: python -m crxzipple.modules.tool.infrastructure.runtimes.sandbox_worker <runtime_key>",
            file=sys.stderr,
        )
        return 2

    runtime_key = args[0]
    settings = load_settings()
    configure_logging(settings)

    try:
        arguments, execution_context = _read_arguments()
        result = asyncio.run(_execute(runtime_key, arguments, execution_context))
    except Exception:
        logger.exception("sandbox worker failed", extra={"runtime_key": runtime_key})
        return 1

    print(json.dumps(_serialize_result(result), ensure_ascii=True, sort_keys=True))
    return 0


def _read_arguments() -> tuple[dict[str, Any], ToolExecutionContext | None]:
    raw = sys.stdin.read().strip()
    if not raw:
        return {}, None

    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ToolExecutionNotSupportedError(
            "Sandbox worker expects a JSON object payload.",
        )
    arguments = payload.get("arguments", {})
    if not isinstance(arguments, dict):
        raise ToolExecutionNotSupportedError(
            "Sandbox worker expects 'arguments' to be a JSON object.",
        )
    execution_context_payload = payload.get("execution_context")
    if execution_context_payload is not None and not isinstance(
        execution_context_payload,
        dict,
    ):
        raise ToolExecutionNotSupportedError(
            "Sandbox worker expects 'execution_context' to be a JSON object when present.",
        )
    return arguments, ToolExecutionContext.from_payload(execution_context_payload)


async def _execute(
    runtime_key: str,
    arguments: dict[str, Any],
    execution_context: ToolExecutionContext | None,
) -> Any:
    registry = ToolRuntimeRegistry()
    apply_tool_package_plans(
        ToolPackageApplyContext(
            sandbox_tool_registry=registry,
        ),
        discover_tool_package_plans(),
        include_openapi=False,
        include_local=False,
    )
    handler = registry.get_handler(runtime_key)
    if handler is None:
        raise ToolExecutionNotSupportedError(
            f"No sandbox handler is registered for runtime '{runtime_key}'.",
        )
    return await invoke_tool_handler(handler, arguments, execution_context)


def _serialize_result(result: Any) -> Any:
    if isinstance(result, ToolRunResult):
        return result.to_payload()
    return result


if __name__ == "__main__":
    raise SystemExit(main())
