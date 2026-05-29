from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import time
from typing import Any

import requests

from crxzipple.modules.browser.domain import (
    BrowserProfileCapabilities,
    BrowserSystemConfig,
    BrowserValidationError,
    ResolvedBrowserProfile,
)
from crxzipple.modules.daemon import DaemonApplicationService
from crxzipple.shared.access import AccessConsumerRef

from .cdp_urls import append_cdp_path
from .daemon_leases import host_daemon_service_key
from .proxy_adapter import BrowserLocalProxyAdapter


def _remote_allow_origins(*, host: str, port: int) -> str:
    hosts = [host]
    if host in {"127.0.0.1", "localhost", "::1"}:
        hosts = ["127.0.0.1", "localhost", "[::1]"]
    return ",".join(f"http://{item}:{port}" for item in hosts)


def _read_json_response(
    *,
    method: str,
    url: str,
    response: requests.Response,
) -> Any:
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        raise BrowserValidationError(
            f"Browser CDP request {method.upper()} {url} failed with HTTP {response.status_code}.",
        ) from exc
    try:
        return response.json()
    except ValueError as exc:
        raise BrowserValidationError(
            f"Browser CDP request {method.upper()} {url} did not return JSON.",
        ) from exc


@dataclass(slots=True)
class BrowserHostProcessRunner:
    """Launch and hold one managed browser host process for daemon supervision."""

    daemon_service: DaemonApplicationService
    system: BrowserSystemConfig
    profile: ResolvedBrowserProfile
    capabilities: BrowserProfileCapabilities
    profiles_root: str | Path | None = None
    request_timeout_s: float = 5.0
    launch_timeout_s: float = 10.0
    launch_poll_interval_s: float = 0.1
    popen: Any = field(default=subprocess.Popen, repr=False)
    list_processes: Any = field(default=None, repr=False)
    credential_provider: Any | None = field(default=None, repr=False)
    proxy_adapter_factory: Any = field(default=BrowserLocalProxyAdapter, repr=False)
    proxy_egress_check_url: str | None = None
    sleep: Any = field(default=time.sleep, repr=False)
    monotonic: Any = field(default=time.monotonic, repr=False)
    _http: requests.Session = field(default_factory=requests.Session, init=False, repr=False)
    _process: Any | None = field(default=None, init=False, repr=False)
    _proxy_adapter: Any | None = field(default=None, init=False, repr=False)
    _proxy_egress: dict[str, Any] | None = field(default=None, init=False, repr=False)
    _reported_ready: bool = field(default=False, init=False, repr=False)

    def __post_init__(self) -> None:
        self._http.trust_env = False
        if self.list_processes is None:
            object.__setattr__(self, "list_processes", self._default_list_processes)

    def start(self) -> str:
        if self.capabilities.mode != "local-managed" or not self.capabilities.can_launch:
            raise BrowserValidationError(
                f"Browser profile '{self.profile.name}' is not a launchable managed profile.",
            )
        adopted = self._adopt_existing_process()
        if adopted is not None:
            return adopted
        conflict = self._find_conflicting_process()
        if conflict is not None:
            reason = (
                "CDP port is occupied by a browser process that does not match the "
                "configured managed profile."
            )
            self._report_failed(
                reason=reason,
                metadata={
                    "conflict_pid": conflict.get("pid"),
                },
            )
            raise BrowserValidationError(reason)
        process = self._ensure_process()
        endpoint = self._wait_until_ready(process)
        self.daemon_service.report_service_ready(
            service_key=host_daemon_service_key(profile_name=self.profile.name),
            pid=getattr(process, "pid", None),
            endpoint=endpoint,
            metadata=self._daemon_metadata(
                pid=getattr(process, "pid", None),
                adopted=False,
            ),
        )
        self._reported_ready = True
        return endpoint

    def healthcheck(self) -> str:
        endpoint = self._request_cdp_version()
        self.daemon_service.report_service_ready(
            service_key=host_daemon_service_key(profile_name=self.profile.name),
            pid=getattr(self._process, "pid", None),
            endpoint=endpoint,
            metadata=self._daemon_metadata(
                pid=getattr(self._process, "pid", None),
                adopted=False if self._process is not None else None,
            ),
        )
        self._reported_ready = True
        return endpoint

    def close(self) -> None:
        process = self._process
        self._process = None
        if process is not None:
            self._terminate_process(process)
        if self._reported_ready:
            self.daemon_service.report_service_stopped(
                service_key=host_daemon_service_key(profile_name=self.profile.name),
                clear_metadata_keys=(
                    "browser_pid",
                    "proxy_adapter",
                    "proxy_upstream",
                    "proxy_upstream_scheme",
                    "proxy_upstream_host",
                    "proxy_upstream_port",
                    "proxy_local_url",
                    "proxy_egress",
                    "proxy_egress_status",
                    "proxy_egress_ip",
                ),
            )
        self._close_proxy_adapter()
        self._http.close()

    def _ensure_process(self) -> Any:
        if self._process is not None and getattr(self._process, "poll", lambda: None)() is None:
            return self._process
        try:
            command = self._launch_command()
        except BrowserValidationError as exc:
            self._report_failed(reason=str(exc))
            self._close_proxy_adapter()
            raise
        try:
            self._process = self.popen(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
            )
        except Exception as exc:  # noqa: BLE001
            self._report_failed(
                reason=f"Managed browser host could not be launched: {exc}",
            )
            self._close_proxy_adapter()
            raise BrowserValidationError(
                f"Managed browser host could not be launched: {exc}",
            ) from exc
        return self._process

    def _wait_until_ready(self, process: Any) -> str:
        deadline = self.monotonic() + max(self.launch_timeout_s, self.launch_poll_interval_s)
        last_error: BrowserValidationError | None = None
        while True:
            try:
                return self._request_cdp_version()
            except BrowserValidationError as exc:
                last_error = exc
            poll_result = getattr(process, "poll", lambda: None)()
            if poll_result is not None:
                reason = "Managed browser host exited before CDP became available."
                self._report_failed(
                    reason=reason,
                    pid=getattr(process, "pid", None),
                )
                self._close_proxy_adapter()
                raise BrowserValidationError(reason) from last_error
            if self.monotonic() >= deadline:
                self._terminate_process(process)
                reason = (
                    f"{last_error} Managed browser host did not expose CDP before timeout."
                    if last_error is not None
                    else "Managed browser host did not expose CDP before timeout."
                )
                self._report_failed(
                    reason=reason,
                    pid=getattr(process, "pid", None),
                )
                self._close_proxy_adapter()
                raise BrowserValidationError(reason) from last_error
            self.sleep(self.launch_poll_interval_s)

    def _request_cdp_version(self) -> str:
        endpoint = self._server_url()
        request_url = append_cdp_path(endpoint, "/json/version")
        try:
            response = self._http.get(request_url, timeout=self.request_timeout_s)
        except requests.RequestException as exc:
            raise BrowserValidationError(
                f"Browser CDP request GET {request_url} failed: {exc}",
            ) from exc
        payload = _read_json_response(method="get", url=request_url, response=response)
        if not isinstance(payload, dict):
            raise BrowserValidationError("Browser CDP version endpoint returned an invalid payload.")
        return endpoint

    def _launch_command(self) -> list[str]:
        cdp_port = self.profile.cdp_port
        if cdp_port is None:
            raise BrowserValidationError(
                "Managed browser host launch requires a resolved cdp_port.",
            )
        command = [
            self._resolve_executable_path(),
            f"--remote-debugging-address={self.system.cdp_host}",
            f"--remote-debugging-port={cdp_port}",
            f"--remote-allow-origins={_remote_allow_origins(host=self.system.cdp_host, port=cdp_port)}",
            f"--user-data-dir={self._resolve_user_data_dir()}",
            "--no-first-run",
            "--no-default-browser-check",
        ]
        if self.profile.profile_directory is not None:
            command.append(f"--profile-directory={self.profile.profile_directory}")
        if self.system.headless:
            command.append("--headless=new")
        if self.system.no_sandbox:
            command.append("--no-sandbox")
        proxy_server = self._launch_proxy_server()
        if proxy_server is not None:
            command.append(f"--proxy-server={proxy_server}")
            if self.profile.proxy_bypass_list:
                command.append(f"--proxy-bypass-list={';'.join(self.profile.proxy_bypass_list)}")
        return command

    def _launch_proxy_server(self) -> str | None:
        if self.profile.proxy_mode == "static":
            return self.profile.proxy_server
        if self.profile.proxy_mode != "access_binding":
            return None
        adapter = self._ensure_proxy_adapter()
        local_url = adapter.start()
        self._proxy_egress = self._check_proxy_egress(adapter)
        return local_url

    def _ensure_proxy_adapter(self) -> Any:
        if self._proxy_adapter is not None:
            return self._proxy_adapter
        if not self.profile.proxy_server:
            raise BrowserValidationError(
                "proxy_server is required when proxy_mode is access_binding.",
            )
        if not self.profile.proxy_binding_id:
            raise BrowserValidationError(
                "proxy_binding_id is required when proxy_mode is access_binding.",
            )
        resolve = getattr(self.credential_provider, "resolve_credential", None)
        if not callable(resolve):
            raise BrowserValidationError(
                "Browser proxy access_binding requires an Access credential provider.",
            )
        try:
            credential = resolve(
                self.profile.proxy_binding_id,
                expected_kind=self.profile.proxy_credential_kind,
                consumer=AccessConsumerRef(
                    consumer_id=f"browser.profile:{self.profile.name}:proxy",
                    module="browser",
                    component="profile_proxy",
                    runtime_ref=self.profile.name,
                ),
            )
        except TypeError:
            credential = resolve(
                self.profile.proxy_binding_id,
                expected_kind=self.profile.proxy_credential_kind,
            )
        adapter = self.proxy_adapter_factory(
            upstream_proxy_url=self.profile.proxy_server,
            credential=str(credential),
            credential_kind=self.profile.proxy_credential_kind,
        )
        self._proxy_adapter = adapter
        return adapter

    def _check_proxy_egress(self, adapter: Any) -> dict[str, Any]:
        if not self.proxy_egress_check_url:
            return {"status": "not_configured"}
        check = getattr(adapter, "check_egress", None)
        if not callable(check):
            return {"status": "unsupported", "url": self.proxy_egress_check_url}
        try:
            result = check(self.proxy_egress_check_url)
        except Exception as exc:  # noqa: BLE001
            return {
                "status": "failed",
                "reason": str(exc),
                "url": self.proxy_egress_check_url,
            }
        return result if isinstance(result, dict) else {"status": "unknown"}

    def _close_proxy_adapter(self) -> None:
        adapter = self._proxy_adapter
        self._proxy_adapter = None
        self._proxy_egress = None
        close = getattr(adapter, "close", None)
        if callable(close):
            try:
                close()
            except Exception:  # noqa: BLE001
                pass

    def _resolve_executable_path(self) -> str:
        configured = self.system.executable_path
        if configured is not None:
            path = Path(configured).expanduser()
            if not path.is_file():
                raise BrowserValidationError(
                    f"Configured browser executable does not exist: {path}",
                )
            return str(path.resolve())

        candidates = [
            shutil.which("google-chrome"),
            shutil.which("chromium"),
            shutil.which("chromium-browser"),
            shutil.which("microsoft-edge"),
            shutil.which("msedge"),
            shutil.which("brave-browser"),
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
            "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
            "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
        ]
        for candidate in candidates:
            if not candidate:
                continue
            path = Path(candidate).expanduser()
            if path.is_file():
                return str(path.resolve())
        raise BrowserValidationError(
            "No Chromium-compatible browser executable was found. Set browser.executable_path.",
        )

    def _resolve_user_data_dir(self) -> str:
        configured = self.profile.user_data_dir
        if configured is not None:
            path = Path(configured).expanduser()
        elif self.profiles_root is not None:
            path = Path(self.profiles_root).expanduser().resolve() / self.profile.name / "userdata"
        else:
            raise BrowserValidationError(
                "Managed browser host launch requires a user_data_dir or profiles_root.",
            )
        path.mkdir(parents=True, exist_ok=True)
        return str(path.resolve())

    def _server_url(self) -> str:
        if self.profile.cdp_url is not None:
            return self.profile.cdp_url
        if self.profile.cdp_port is None:
            raise BrowserValidationError(
                "Managed browser host launch requires a resolved CDP endpoint.",
            )
        return f"http://{self.system.cdp_host}:{self.profile.cdp_port}"

    def _daemon_metadata(
        self,
        *,
        pid: int | None = None,
        adopted: bool | None = None,
    ) -> dict[str, Any]:
        user_data_dir = self._try_resolve_user_data_dir()
        metadata: dict[str, Any] = {
            "profile_name": self.profile.name,
            "mode": self.capabilities.mode,
            "server_url": self._server_url(),
            "launch_fingerprint": self._launch_fingerprint(user_data_dir=user_data_dir),
        }
        if user_data_dir is not None:
            metadata["user_data_dir"] = user_data_dir
        if self.profile.cdp_url is not None:
            metadata["cdp_url"] = self.profile.cdp_url
        if self.profile.cdp_port is not None:
            metadata["cdp_port"] = self.profile.cdp_port
        if self.profile.profile_directory is not None:
            metadata["profile_directory"] = self.profile.profile_directory
        if self.profile.proxy_mode != "none":
            metadata["proxy_mode"] = self.profile.proxy_mode
        if self.profile.proxy_mode == "static" and self.profile.proxy_server is not None:
            metadata["proxy_server"] = self.profile.proxy_server
        if self.profile.proxy_mode == "access_binding":
            if self.profile.proxy_binding_id is not None:
                metadata["proxy_binding_id"] = self.profile.proxy_binding_id
            metadata["proxy_credential_kind"] = self.profile.proxy_credential_kind
            proxy_adapter_metadata = self._proxy_adapter_metadata()
            if proxy_adapter_metadata:
                metadata.update(proxy_adapter_metadata)
            proxy_egress = self._proxy_egress
            if proxy_egress is not None:
                metadata["proxy_egress"] = dict(proxy_egress)
                metadata["proxy_egress_status"] = str(proxy_egress.get("status") or "unknown")
                if proxy_egress.get("ip"):
                    metadata["proxy_egress_ip"] = str(proxy_egress["ip"])
        if pid is not None:
            metadata["browser_pid"] = pid
        if adopted is not None:
            metadata["adopted"] = adopted
        return metadata

    def _adopt_existing_process(self) -> str | None:
        matching_process = self._find_matching_managed_process()
        if matching_process is None:
            return None
        try:
            endpoint = self._request_cdp_version()
        except BrowserValidationError as exc:
            self._report_failed(
                reason=f"Matching managed browser process did not expose CDP: {exc}",
                pid=int(matching_process["pid"]),
                metadata={"adopted": False},
            )
            raise BrowserValidationError(
                "Matching managed browser process did not expose CDP.",
            ) from exc
        self.daemon_service.report_service_ready(
            service_key=host_daemon_service_key(profile_name=self.profile.name),
            pid=int(matching_process["pid"]),
            endpoint=endpoint,
            metadata=self._daemon_metadata(
                pid=int(matching_process["pid"]),
                adopted=True,
            ),
        )
        self._reported_ready = True
        return endpoint

    def _find_matching_managed_process(self) -> dict[str, Any] | None:
        if self.profile.proxy_mode == "access_binding":
            return None
        cdp_port = self.profile.cdp_port
        user_data_dir = self._try_resolve_user_data_dir()
        if cdp_port is None or user_data_dir is None:
            return None
        expected_headless = bool(self.system.headless)
        expected_origins = f"--remote-allow-origins={_remote_allow_origins(host=self.system.cdp_host, port=cdp_port)}"
        for item in self.list_processes():
            pid = item.get("pid")
            command = item.get("command")
            if not isinstance(pid, int) or pid < 1:
                continue
            if not isinstance(command, str) or not command.strip():
                continue
            if f"--remote-debugging-port={cdp_port}" not in command:
                continue
            if f"--user-data-dir={user_data_dir}" not in command:
                continue
            if expected_origins not in command:
                continue
            if ("--headless" in command) != expected_headless:
                continue
            if (
                self.profile.profile_directory is not None
                and f"--profile-directory={self.profile.profile_directory}" not in command
            ):
                continue
            return {
                "pid": pid,
                "command": command.strip(),
            }
        return None

    def _find_conflicting_process(self) -> dict[str, Any] | None:
        cdp_port = self.profile.cdp_port
        if cdp_port is None:
            return None
        matching = self._find_matching_managed_process()
        if matching is not None:
            return None
        for item in self.list_processes():
            pid = item.get("pid")
            command = item.get("command")
            if not isinstance(pid, int) or pid < 1:
                continue
            if not isinstance(command, str) or not command.strip():
                continue
            if f"--remote-debugging-port={cdp_port}" not in command:
                continue
            return {
                "pid": pid,
                "command": command.strip(),
            }
        return None

    def _report_failed(
        self,
        *,
        reason: str,
        pid: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.daemon_service.report_service_failed(
            service_key=host_daemon_service_key(profile_name=self.profile.name),
            reason=reason,
            pid=pid,
            metadata={
                **self._daemon_metadata(pid=pid),
                **(dict(metadata) if metadata else {}),
            },
        )

    def _launch_fingerprint(self, *, user_data_dir: str | None) -> str:
        try:
            executable_path = self._resolve_executable_path()
        except BrowserValidationError:
            executable_path = self.system.executable_path
        payload = {
            "cdp_host": self.system.cdp_host,
            "cdp_port": self.profile.cdp_port,
            "executable_path": executable_path,
            "headless": self.system.headless,
            "no_sandbox": self.system.no_sandbox,
            "profile_directory": self.profile.profile_directory,
            "proxy_bypass_list": list(self.profile.proxy_bypass_list),
            "proxy_mode": self.profile.proxy_mode,
            "proxy_server": self.profile.proxy_server,
            "proxy_binding_id": self.profile.proxy_binding_id,
            "proxy_credential_kind": self.profile.proxy_credential_kind,
            "user_data_dir": user_data_dir,
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return f"sha256:{hashlib.sha256(encoded.encode('utf-8')).hexdigest()}"

    def _try_resolve_user_data_dir(self) -> str | None:
        try:
            return self._resolve_user_data_dir()
        except BrowserValidationError:
            return None

    @staticmethod
    def _terminate_process(process: Any) -> None:
        if getattr(process, "poll", lambda: None)() is not None:
            return
        try:
            process.terminate()
            process.wait(timeout=2)
            return
        except Exception:  # noqa: BLE001
            pass
        try:
            process.kill()
            process.wait(timeout=2)
        except Exception:  # noqa: BLE001
            pass

    @staticmethod
    def _default_list_processes() -> list[dict[str, Any]]:
        try:
            output = subprocess.check_output(
                ["ps", "-axo", "pid=,command="],
                text=True,
            )
        except Exception:  # noqa: BLE001
            return []
        resolved: list[dict[str, Any]] = []
        for line in output.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            pid_text, _, command = stripped.partition(" ")
            try:
                pid = int(pid_text)
            except ValueError:
                continue
            resolved.append({"pid": pid, "command": command.strip()})
        return resolved

    def _proxy_adapter_metadata(self) -> dict[str, Any]:
        adapter = self._proxy_adapter
        metadata = getattr(adapter, "metadata", None)
        if not callable(metadata):
            return {}
        try:
            payload = metadata()
        except Exception:  # noqa: BLE001
            return {}
        return dict(payload) if isinstance(payload, dict) else {}
