from __future__ import annotations

import asyncio
import threading
from typing import Any

from crxzipple.core.config import McpProviderSettings
from crxzipple.modules.tool.domain.exceptions import ToolValidationError
from .mcp_protocol import (
    initialize_params,
    jsonrpc_notification_payload,
    jsonrpc_request_payload,
    require_result_payload,
)
from .mcp_stdio_async_loop import close_stdio_loop, ensure_stdio_loop
from .mcp_stdio_messages import (
    parse_stdio_response_line,
    stdio_message_bytes,
    stdio_send_failure_message,
    stdio_session_unavailable_message,
    stdio_terminated_message,
    stdio_timeout_message,
)
from .mcp_stdio_processes import close_async_stdio_process, start_async_stdio_process


class McpStdioAsyncSession:
    def __init__(self, config: McpProviderSettings) -> None:
        self.config = config
        self._loop_guard = threading.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._loop_thread: threading.Thread | None = None
        self._process: asyncio.subprocess.Process | None = None
        self._initialized = False
        self._lock: asyncio.Lock | None = None

    async def request(
        self,
        method: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        loop = self._ensure_loop()
        future = asyncio.run_coroutine_threadsafe(
            self._request_in_loop(method, params or {}),
            loop,
        )
        return await asyncio.wrap_future(future)

    def close(self) -> None:
        with self._loop_guard:
            loop = self._loop
            thread = self._loop_thread
            self._loop = None
            self._loop_thread = None
            self._lock = None
            close_stdio_loop(
                loop=loop,
                thread=thread,
                close_session=self._close_session,
                timeout_seconds=float(self.config.timeout_seconds),
            )

    def _ensure_loop(self) -> asyncio.AbstractEventLoop:
        with self._loop_guard:
            loop, thread, created = ensure_stdio_loop(
                provider_name=self.config.name,
                timeout_seconds=float(self.config.timeout_seconds),
                loop=self._loop,
                thread=self._loop_thread,
            )
            self._loop = loop
            self._loop_thread = thread
            if created:
                self._process = None
                self._initialized = False
                self._lock = None
            return loop

    async def _request_in_loop(
        self,
        method: str,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        if self._lock is None:
            self._lock = asyncio.Lock()
        async with self._lock:
            await self._ensure_session_locked()
            return await self._request_locked(method, params)

    async def _ensure_session_locked(self) -> None:
        if self._process is None or self._process.returncode is not None:
            await self._start_process_locked()
        if not self._initialized:
            await self._initialize_locked()

    async def _start_process_locked(self) -> None:
        self._process = await start_async_stdio_process(self.config)
        self._initialized = False

    async def _initialize_locked(self) -> None:
        await self._request_locked(
            "initialize",
            initialize_params(),
        )
        await self._send_notification_locked("notifications/initialized", {})
        self._initialized = True

    async def _request_locked(
        self,
        method: str,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        payload = jsonrpc_request_payload(method, params)
        await self._write_message_locked(payload)
        response = await self._read_response_locked(
            expected_id=payload["id"],
            method=method,
        )
        return require_result_payload(
            response,
            provider_name=self.config.name,
            method=method,
        )

    async def _send_notification_locked(
        self,
        method: str,
        params: dict[str, Any],
    ) -> None:
        await self._write_message_locked(jsonrpc_notification_payload(method, params))

    async def _write_message_locked(self, payload: dict[str, Any]) -> None:
        process = self._process
        if process is None or process.stdin is None:
            raise ToolValidationError(
                stdio_session_unavailable_message(self.config.name),
            )

        try:
            process.stdin.write(stdio_message_bytes(payload))
            await process.stdin.drain()
        except BrokenPipeError as exc:
            await self._close_process_locked()
            raise ToolValidationError(
                stdio_send_failure_message(self.config.name),
            ) from exc

    async def _read_response_locked(
        self,
        *,
        expected_id: str,
        method: str,
    ) -> dict[str, Any]:
        process = self._process
        if process is None or process.stdout is None:
            raise ToolValidationError(
                stdio_session_unavailable_message(self.config.name),
            )

        while True:
            try:
                line = await asyncio.wait_for(
                    process.stdout.readline(),
                    timeout=self.config.timeout_seconds,
                )
            except asyncio.TimeoutError as exc:
                await self._close_process_locked()
                raise ToolValidationError(
                    stdio_timeout_message(self.config.name, method),
                ) from exc
            if line == b"":
                detail = await self._read_stderr_locked()
                await self._close_process_locked()
                raise ToolValidationError(
                    stdio_terminated_message(
                        self.config.name,
                        method=method,
                        stderr_detail=detail,
                    ),
                )

            response = parse_stdio_response_line(
                line.decode("utf-8", errors="replace"),
                expected_id=expected_id,
                provider_name=self.config.name,
                method=method,
            )
            if response is not None:
                return response

    async def _read_stderr_locked(self) -> str:
        process = self._process
        if process is None or process.stderr is None:
            return ""
        try:
            output = await process.stderr.read()
            return output.decode("utf-8", errors="replace").strip()
        except Exception:
            return ""

    async def _close_session(self) -> None:
        if self._lock is None:
            await self._close_process_locked()
            return
        async with self._lock:
            await self._close_process_locked()

    async def _close_process_locked(self) -> None:
        process = self._process
        self._process = None
        self._initialized = False
        await close_async_stdio_process(process)
