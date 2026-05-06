from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path
import select
import subprocess
import tempfile
import threading
from typing import Any, Callable
from uuid import uuid4

from crxzipple.modules.browser.domain import (
    BrowserSystemConfig,
    BrowserTab,
    BrowserValidationError,
)
from crxzipple.modules.daemon import (
    DaemonApplicationService,
    DaemonLease,
    DaemonValidationError,
)


def _normalize_user_data_dir(user_data_dir: str | None) -> str | None:
    if user_data_dir is None:
        return None
    normalized = user_data_dir.strip()
    return normalized or None


def _parse_page_id(target_id: str) -> int:
    normalized = target_id.strip()
    if not normalized:
        raise BrowserValidationError("target_id is required.")
    try:
        page_id = int(normalized)
    except ValueError as exc:
        raise BrowserValidationError(f"Browser tab '{target_id}' is not a valid MCP page id.") from exc
    if page_id < 1:
        raise BrowserValidationError(f"Browser tab '{target_id}' is not a valid MCP page id.")
    return page_id


def _as_record(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        return dict(value)
    return None


def _extract_structured_content(result: dict[str, Any]) -> dict[str, Any]:
    return _as_record(result.get("structuredContent")) or {}


def _extract_text_content(result: dict[str, Any]) -> list[str]:
    content = result.get("content")
    if not isinstance(content, list):
        return []
    resolved: list[str] = []
    for item in content:
        record = _as_record(item)
        if record is None:
            continue
        text = record.get("text")
        if isinstance(text, str) and text.strip():
            resolved.append(text)
    return resolved


def _extract_tool_error_message(result: dict[str, Any], *, name: str) -> str:
    structured = _extract_structured_content(result)
    message = structured.get("message")
    if isinstance(message, str) and message.strip():
        return message.strip()
    for block in _extract_text_content(result):
        if block.strip():
            return block.strip()
    return f"Chrome MCP tool '{name}' failed."


def _extract_json_text(text: str) -> Any:
    stripped = text.strip()
    if not stripped:
        return None
    if "```json" in stripped.lower():
        start = stripped.lower().find("```json")
        body = stripped[start + len("```json") :].strip()
        if "```" in body:
            body = body.split("```", 1)[0].strip()
        stripped = body
    return json.loads(stripped)


def _extract_json_message(result: dict[str, Any]) -> Any:
    candidates = []
    structured = _extract_structured_content(result)
    message = structured.get("message")
    if isinstance(message, str) and message.strip():
        candidates.append(message)
    candidates.extend(_extract_text_content(result))
    last_error: Exception | None = None
    for candidate in candidates:
        try:
            return _extract_json_text(candidate)
        except Exception as exc:  # noqa: BLE001
            last_error = exc
    if last_error is not None:
        raise BrowserValidationError(
            f"Chrome MCP evaluate_script returned invalid JSON content: {last_error}",
        ) from last_error
    return None


def _extract_structured_pages(result: dict[str, Any]) -> list[dict[str, Any]]:
    structured = _extract_structured_content(result)
    pages = structured.get("pages")
    if isinstance(pages, list):
        resolved: list[dict[str, Any]] = []
        for item in pages:
            record = _as_record(item)
            if record is None:
                continue
            page_id = record.get("id")
            if isinstance(page_id, int):
                resolved.append(record)
        if resolved:
            return resolved

    resolved = []
    for block in _extract_text_content(result):
        for line in block.splitlines():
            match = line.strip()
            if not match:
                continue
            page_id_text, _, remainder = match.partition(":")
            try:
                page_id = int(page_id_text.strip())
            except ValueError:
                continue
            selected = "[selected]" in remainder.lower()
            url = remainder.replace("[selected]", "").strip()
            resolved.append(
                {
                    "id": page_id,
                    "url": url or None,
                    "selected": selected,
                }
            )
    return resolved


def _to_browser_tabs(pages: list[dict[str, Any]]) -> tuple[BrowserTab, ...]:
    return tuple(
        BrowserTab(
            target_id=str(page["id"]),
            url=str(page.get("url") or "").strip(),
            title="",
            type="page",
        )
        for page in pages
        if isinstance(page.get("id"), int)
    )


class _ChromeMcpStdioClient:
    def __init__(
        self,
        *,
        profile_name: str,
        command: tuple[str, ...],
        timeout_seconds: int,
        popen: Callable[..., subprocess.Popen[str]] = subprocess.Popen,
    ) -> None:
        self.profile_name = profile_name
        self.command = tuple(command)
        self.timeout_seconds = timeout_seconds
        self._popen = popen
        self._lock = threading.Lock()
        self._process: subprocess.Popen[str] | None = None
        self._initialized = False

    @property
    def pid(self) -> int | None:
        process = self._process
        if process is None:
            return None
        return process.pid

    def list_tools(self) -> list[dict[str, Any]]:
        result = self.request("tools/list")
        tools = result.get("tools")
        if not isinstance(tools, list):
            raise BrowserValidationError(
                f"Chrome MCP for profile '{self.profile_name}' returned an invalid tools/list payload.",
            )
        return [tool for tool in tools if isinstance(tool, dict)]

    def call_tool(self, *, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        result = self.request(
            "tools/call",
            {
                "name": tool_name,
                "arguments": dict(arguments),
            },
        )
        return result

    def request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
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
        try:
            self._process = self._popen(
                self.command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
        except OSError as exc:
            raise BrowserValidationError(
                f"Chrome MCP for profile '{self.profile_name}' could not start command {self.command!r}: {exc}",
            ) from exc
        self._initialized = False

    def _initialize_locked(self) -> None:
        self._request_locked(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {
                    "name": "crxzipple-browser",
                    "version": "0.1.0",
                },
            },
        )
        self._send_notification_locked("notifications/initialized", {})
        result = self._request_locked("tools/list", {})
        tools = result.get("tools")
        if not isinstance(tools, list):
            self._close_process_locked()
            raise BrowserValidationError(
                f"Chrome MCP for profile '{self.profile_name}' returned an invalid tools/list payload.",
            )
        if not any(isinstance(tool, dict) and tool.get("name") == "list_pages" for tool in tools):
            self._close_process_locked()
            raise BrowserValidationError(
                f"Chrome MCP for profile '{self.profile_name}' did not expose list_pages.",
            )
        self._initialized = True

    def _request_locked(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
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
            message = str(error.get("message") or "unknown MCP error")
            raise BrowserValidationError(
                f"Chrome MCP for profile '{self.profile_name}' returned an error for method '{method}': {message}",
            )
        result = response.get("result")
        if not isinstance(result, dict):
            raise BrowserValidationError(
                f"Chrome MCP for profile '{self.profile_name}' returned an invalid result for method '{method}'.",
            )
        return result

    def _send_notification_locked(self, method: str, params: dict[str, Any]) -> None:
        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
        }
        self._write_message_locked(payload)

    def _write_message_locked(self, payload: dict[str, Any]) -> None:
        process = self._process
        if process is None or process.stdin is None:
            raise BrowserValidationError(
                f"Chrome MCP session for profile '{self.profile_name}' is not available.",
            )
        try:
            process.stdin.write(json.dumps(payload) + "\n")
            process.stdin.flush()
        except BrokenPipeError as exc:
            self._close_process_locked()
            raise BrowserValidationError(
                f"Chrome MCP session for profile '{self.profile_name}' terminated unexpectedly.",
            ) from exc

    def _read_response_locked(self, *, expected_id: str, method: str) -> dict[str, Any]:
        process = self._process
        if process is None or process.stdout is None:
            raise BrowserValidationError(
                f"Chrome MCP session for profile '{self.profile_name}' is not available.",
            )
        while True:
            readable, _, _ = select.select(
                [process.stdout],
                [],
                [],
                self.timeout_seconds,
            )
            if not readable:
                self._close_process_locked()
                raise BrowserValidationError(
                    f"Chrome MCP for profile '{self.profile_name}' timed out while waiting for '{method}'.",
                )
            line = process.stdout.readline()
            if line == "":
                detail = self._read_stderr_locked()
                self._close_process_locked()
                raise BrowserValidationError(
                    f"Chrome MCP for profile '{self.profile_name}' terminated while waiting for '{method}': {detail or 'no stderr output'}",
                )
            try:
                response = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(response, dict):
                continue
            response_id = response.get("id")
            if response_id is None:
                continue
            if str(response_id) != expected_id:
                raise BrowserValidationError(
                    f"Chrome MCP for profile '{self.profile_name}' returned an unexpected response id.",
                )
            return response

    def _read_stderr_locked(self) -> str:
        process = self._process
        if process is None or process.stderr is None:
            return ""
        try:
            return process.stderr.read().strip()
        except Exception:  # noqa: BLE001
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


class ChromeMcpClientPool:
    def __init__(
        self,
        *,
        client_factory: Callable[
            [str, BrowserSystemConfig, str | None],
            _ChromeMcpStdioClient | Any,
        ]
        | None = None,
        daemon_service: DaemonApplicationService,
    ) -> None:
        self._client_factory = client_factory or self._create_client
        self._lock = threading.Lock()
        self._clients: dict[tuple[str, str | None], Any] = {}
        self._daemon_service = daemon_service

    def ensure_available(
        self,
        *,
        profile_name: str,
        system: BrowserSystemConfig,
        user_data_dir: str | None = None,
    ) -> None:
        self._client(
            profile_name=profile_name,
            system=system,
            user_data_dir=user_data_dir,
        )

    def get_pid(
        self,
        *,
        profile_name: str,
        system: BrowserSystemConfig,
        user_data_dir: str | None = None,
    ) -> int | None:
        client = self._client(
            profile_name=profile_name,
            system=system,
            user_data_dir=user_data_dir,
        )
        return getattr(client, "pid", None)

    def close_profile(self, *, profile_name: str) -> None:
        normalized = profile_name.strip().lower()
        with self._lock:
            keys = [key for key in self._clients if key[0] == normalized]
            clients = [self._clients.pop(key) for key in keys]
        for client in clients:
            client.close()
        for key_profile, user_data_dir in keys:
            self._sync_daemon_stopped(
                profile_name=key_profile,
                user_data_dir=user_data_dir,
            )

    def close(self) -> None:
        with self._lock:
            entries = list(self._clients.items())
            self._clients.clear()
        for (_profile_name, _user_data_dir), client in entries:
            client.close()
            self._sync_daemon_stopped(
                profile_name=_profile_name,
                user_data_dir=_user_data_dir,
            )

    def list_tabs(
        self,
        *,
        profile_name: str,
        system: BrowserSystemConfig,
        user_data_dir: str | None = None,
    ) -> tuple[BrowserTab, ...]:
        result = self._call_tool(
            profile_name=profile_name,
            system=system,
            user_data_dir=user_data_dir,
            name="list_pages",
        )
        return _to_browser_tabs(_extract_structured_pages(result))

    def open_tab(
        self,
        *,
        profile_name: str,
        system: BrowserSystemConfig,
        url: str,
        user_data_dir: str | None = None,
    ) -> BrowserTab:
        result = self._call_tool(
            profile_name=profile_name,
            system=system,
            user_data_dir=user_data_dir,
            name="new_page",
            arguments={"url": url},
        )
        pages = _extract_structured_pages(result)
        chosen = next((page for page in pages if page.get("selected") is True), None)
        if chosen is None and pages:
            chosen = pages[-1]
        if chosen is None or not isinstance(chosen.get("id"), int):
            raise BrowserValidationError("Chrome MCP did not return the created page.")
        return BrowserTab(
            target_id=str(chosen["id"]),
            url=str(chosen.get("url") or url).strip(),
            title="",
            type="page",
        )

    def focus_tab(
        self,
        *,
        profile_name: str,
        system: BrowserSystemConfig,
        target_id: str,
        user_data_dir: str | None = None,
    ) -> None:
        self._call_tool(
            profile_name=profile_name,
            system=system,
            user_data_dir=user_data_dir,
            name="select_page",
            arguments={
                "pageId": _parse_page_id(target_id),
                "bringToFront": True,
            },
        )

    def close_tab(
        self,
        *,
        profile_name: str,
        system: BrowserSystemConfig,
        target_id: str,
        user_data_dir: str | None = None,
    ) -> None:
        self._call_tool(
            profile_name=profile_name,
            system=system,
            user_data_dir=user_data_dir,
            name="close_page",
            arguments={"pageId": _parse_page_id(target_id)},
        )

    def navigate_tab(
        self,
        *,
        profile_name: str,
        system: BrowserSystemConfig,
        target_id: str,
        url: str,
        user_data_dir: str | None = None,
        timeout_ms: int | None = None,
    ) -> BrowserTab:
        arguments: dict[str, Any] = {
            "pageId": _parse_page_id(target_id),
            "type": "url",
            "url": url,
        }
        if timeout_ms is not None:
            arguments["timeout"] = timeout_ms
        self._call_tool(
            profile_name=profile_name,
            system=system,
            user_data_dir=user_data_dir,
            name="navigate_page",
            arguments=arguments,
        )
        tabs = self.list_tabs(
            profile_name=profile_name,
            system=system,
            user_data_dir=user_data_dir,
        )
        for tab in tabs:
            if tab.target_id == target_id:
                return tab
        return BrowserTab(target_id=target_id, url=url, title="", type="page")

    def resize_page(
        self,
        *,
        profile_name: str,
        system: BrowserSystemConfig,
        target_id: str,
        width: int,
        height: int,
        user_data_dir: str | None = None,
    ) -> None:
        self._call_tool(
            profile_name=profile_name,
            system=system,
            user_data_dir=user_data_dir,
            name="resize_page",
            arguments={
                "pageId": _parse_page_id(target_id),
                "width": int(width),
                "height": int(height),
            },
        )

    def take_snapshot(
        self,
        *,
        profile_name: str,
        system: BrowserSystemConfig,
        target_id: str,
        user_data_dir: str | None = None,
    ) -> dict[str, Any]:
        result = self._call_tool(
            profile_name=profile_name,
            system=system,
            user_data_dir=user_data_dir,
            name="take_snapshot",
            arguments={"pageId": _parse_page_id(target_id)},
        )
        snapshot = _extract_structured_content(result).get("snapshot")
        if not isinstance(snapshot, dict):
            raise BrowserValidationError("Chrome MCP snapshot response did not include structured data.")
        return dict(snapshot)

    def take_screenshot(
        self,
        *,
        profile_name: str,
        system: BrowserSystemConfig,
        target_id: str,
        user_data_dir: str | None = None,
        uid: str | None = None,
        full_page: bool = False,
        image_format: str = "png",
    ) -> bytes:
        with tempfile.TemporaryDirectory(prefix="crxzipple-browser-mcp-") as tempdir:
            file_path = Path(tempdir) / f"screenshot.{image_format}"
            arguments: dict[str, Any] = {
                "pageId": _parse_page_id(target_id),
                "filePath": str(file_path),
                "format": image_format,
            }
            if uid:
                arguments["uid"] = uid
            if full_page:
                arguments["fullPage"] = True
            self._call_tool(
                profile_name=profile_name,
                system=system,
                user_data_dir=user_data_dir,
                name="take_screenshot",
                arguments=arguments,
            )
            return file_path.read_bytes()

    def click_element(
        self,
        *,
        profile_name: str,
        system: BrowserSystemConfig,
        target_id: str,
        uid: str,
        user_data_dir: str | None = None,
        double_click: bool = False,
    ) -> None:
        arguments: dict[str, Any] = {
            "pageId": _parse_page_id(target_id),
            "uid": uid,
        }
        if double_click:
            arguments["dblClick"] = True
        self._call_tool(
            profile_name=profile_name,
            system=system,
            user_data_dir=user_data_dir,
            name="click",
            arguments=arguments,
        )

    def fill_element(
        self,
        *,
        profile_name: str,
        system: BrowserSystemConfig,
        target_id: str,
        uid: str,
        value: str,
        user_data_dir: str | None = None,
    ) -> None:
        self._call_tool(
            profile_name=profile_name,
            system=system,
            user_data_dir=user_data_dir,
            name="fill",
            arguments={
                "pageId": _parse_page_id(target_id),
                "uid": uid,
                "value": value,
            },
        )

    def upload_file(
        self,
        *,
        profile_name: str,
        system: BrowserSystemConfig,
        target_id: str,
        uid: str,
        file_path: str,
        user_data_dir: str | None = None,
    ) -> None:
        self._call_tool(
            profile_name=profile_name,
            system=system,
            user_data_dir=user_data_dir,
            name="upload_file",
            arguments={
                "pageId": _parse_page_id(target_id),
                "uid": uid,
                "filePath": file_path,
            },
        )

    def hover_element(
        self,
        *,
        profile_name: str,
        system: BrowserSystemConfig,
        target_id: str,
        uid: str,
        user_data_dir: str | None = None,
    ) -> None:
        self._call_tool(
            profile_name=profile_name,
            system=system,
            user_data_dir=user_data_dir,
            name="hover",
            arguments={
                "pageId": _parse_page_id(target_id),
                "uid": uid,
            },
        )

    def drag_element(
        self,
        *,
        profile_name: str,
        system: BrowserSystemConfig,
        target_id: str,
        from_uid: str,
        to_uid: str,
        user_data_dir: str | None = None,
    ) -> None:
        self._call_tool(
            profile_name=profile_name,
            system=system,
            user_data_dir=user_data_dir,
            name="drag",
            arguments={
                "pageId": _parse_page_id(target_id),
                "from_uid": from_uid,
                "to_uid": to_uid,
            },
        )

    def press_key(
        self,
        *,
        profile_name: str,
        system: BrowserSystemConfig,
        target_id: str,
        key: str,
        user_data_dir: str | None = None,
    ) -> None:
        self._call_tool(
            profile_name=profile_name,
            system=system,
            user_data_dir=user_data_dir,
            name="press_key",
            arguments={
                "pageId": _parse_page_id(target_id),
                "key": key,
            },
        )

    def handle_dialog(
        self,
        *,
        profile_name: str,
        system: BrowserSystemConfig,
        target_id: str,
        action: str,
        prompt_text: str | None = None,
        user_data_dir: str | None = None,
    ) -> None:
        arguments: dict[str, Any] = {
            "pageId": _parse_page_id(target_id),
            "action": action,
        }
        if prompt_text is not None:
            arguments["promptText"] = prompt_text
        self._call_tool(
            profile_name=profile_name,
            system=system,
            user_data_dir=user_data_dir,
            name="handle_dialog",
            arguments=arguments,
        )

    def evaluate_script(
        self,
        *,
        profile_name: str,
        system: BrowserSystemConfig,
        target_id: str,
        fn: str,
        user_data_dir: str | None = None,
        args: list[str] | None = None,
    ) -> Any:
        arguments: dict[str, Any] = {
            "pageId": _parse_page_id(target_id),
            "function": fn,
        }
        if args:
            arguments["args"] = list(args)
        result = self._call_tool(
            profile_name=profile_name,
            system=system,
            user_data_dir=user_data_dir,
            name="evaluate_script",
            arguments=arguments,
        )
        return _extract_json_message(result)

    def wait_for_text(
        self,
        *,
        profile_name: str,
        system: BrowserSystemConfig,
        target_id: str,
        text: list[str],
        user_data_dir: str | None = None,
        timeout_ms: int | None = None,
    ) -> None:
        arguments: dict[str, Any] = {
            "pageId": _parse_page_id(target_id),
            "text": list(text),
        }
        if timeout_ms is not None:
            arguments["timeout"] = timeout_ms
        self._call_tool(
            profile_name=profile_name,
            system=system,
            user_data_dir=user_data_dir,
            name="wait_for",
            arguments=arguments,
        )

    def _client(
        self,
        *,
        profile_name: str,
        system: BrowserSystemConfig,
        user_data_dir: str | None,
    ) -> Any:
        normalized_profile = profile_name.strip().lower()
        normalized_user_data_dir = _normalize_user_data_dir(user_data_dir)
        cache_key = (normalized_profile, normalized_user_data_dir)
        with self._lock:
            client = self._clients.get(cache_key)
            if client is None:
                client = self._client_factory(normalized_profile, system, normalized_user_data_dir)
                self._clients[cache_key] = client
        return client

    def _create_client(
        self,
        profile_name: str,
        system: BrowserSystemConfig,
        user_data_dir: str | None,
    ) -> _ChromeMcpStdioClient:
        command = list(system.mcp_command)
        if user_data_dir:
            command.extend(["--userDataDir", user_data_dir])
        client = _ChromeMcpStdioClient(
            profile_name=profile_name,
            command=tuple(command),
            timeout_seconds=system.mcp_timeout_seconds,
        )
        return client

    def _call_tool(
        self,
        *,
        profile_name: str,
        system: BrowserSystemConfig,
        user_data_dir: str | None,
        name: str,
        arguments: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        client = self._client(
            profile_name=profile_name,
            system=system,
            user_data_dir=user_data_dir,
        )
        self._sync_daemon_ready(
            profile_name=profile_name,
            user_data_dir=user_data_dir,
            client=client,
        )
        with self._capability_lease(
            profile_name=profile_name,
            user_data_dir=user_data_dir,
        ):
            try:
                result = client.call_tool(tool_name=name, arguments=dict(arguments or {}))
            except BrowserValidationError as exc:
                self._sync_daemon_failed(
                    profile_name=profile_name,
                    user_data_dir=user_data_dir,
                    last_error=str(exc),
                    client=client,
                )
                raise
            if not isinstance(result, dict):
                error = BrowserValidationError(
                    f"Chrome MCP for profile '{profile_name}' returned an invalid payload for tool '{name}'.",
                )
                self._sync_daemon_failed(
                    profile_name=profile_name,
                    user_data_dir=user_data_dir,
                    last_error=str(error),
                    client=client,
                )
                raise error
            if result.get("isError") is True:
                error = BrowserValidationError(
                    _extract_tool_error_message(result, name=name),
                )
                self._sync_daemon_failed(
                    profile_name=profile_name,
                    user_data_dir=user_data_dir,
                    last_error=str(error),
                    client=client,
                )
                raise error
            self._sync_daemon_ready(
                profile_name=profile_name,
                user_data_dir=user_data_dir,
                client=client,
            )
            return result

    def _daemon_service_key(self, profile_name: str) -> str:
        return f"capability:chrome-mcp:{profile_name.strip().lower()}"

    def _daemon_metadata(
        self,
        *,
        profile_name: str,
        user_data_dir: str | None,
        client: Any | None,
    ) -> dict[str, Any]:
        metadata: dict[str, Any] = {"profile_name": profile_name.strip().lower()}
        normalized_user_data_dir = _normalize_user_data_dir(user_data_dir)
        if normalized_user_data_dir is not None:
            metadata["user_data_dir"] = normalized_user_data_dir
        command = getattr(client, "command", None)
        if isinstance(command, tuple):
            metadata["command"] = list(command)
        client_pid = getattr(client, "pid", None)
        if client_pid is not None:
            metadata["chrome_mcp_pid"] = client_pid
        return metadata

    def _sync_daemon_ready(
        self,
        *,
        profile_name: str,
        user_data_dir: str | None,
        client: Any,
    ) -> None:
        self._daemon_service.report_service_ready(
            service_key=self._daemon_service_key(profile_name),
            pid=getattr(client, "pid", None),
            endpoint="stdio",
            metadata=self._daemon_metadata(
                profile_name=profile_name,
                user_data_dir=user_data_dir,
                client=client,
            ),
        )

    def _sync_daemon_failed(
        self,
        *,
        profile_name: str,
        user_data_dir: str | None,
        last_error: str,
        client: Any | None = None,
    ) -> None:
        self._daemon_service.report_service_failed(
            service_key=self._daemon_service_key(profile_name),
            reason=last_error,
            pid=getattr(client, "pid", None),
            endpoint="stdio",
            metadata=self._daemon_metadata(
                profile_name=profile_name,
                user_data_dir=user_data_dir,
                client=client,
            ),
        )

    def _sync_daemon_stopped(
        self,
        *,
        profile_name: str,
        user_data_dir: str | None,
    ) -> None:
        self._daemon_service.report_service_stopped(
            service_key=self._daemon_service_key(profile_name),
            clear_metadata_keys=("chrome_mcp_pid",),
            metadata=self._daemon_metadata(
                profile_name=profile_name,
                user_data_dir=user_data_dir,
                client=None,
            ),
        )

    def _lease_owner_id(
        self,
        *,
        profile_name: str,
        user_data_dir: str | None,
    ) -> str:
        normalized_profile = profile_name.strip().lower()
        normalized_user_data_dir = _normalize_user_data_dir(user_data_dir)
        if normalized_user_data_dir is None:
            return normalized_profile
        digest = hashlib.sha1(normalized_user_data_dir.encode("utf-8")).hexdigest()[:8]
        return f"{normalized_profile}:{digest}"

    @contextmanager
    def _capability_lease(
        self,
        *,
        profile_name: str,
        user_data_dir: str | None,
    ) -> Any:
        daemon_service = self._daemon_service
        lease: DaemonLease | None = None
        try:
            lease = daemon_service.acquire_lease(
                service_key=self._daemon_service_key(profile_name),
                owner_kind="browser_profile",
                owner_id=self._lease_owner_id(
                    profile_name=profile_name,
                    user_data_dir=user_data_dir,
                ),
                ttl_seconds=60,
                metadata={
                    "profile_name": profile_name.strip().lower(),
                    **(
                        {"user_data_dir": user_data_dir}
                        if user_data_dir is not None
                        else {}
                    ),
                },
            )
        except (DaemonNotFoundError, DaemonValidationError) as exc:
            raise BrowserValidationError(str(exc)) from exc
        try:
            yield
        finally:
            if lease is not None:
                daemon_service.release_lease(lease.id)
