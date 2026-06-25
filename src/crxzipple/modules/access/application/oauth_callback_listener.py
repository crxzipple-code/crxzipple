from __future__ import annotations

from datetime import datetime
from html import escape as html_escape
from http.server import BaseHTTPRequestHandler, HTTPServer
import subprocess
import sys
from threading import Lock, Thread, Timer
from typing import Any, Protocol
from urllib.parse import parse_qs, urlparse
import webbrowser

from .oauth_contracts import AccessOAuthRepository, JsonObject


CODEX_OAUTH_CALLBACK_URL = "http://localhost:1455/auth/callback"
CODEX_OAUTH_CALLBACK_HOST = "localhost"
CODEX_OAUTH_CALLBACK_PORT = 1455
CODEX_OAUTH_CALLBACK_PATH = "/auth/callback"
CODEX_OAUTH_CALLBACK_TIMEOUT_SECONDS = 10 * 60
_CODEX_OAUTH_CALLBACK_LOCK = Lock()
_CODEX_OAUTH_CALLBACK_ACTIVE: dict[str, Any] | None = None


class CodexOAuthCallbackCompletionService(Protocol):
    repository: AccessOAuthRepository

    def complete_browser_setup(
        self,
        *,
        session_id: str,
        code: str,
        state: str | None = None,
        account_id: str | None = None,
        credential_binding_id: str | None = None,
    ) -> object: ...

    def _now(self) -> datetime: ...


def start_codex_oauth_callback_listener(
    *,
    service: CodexOAuthCallbackCompletionService,
    session_id: str,
    account_id: str,
    credential_binding_id: str,
    timeout_seconds: int,
) -> JsonObject:
    stop_active_codex_oauth_callback_listener(
        service=service,
        reason="OpenAI Codex OAuth callback listener was superseded by a newer login.",
        superseded_by_session_id=session_id,
    )
    completed = {"value": False}

    class CodexOAuthHTTPServer(HTTPServer):
        allow_reuse_address = True

    class CodexCallbackHandler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            return

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path != CODEX_OAUTH_CALLBACK_PATH:
                self.send_error(404, "Not found")
                return

            values = parse_qs(parsed.query)
            code = _optional_text((values.get("code") or [""])[0])
            state = _optional_text((values.get("state") or [""])[0])
            if code is None:
                self._send_html(
                    400,
                    "Authentication failed",
                    "OpenAI did not return an authorization code.",
                )
                _shutdown_callback_server()
                return

            try:
                service.complete_browser_setup(
                    session_id=session_id,
                    code=code,
                    state=state,
                    account_id=account_id,
                    credential_binding_id=credential_binding_id,
                )
            except Exception as exc:
                _mark_setup_session("failed", {"error": str(exc)})
                self._send_html(500, "Authentication failed", str(exc))
                _shutdown_callback_server()
                return

            self._send_html(
                200,
                "Authentication successful",
                "OpenAI Codex OAuth is connected. You can return to CRXZIPPLE.",
            )
            _shutdown_callback_server()

        def _send_html(self, status: int, title: str, message: str) -> None:
            body = oauth_callback_html(title, message).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    try:
        server = CodexOAuthHTTPServer(
            (CODEX_OAUTH_CALLBACK_HOST, CODEX_OAUTH_CALLBACK_PORT),
            CodexCallbackHandler,
        )
    except OSError as exc:
        raise ValueError(
            "OpenAI Codex OAuth callback listener could not bind "
            f"{CODEX_OAUTH_CALLBACK_URL}: {exc}",
        ) from exc

    def _mark_setup_session(status: str, metadata: JsonObject) -> None:
        try:
            service.repository.complete_setup_session(
                session_id,
                status=status,
                metadata=metadata,
                completed_at=service._now(),
            )
        except Exception:
            return

    def _shutdown_callback_server() -> None:
        if completed["value"]:
            return
        completed["value"] = True
        clear_active_codex_oauth_callback_listener(
            session_id=session_id,
            completed=completed,
        )
        Thread(target=server.shutdown, daemon=True).start()

    def _expire_callback_server() -> None:
        if completed["value"]:
            return
        _mark_setup_session(
            "expired",
            {"error": "OpenAI Codex OAuth callback timed out."},
        )
        _shutdown_callback_server()

    def _serve() -> None:
        timer = Timer(timeout_seconds, _expire_callback_server)
        timer.daemon = True
        timer.start()
        try:
            server.serve_forever(poll_interval=0.2)
        finally:
            timer.cancel()
            server.server_close()

    register_active_codex_oauth_callback_listener(
        session_id=session_id,
        server=server,
        completed=completed,
    )
    Thread(target=_serve, name=f"codex-oauth-{session_id}", daemon=True).start()
    return {
        "status": "listening",
        "host": CODEX_OAUTH_CALLBACK_HOST,
        "port": CODEX_OAUTH_CALLBACK_PORT,
        "path": CODEX_OAUTH_CALLBACK_PATH,
        "timeout_seconds": timeout_seconds,
    }


def register_active_codex_oauth_callback_listener(
    *,
    session_id: str,
    server: HTTPServer,
    completed: dict[str, bool],
) -> None:
    global _CODEX_OAUTH_CALLBACK_ACTIVE
    with _CODEX_OAUTH_CALLBACK_LOCK:
        _CODEX_OAUTH_CALLBACK_ACTIVE = {
            "session_id": session_id,
            "server": server,
            "completed": completed,
        }


def clear_active_codex_oauth_callback_listener(
    *,
    session_id: str,
    completed: dict[str, bool],
) -> None:
    global _CODEX_OAUTH_CALLBACK_ACTIVE
    with _CODEX_OAUTH_CALLBACK_LOCK:
        active = _CODEX_OAUTH_CALLBACK_ACTIVE
        if active is None:
            return
        if active.get("session_id") != session_id:
            return
        if active.get("completed") is not completed:
            return
        _CODEX_OAUTH_CALLBACK_ACTIVE = None


def stop_active_codex_oauth_callback_listener(
    *,
    service: CodexOAuthCallbackCompletionService,
    reason: str,
    superseded_by_session_id: str | None = None,
) -> None:
    global _CODEX_OAUTH_CALLBACK_ACTIVE
    with _CODEX_OAUTH_CALLBACK_LOCK:
        active = _CODEX_OAUTH_CALLBACK_ACTIVE
        _CODEX_OAUTH_CALLBACK_ACTIVE = None
    if active is None:
        return

    completed = active.get("completed")
    if isinstance(completed, dict):
        if completed.get("value"):
            return
        completed["value"] = True

    previous_session_id = _optional_text(active.get("session_id"))
    if previous_session_id is not None:
        metadata: JsonObject = {
            "error": reason,
            "callback_listener": {"status": "superseded"},
        }
        if superseded_by_session_id is not None:
            metadata["superseded_by_session_id"] = superseded_by_session_id
        try:
            service.repository.complete_setup_session(
                previous_session_id,
                status="expired",
                metadata=metadata,
                completed_at=service._now(),
            )
        except Exception:
            pass

    server = active.get("server")
    if isinstance(server, HTTPServer):
        try:
            server.shutdown()
        finally:
            server.server_close()


def oauth_callback_html(title: str, message: str) -> str:
    return (
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\" />"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />"
        f"<title>{html_escape(title)}</title></head><body>"
        f"<p>{html_escape(message)}</p></body></html>"
    )


def open_browser_url(url: str) -> bool:
    try:
        if sys.platform == "darwin":
            subprocess.Popen(
                ("open", url),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return True
        return bool(webbrowser.open_new_tab(url))
    except Exception:
        return False


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None
