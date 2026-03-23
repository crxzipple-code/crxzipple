from __future__ import annotations

import os
import threading
from typing import Any

from crxzipple.modules.tool import ToolRunResult


async def run(arguments: dict[str, Any]) -> ToolRunResult:
    name = str(arguments.get("name", "world"))
    return ToolRunResult(
        content={
            "message": f"hello {name}",
        },
        metadata={
            "environment": "local",
            "process_id": os.getpid(),
            "thread_name": threading.current_thread().name,
            "thread_ident": threading.get_ident(),
        },
    )
