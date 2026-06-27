from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from concurrent.futures import TimeoutError as FutureTimeoutError
import threading

from crxzipple.modules.tool.domain.exceptions import ToolValidationError


def ensure_stdio_loop(
    *,
    provider_name: str,
    timeout_seconds: float,
    loop: asyncio.AbstractEventLoop | None,
    thread: threading.Thread | None,
) -> tuple[asyncio.AbstractEventLoop, threading.Thread, bool]:
    if (
        loop is not None
        and loop.is_running()
        and thread is not None
        and thread.is_alive()
    ):
        return loop, thread, False

    ready = threading.Event()
    loop_ref: dict[str, asyncio.AbstractEventLoop] = {}

    def _run_loop() -> None:
        runtime_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(runtime_loop)
        loop_ref["loop"] = runtime_loop
        ready.set()
        runtime_loop.run_forever()
        runtime_loop.close()

    next_thread = threading.Thread(
        target=_run_loop,
        name=f"mcp-stdio-{provider_name}",
        daemon=True,
    )
    next_thread.start()
    ready.wait(timeout=max(float(timeout_seconds), 1.0))
    next_loop = loop_ref.get("loop")
    if next_loop is None:
        raise ToolValidationError(
            f"MCP provider '{provider_name}' could not start async session loop.",
        )
    return next_loop, next_thread, True


def close_stdio_loop(
    *,
    loop: asyncio.AbstractEventLoop | None,
    thread: threading.Thread | None,
    close_session: Callable[[], Awaitable[None]],
    timeout_seconds: float,
) -> None:
    if loop is None:
        return
    timeout = max(float(timeout_seconds), 1.0)
    if loop.is_running():
        future = asyncio.run_coroutine_threadsafe(close_session(), loop)
        try:
            future.result(timeout=timeout)
        except (FutureTimeoutError, RuntimeError):
            pass
        loop.call_soon_threadsafe(loop.stop)
    if thread is not None and thread.is_alive():
        thread.join(timeout=timeout)


__all__ = [
    "close_stdio_loop",
    "ensure_stdio_loop",
]
