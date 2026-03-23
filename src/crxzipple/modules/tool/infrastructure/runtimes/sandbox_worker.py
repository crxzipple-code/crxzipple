from __future__ import annotations

import asyncio
import json
import sys
from typing import Any

from crxzipple.core.config import load_settings
from crxzipple.core.logger import configure_logging, get_logger
from crxzipple.modules.tool.domain import ToolRunResult
from crxzipple.modules.tool.domain.exceptions import ToolExecutionNotSupportedError
from crxzipple.modules.tool.infrastructure.runtimes.registry import ToolRuntimeRegistry
from crxzipple.modules.tool.infrastructure.runtimes.sandbox_handlers import (
    register_builtin_sandbox_handlers,
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
        payload = _read_arguments()
        result = asyncio.run(_execute(runtime_key, payload))
    except Exception:
        logger.exception("sandbox worker failed", extra={"runtime_key": runtime_key})
        return 1

    print(json.dumps(_serialize_result(result), ensure_ascii=True, sort_keys=True))
    return 0


def _read_arguments() -> dict[str, Any]:
    raw = sys.stdin.read().strip()
    if not raw:
        return {}

    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ToolExecutionNotSupportedError(
            "Sandbox worker expects a JSON object payload.",
        )
    return payload


async def _execute(runtime_key: str, payload: dict[str, Any]) -> Any:
    registry = ToolRuntimeRegistry()
    register_builtin_sandbox_handlers(registry)
    handler = registry.get_handler(runtime_key)
    if handler is None:
        raise ToolExecutionNotSupportedError(
            f"No sandbox handler is registered for runtime '{runtime_key}'.",
        )
    return await handler(payload)


def _serialize_result(result: Any) -> Any:
    if isinstance(result, ToolRunResult):
        return result.to_payload()
    return result


if __name__ == "__main__":
    raise SystemExit(main())
