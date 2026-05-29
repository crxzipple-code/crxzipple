from __future__ import annotations

import os
import threading
from typing import Any

from crxzipple.modules.tool.domain import ToolExecutionContext, ToolRunResult


async def _local_echo_handler(
    arguments: dict[str, Any],
    execution_context: ToolExecutionContext | None = None,
) -> ToolRunResult:
    return ToolRunResult.text(
        str(arguments.get("message") or ""),
        details={
            "received": dict(arguments),
            "message": arguments.get("message"),
            "execution_context": (
                execution_context.to_payload() if execution_context is not None else None
            ),
        },
        metadata={
            "tool": "echo",
            "environment": "local",
            "process_id": os.getpid(),
            "thread_name": threading.current_thread().name,
            "thread_ident": threading.get_ident(),
        },
    )


def echo(_deps: Any):
    return _local_echo_handler
