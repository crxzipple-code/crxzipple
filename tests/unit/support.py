from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import threading
import tempfile
from dataclasses import replace
from urllib.parse import parse_qs, urlparse

from crxzipple.bootstrap import AppContainer, build_container
from crxzipple.core.config import Settings, load_settings
from crxzipple.core.db import create_schema


class SqliteTestHarness:
    def __init__(self) -> None:
        self._tempdir = tempfile.TemporaryDirectory()
        database_path = Path(self._tempdir.name) / "test.db"
        self.authorization_runtime_policy_path = str(
            Path(self._tempdir.name) / "authorization_runtime.yaml",
        )
        self.database_url = f"sqlite:///{database_path}"
        self._containers: list[AppContainer] = []

    def initialize_schema(self, *, settings: Settings | None = None) -> None:
        resolved_settings = self._resolved_settings(settings)
        container = build_container(
            settings=resolved_settings,
            database_url=self.database_url,
        )
        create_schema(container.engine)
        container.close()

    def build_container(self, *, settings: Settings | None = None) -> AppContainer:
        resolved_settings = self._resolved_settings(settings)
        container = build_container(
            settings=resolved_settings,
            database_url=self.database_url,
        )
        create_schema(container.engine)
        self._containers.append(container)
        return container

    def _resolved_settings(self, settings: Settings | None) -> Settings:
        resolved = settings or load_settings()
        return replace(
            resolved,
            authorization_runtime_policy_path=self.authorization_runtime_policy_path,
        )

    def close(self) -> None:
        while self._containers:
            container = self._containers.pop()
            container.close()
        self._tempdir.cleanup()


def openapi_fixture_path(name: str) -> str:
    return str(Path(__file__).with_name("fixtures") / name)


def fixture_path(name: str) -> str:
    return str(Path(__file__).with_name("fixtures") / name)


class SampleApiServer:
    def __init__(self) -> None:
        self._server = ThreadingHTTPServer(
            ("127.0.0.1", 0),
            _build_sample_api_handler(),
        )
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            name="sample-api-server",
            daemon=True,
        )

    @property
    def base_url(self) -> str:
        host, port = self._server.server_address
        return f"http://{host}:{port}"

    def start(self) -> None:
        self._thread.start()

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=2)


class SampleLlmApiServer:
    def __init__(self) -> None:
        self._server = ThreadingHTTPServer(
            ("127.0.0.1", 0),
            _build_sample_llm_api_handler(),
        )
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            name="sample-llm-api-server",
            daemon=True,
        )

    @property
    def base_url(self) -> str:
        host, port = self._server.server_address
        return f"http://{host}:{port}"

    def start(self) -> None:
        self._thread.start()

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=2)


def _build_sample_api_handler() -> type[BaseHTTPRequestHandler]:
    class SampleApiHandler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path.startswith("/echo/"):
                message = parsed.path.removeprefix("/echo/")
                query = parse_qs(parsed.query)
                if query.get("api_key", [""])[0] != "sample-api-key":
                    self._write_json(401, {"detail": "invalid api key"})
                    return
                uppercase = query.get("uppercase", ["false"])[0].lower() == "true"
                payload = {
                    "message": message.upper() if uppercase else message,
                    "uppercase": uppercase,
                }
                self._write_json(200, payload)
                return

            if parsed.path == "/search":
                if self.headers.get("Authorization") != "Bearer sample-bearer-token":
                    self._write_json(401, {"detail": "missing bearer token"})
                    return
                length = int(self.headers.get("Content-Length", "0"))
                body = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
                payload = {
                    "query": body.get("query"),
                    "limit": body.get("limit", 10),
                    "items": [f"result:{body.get('query', '')}"],
                }
                self._write_json(200, payload)
                return

            self._write_json(404, {"detail": "not found"})

        def log_message(self, format: str, *args: object) -> None:
            return

        def _write_json(self, status_code: int, payload: dict[str, object]) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return SampleApiHandler


def _build_sample_llm_api_handler() -> type[BaseHTTPRequestHandler]:
    class SampleLlmApiHandler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path != "/v1/chat/completions":
                self._write_json(404, {"detail": "not found"})
                return

            if self.headers.get("Authorization") != "Bearer sample-compat-token":
                self._write_json(401, {"detail": "invalid bearer token"})
                return

            length = int(self.headers.get("Content-Length", "0"))
            payload = (
                json.loads(self.rfile.read(length).decode("utf-8"))
                if length
                else {}
            )
            messages = payload.get("messages")
            if not isinstance(messages, list) or not messages:
                self._write_json(400, {"detail": "messages are required"})
                return

            tool_calls: list[dict[str, object]] = []
            tools = payload.get("tools")
            if isinstance(tools, list) and tools:
                first_tool = tools[0]
                function_payload = (
                    first_tool.get("function")
                    if isinstance(first_tool, dict)
                    else None
                )
                tool_name = (
                    function_payload.get("name")
                    if isinstance(function_payload, dict)
                    else "search_docs"
                )
                tool_calls.append(
                    {
                        "id": "call_sample_1",
                        "type": "function",
                        "function": {
                            "name": tool_name,
                            "arguments": json.dumps({"query": "ddd"}),
                        },
                    },
                )

            self._write_json(
                200,
                {
                    "id": "chatcmpl_sample_1",
                    "model": payload.get("model", "sample-model"),
                    "choices": [
                        {
                            "finish_reason": "tool_calls" if tool_calls else "stop",
                            "message": {
                                "role": "assistant",
                                "content": "hello from sample llm",
                                "tool_calls": tool_calls,
                            },
                        },
                    ],
                    "usage": {
                        "prompt_tokens": 13,
                        "completion_tokens": 8,
                        "total_tokens": 21,
                    },
                },
            )

        def log_message(self, format: str, *args: object) -> None:
            return

        def _write_json(self, status_code: int, payload: dict[str, object]) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return SampleLlmApiHandler
