from __future__ import annotations

import asyncio
from concurrent.futures import TimeoutError as FutureTimeoutError
import json
import select
import subprocess
import threading
from typing import Any
from uuid import uuid4

from crxzipple.core.config import McpProviderSettings
from crxzipple.modules.tool.domain.exceptions import ToolValidationError


class McpStdioClient:
    def __init__(self, config: McpProviderSettings) -> None:
        self.config = config
        self._lock = threading.Lock()
        self._process: subprocess.Popen[str] | None = None
        self._initialized = False
        self._async_loop_guard = threading.Lock()
        self._async_loop: asyncio.AbstractEventLoop | None = None
        self._async_loop_thread: threading.Thread | None = None
        self._async_process: asyncio.subprocess.Process | None = None
        self._async_initialized = False
        self._async_lock: asyncio.Lock | None = None

    def list_tools(self) -> list[dict[str, Any]]:
        result = self.request("tools/list")
        tools = result.get("tools")
        if not isinstance(tools, list):
            raise ToolValidationError(
                f"MCP provider '{self.config.name}' returned an invalid tools/list payload.",
            )
        return [tool for tool in tools if isinstance(tool, dict)]

    def call_tool(
        self,
        *,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> Any:
        result = self.request(
            "tools/call",
            {
                "name": tool_name,
                "arguments": dict(arguments),
            },
        )
        return result

    async def call_tool_async(
        self,
        *,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> Any:
        result = await self.request_async(
            "tools/call",
            {
                "name": tool_name,
                "arguments": dict(arguments),
            },
        )
        return result

    def request(
        self,
        method: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            self._ensure_session_locked()
            return self._request_locked(method, params or {})

    async def request_async(
        self,
        method: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        loop = self._ensure_async_loop()
        future = asyncio.run_coroutine_threadsafe(
            self._request_in_async_loop(method, params or {}),
            loop,
        )
        return await asyncio.wrap_future(future)

    def close(self) -> None:
        with self._lock:
            self._close_process_locked()
        self._close_async_loop()

    def _ensure_async_loop(self) -> asyncio.AbstractEventLoop:
        with self._async_loop_guard:
            if (
                self._async_loop is not None
                and self._async_loop.is_running()
                and self._async_loop_thread is not None
                and self._async_loop_thread.is_alive()
            ):
                return self._async_loop

            ready = threading.Event()
            loop_ref: dict[str, asyncio.AbstractEventLoop] = {}

            def _run_loop() -> None:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop_ref["loop"] = loop
                ready.set()
                loop.run_forever()
                loop.close()

            thread = threading.Thread(
                target=_run_loop,
                name=f"mcp-stdio-{self.config.name}",
                daemon=True,
            )
            thread.start()
            ready.wait(timeout=max(float(self.config.timeout_seconds), 1.0))
            loop = loop_ref.get("loop")
            if loop is None:
                raise ToolValidationError(
                    f"MCP provider '{self.config.name}' could not start async session loop.",
                )
            self._async_loop = loop
            self._async_loop_thread = thread
            self._async_process = None
            self._async_initialized = False
            self._async_lock = None
            return loop

    def _close_async_loop(self) -> None:
        with self._async_loop_guard:
            loop = self._async_loop
            thread = self._async_loop_thread
            self._async_loop = None
            self._async_loop_thread = None
            self._async_lock = None
            if loop is None:
                return
            if loop.is_running():
                future = asyncio.run_coroutine_threadsafe(
                    self._close_async_session(),
                    loop,
                )
                try:
                    future.result(timeout=max(float(self.config.timeout_seconds), 1.0))
                except (FutureTimeoutError, RuntimeError):
                    pass
                loop.call_soon_threadsafe(loop.stop)
            if thread is not None and thread.is_alive():
                thread.join(timeout=max(float(self.config.timeout_seconds), 1.0))

    async def _request_in_async_loop(
        self,
        method: str,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        if self._async_lock is None:
            self._async_lock = asyncio.Lock()
        async with self._async_lock:
            await self._ensure_async_session_locked()
            return await self._request_async_locked(method, params)

    async def _ensure_async_session_locked(self) -> None:
        if self._async_process is None or self._async_process.returncode is not None:
            await self._start_async_process_locked()
        if not self._async_initialized:
            await self._initialize_async_locked()

    async def _start_async_process_locked(self) -> None:
        try:
            self._async_process = await asyncio.create_subprocess_exec(
                *self.config.command,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except OSError as exc:
            raise ToolValidationError(
                f"MCP provider '{self.config.name}' could not start command {self.config.command!r}: {exc}",
            ) from exc

        self._async_initialized = False

    async def _initialize_async_locked(self) -> None:
        await self._request_async_locked(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {
                    "name": "crxzipple",
                    "version": "0.1.0",
                },
            },
        )
        await self._send_async_notification_locked("notifications/initialized", {})
        self._async_initialized = True

    async def _request_async_locked(
        self,
        method: str,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        payload = {
            "jsonrpc": "2.0",
            "id": uuid4().hex,
            "method": method,
            "params": params,
        }
        await self._write_async_message_locked(payload)
        response = await self._read_async_response_locked(
            expected_id=payload["id"],
            method=method,
        )
        error = response.get("error")
        if isinstance(error, dict):
            message = str(error.get("message", "unknown MCP error"))
            raise ToolValidationError(
                f"MCP provider '{self.config.name}' returned an error for method '{method}': {message}",
            )

        result = response.get("result")
        if not isinstance(result, dict):
            raise ToolValidationError(
                f"MCP provider '{self.config.name}' returned an invalid result payload for method '{method}'.",
            )
        return result

    async def _send_async_notification_locked(
        self,
        method: str,
        params: dict[str, Any],
    ) -> None:
        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
        }
        await self._write_async_message_locked(payload)

    async def _write_async_message_locked(self, payload: dict[str, Any]) -> None:
        process = self._async_process
        if process is None or process.stdin is None:
            raise ToolValidationError(
                f"MCP provider '{self.config.name}' session is not available.",
            )

        try:
            process.stdin.write((json.dumps(payload) + "\n").encode("utf-8"))
            await process.stdin.drain()
        except BrokenPipeError as exc:
            await self._close_async_process_locked()
            raise ToolValidationError(
                f"MCP provider '{self.config.name}' session terminated unexpectedly while sending a request.",
            ) from exc

    async def _read_async_response_locked(
        self,
        *,
        expected_id: str,
        method: str,
    ) -> dict[str, Any]:
        process = self._async_process
        if process is None or process.stdout is None:
            raise ToolValidationError(
                f"MCP provider '{self.config.name}' session is not available.",
            )

        while True:
            try:
                line = await asyncio.wait_for(
                    process.stdout.readline(),
                    timeout=self.config.timeout_seconds,
                )
            except asyncio.TimeoutError as exc:
                await self._close_async_process_locked()
                raise ToolValidationError(
                    f"MCP provider '{self.config.name}' timed out while waiting for method '{method}'.",
                ) from exc
            if line == b"":
                detail = await self._read_async_stderr_locked()
                await self._close_async_process_locked()
                raise ToolValidationError(
                    f"MCP provider '{self.config.name}' terminated while waiting for method '{method}': {detail or 'no stderr output'}",
                )

            response = _parse_json_response(line.decode("utf-8", errors="replace"))
            response_id = response.get("id")
            if response_id is None:
                continue
            if str(response_id) != expected_id:
                raise ToolValidationError(
                    f"MCP provider '{self.config.name}' returned an unexpected response id while calling '{method}'.",
                )
            return response

    async def _read_async_stderr_locked(self) -> str:
        process = self._async_process
        if process is None or process.stderr is None:
            return ""
        try:
            output = await process.stderr.read()
            return output.decode("utf-8", errors="replace").strip()
        except Exception:
            return ""

    async def _close_async_session(self) -> None:
        if self._async_lock is None:
            await self._close_async_process_locked()
            return
        async with self._async_lock:
            await self._close_async_process_locked()

    async def _close_async_process_locked(self) -> None:
        process = self._async_process
        self._async_process = None
        self._async_initialized = False
        if process is None:
            return

        if process.stdin is not None:
            process.stdin.close()
            try:
                await process.stdin.wait_closed()
            except Exception:
                pass

        if process.returncode is not None:
            return

        try:
            process.terminate()
            await asyncio.wait_for(process.wait(), timeout=1)
        except (asyncio.TimeoutError, ProcessLookupError):
            process.kill()
            await asyncio.wait_for(process.wait(), timeout=1)

    def _ensure_session_locked(self) -> None:
        if self._process is None or self._process.poll() is not None:
            self._start_process_locked()
        if not self._initialized:
            self._initialize_locked()

    def _start_process_locked(self) -> None:
        try:
            self._process = subprocess.Popen(
                self.config.command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
        except OSError as exc:
            raise ToolValidationError(
                f"MCP provider '{self.config.name}' could not start command {self.config.command!r}: {exc}",
            ) from exc

        self._initialized = False

    def _initialize_locked(self) -> None:
        self._request_locked(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {
                    "name": "crxzipple",
                    "version": "0.1.0",
                },
            },
        )
        self._send_notification_locked("notifications/initialized", {})
        self._initialized = True

    def _request_locked(
        self,
        method: str,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        payload = {
            "jsonrpc": "2.0",
            "id": uuid4().hex,
            "method": method,
            "params": params,
        }
        self._write_message_locked(payload)
        response = self._read_response_locked(expected_id=payload["id"], method=method)
        error = response.get("error")
        if isinstance(error, dict):
            message = str(error.get("message", "unknown MCP error"))
            raise ToolValidationError(
                f"MCP provider '{self.config.name}' returned an error for method '{method}': {message}",
            )

        result = response.get("result")
        if not isinstance(result, dict):
            raise ToolValidationError(
                f"MCP provider '{self.config.name}' returned an invalid result payload for method '{method}'.",
            )
        return result

    def _send_notification_locked(
        self,
        method: str,
        params: dict[str, Any],
    ) -> None:
        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
        }
        self._write_message_locked(payload)

    def _write_message_locked(self, payload: dict[str, Any]) -> None:
        process = self._process
        if process is None or process.stdin is None:
            raise ToolValidationError(
                f"MCP provider '{self.config.name}' session is not available.",
            )

        try:
            process.stdin.write(json.dumps(payload) + "\n")
            process.stdin.flush()
        except BrokenPipeError as exc:
            self._close_process_locked()
            raise ToolValidationError(
                f"MCP provider '{self.config.name}' session terminated unexpectedly while sending a request.",
            ) from exc

    def _read_response_locked(
        self,
        *,
        expected_id: str,
        method: str,
    ) -> dict[str, Any]:
        process = self._process
        if process is None or process.stdout is None:
            raise ToolValidationError(
                f"MCP provider '{self.config.name}' session is not available.",
            )

        while True:
            readable, _, _ = select.select(
                [process.stdout],
                [],
                [],
                self.config.timeout_seconds,
            )
            if not readable:
                self._close_process_locked()
                raise ToolValidationError(
                    f"MCP provider '{self.config.name}' timed out while waiting for method '{method}'.",
                )

            line = process.stdout.readline()
            if line == "":
                detail = self._read_stderr_locked()
                self._close_process_locked()
                raise ToolValidationError(
                    f"MCP provider '{self.config.name}' terminated while waiting for method '{method}': {detail or 'no stderr output'}",
                )

            response = _parse_json_response(line)
            response_id = response.get("id")
            if response_id is None:
                continue
            if str(response_id) != expected_id:
                raise ToolValidationError(
                    f"MCP provider '{self.config.name}' returned an unexpected response id while calling '{method}'.",
                )
            return response

    def _read_stderr_locked(self) -> str:
        process = self._process
        if process is None or process.stderr is None:
            return ""
        try:
            return process.stderr.read().strip()
        except Exception:
            return ""

    def _close_process_locked(self) -> None:
        process = self._process
        self._process = None
        self._initialized = False
        if process is None:
            return

        if process.stdin is not None and not process.stdin.closed:
            process.stdin.close()

        if process.poll() is not None:
            return

        try:
            process.terminate()
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=1)


def _parse_json_response(stdout: str) -> dict[str, Any]:
    lines = [line.strip() for line in stdout.splitlines() if line.strip()]
    if not lines:
        raise ToolValidationError("MCP command returned no JSON response.")

    try:
        payload = json.loads(lines[-1])
    except json.JSONDecodeError as exc:
        raise ToolValidationError(
            "MCP command returned invalid JSON on stdout.",
        ) from exc

    if not isinstance(payload, dict):
        raise ToolValidationError("MCP command response must decode to a JSON object.")
    return payload
