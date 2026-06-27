from __future__ import annotations

import select
import subprocess
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
from .mcp_stdio_messages import (
    parse_stdio_response_line,
    stdio_message_text,
    stdio_send_failure_message,
    stdio_session_unavailable_message,
    stdio_terminated_message,
    stdio_timeout_message,
)
from .mcp_stdio_processes import close_sync_stdio_process, start_sync_stdio_process


class McpStdioSyncSession:
    def __init__(self, config: McpProviderSettings) -> None:
        self.config = config
        self._lock = threading.Lock()
        self._process: subprocess.Popen[str] | None = None
        self._initialized = False

    def request(
        self,
        method: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            self._ensure_session_locked()
            return self._request_locked(method, params or {})

    def close(self) -> None:
        with self._lock:
            self._close_process_locked()

    def _ensure_session_locked(self) -> None:
        if self._process is None or self._process.poll() is not None:
            self._start_process_locked()
        if not self._initialized:
            self._initialize_locked()

    def _start_process_locked(self) -> None:
        self._process = start_sync_stdio_process(self.config)
        self._initialized = False

    def _initialize_locked(self) -> None:
        self._request_locked(
            "initialize",
            initialize_params(),
        )
        self._send_notification_locked("notifications/initialized", {})
        self._initialized = True

    def _request_locked(
        self,
        method: str,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        payload = jsonrpc_request_payload(method, params)
        self._write_message_locked(payload)
        response = self._read_response_locked(expected_id=payload["id"], method=method)
        return require_result_payload(
            response,
            provider_name=self.config.name,
            method=method,
        )

    def _send_notification_locked(
        self,
        method: str,
        params: dict[str, Any],
    ) -> None:
        self._write_message_locked(jsonrpc_notification_payload(method, params))

    def _write_message_locked(self, payload: dict[str, Any]) -> None:
        process = self._process
        if process is None or process.stdin is None:
            raise ToolValidationError(
                stdio_session_unavailable_message(self.config.name),
            )

        try:
            process.stdin.write(stdio_message_text(payload))
            process.stdin.flush()
        except BrokenPipeError as exc:
            self._close_process_locked()
            raise ToolValidationError(
                stdio_send_failure_message(self.config.name),
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
                stdio_session_unavailable_message(self.config.name),
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
                    stdio_timeout_message(self.config.name, method),
                )

            line = process.stdout.readline()
            if line == "":
                detail = self._read_stderr_locked()
                self._close_process_locked()
                raise ToolValidationError(
                    stdio_terminated_message(
                        self.config.name,
                        method=method,
                        stderr_detail=detail,
                    ),
                )

            response = parse_stdio_response_line(
                line,
                expected_id=expected_id,
                provider_name=self.config.name,
                method=method,
            )
            if response is not None:
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
        close_sync_stdio_process(process)
