from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
from typing import Any

from crxzipple.modules.browser.domain import (
    BrowserExecutionPlan,
    BrowserValidationError,
)

from .daemon_leases import (
    host_daemon_enabled,
    host_daemon_service_key,
)
from .engines_cdp_io import (
    has_expected_remote_allow_origins,
    push_cdp_base,
)


def resolve_executable_path(*, plan: BrowserExecutionPlan) -> str:
    configured = plan.system.executable_path
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


def resolve_user_data_dir(
    *,
    plan: BrowserExecutionPlan,
    profiles_root: str | Path | None,
) -> str:
    configured = plan.profile.user_data_dir
    if configured is not None:
        path = Path(configured).expanduser()
    elif profiles_root is not None:
        path = (
            Path(profiles_root).expanduser().resolve()
            / plan.profile.name
            / "userdata"
        )
    else:
        raise BrowserValidationError(
            "Local managed browser launch requires a user_data_dir or profiles_root.",
        )
    path.mkdir(parents=True, exist_ok=True)
    return str(path.resolve())


def try_resolve_user_data_dir(
    *,
    plan: BrowserExecutionPlan,
    profiles_root: str | Path | None,
) -> str | None:
    try:
        return resolve_user_data_dir(plan=plan, profiles_root=profiles_root)
    except BrowserValidationError:
        return None


def find_matching_managed_process(
    *,
    plan: BrowserExecutionPlan,
    list_processes,
    user_data_dir: str | None,
) -> dict[str, Any] | None:
    cdp_port = plan.profile.cdp_port
    if cdp_port is None or user_data_dir is None:
        return None
    for item in list_processes():
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
        if not has_expected_remote_allow_origins(
            command=command,
            host=plan.system.cdp_host,
            port=cdp_port,
        ):
            continue
        return {
            "pid": pid,
            "command": command,
            "headless": "--headless" in command,
        }
    return None


def find_process_for_cdp_port(
    *,
    plan: BrowserExecutionPlan,
    list_processes,
) -> dict[str, Any] | None:
    cdp_port = plan.profile.cdp_port
    if cdp_port is None:
        return None
    for item in list_processes():
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
            "command": command,
            "headless": "--headless" in command,
        }
    return None


def clear_user_data_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    for child in path.iterdir():
        if child.is_dir() and not child.is_symlink():
            shutil.rmtree(child, ignore_errors=True)
        else:
            child.unlink(missing_ok=True)


def default_list_processes() -> list[dict[str, Any]]:
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


def find_process_by_pid(*, list_processes, pid: int) -> dict[str, Any] | None:
    for item in list_processes():
        if item.get("pid") == pid:
            return item
    return None


def host_daemon_cdp_base_urls(
    *,
    daemon_service,
    plan: BrowserExecutionPlan,
) -> tuple[str, ...]:
    if not host_daemon_enabled(plan=plan):
        return ()
    try:
        instances = daemon_service.list_instances(
            service_key=host_daemon_service_key(profile_name=plan.profile.name),
        )
    except Exception:  # noqa: BLE001
        return ()
    endpoints: list[str] = []
    for instance in instances:
        if getattr(instance, "status", "") not in {"ready", "degraded"}:
            continue
        push_cdp_base(endpoints, getattr(instance, "endpoint", None))
        metadata = getattr(instance, "metadata", None)
        if not isinstance(metadata, dict):
            continue
        push_cdp_base(endpoints, metadata.get("server_url"))
        push_cdp_base(endpoints, metadata.get("cdp_url"))
    return tuple(endpoints)


def host_daemon_metadata(
    *,
    plan: BrowserExecutionPlan,
    user_data_dir: str | None,
    pid: int | None = None,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "profile_name": plan.profile.name,
        "mode": plan.capabilities.mode,
    }
    if user_data_dir is not None:
        metadata["user_data_dir"] = user_data_dir
    if plan.profile.cdp_url is not None:
        metadata["cdp_url"] = plan.profile.cdp_url
    if plan.profile.cdp_port is not None:
        metadata["cdp_port"] = plan.profile.cdp_port
    if plan.profile.proxy_mode != "none":
        metadata["proxy_mode"] = plan.profile.proxy_mode
    if plan.profile.proxy_mode == "static" and plan.profile.proxy_server is not None:
        metadata["proxy_server"] = plan.profile.proxy_server
    if plan.profile.proxy_mode == "access_binding":
        if plan.profile.proxy_binding_id is not None:
            metadata["proxy_binding_id"] = plan.profile.proxy_binding_id
        metadata["proxy_credential_kind"] = plan.profile.proxy_credential_kind
    if pid is not None:
        metadata["browser_pid"] = pid
    return metadata


def sync_host_daemon_ready(
    *,
    daemon_service,
    plan: BrowserExecutionPlan,
    pid: int | None,
    endpoint: str | None,
    metadata: dict[str, Any],
) -> None:
    if not host_daemon_enabled(plan=plan):
        return
    daemon_service.report_service_ready(
        service_key=host_daemon_service_key(profile_name=plan.profile.name),
        pid=pid,
        endpoint=endpoint,
        metadata=metadata,
    )


def sync_host_daemon_failed(
    *,
    daemon_service,
    plan: BrowserExecutionPlan,
    reason: str,
    metadata: dict[str, Any],
) -> None:
    if not host_daemon_enabled(plan=plan):
        return
    daemon_service.report_service_failed(
        service_key=host_daemon_service_key(profile_name=plan.profile.name),
        reason=reason,
        metadata=metadata,
    )


def sync_host_daemon_stopped(
    *,
    daemon_service,
    plan: BrowserExecutionPlan,
) -> None:
    if not host_daemon_enabled(plan=plan):
        return
    daemon_service.report_service_stopped(
        service_key=host_daemon_service_key(profile_name=plan.profile.name),
        clear_metadata_keys=("browser_pid",),
    )


def stop_host_daemon_process(
    *,
    daemon_service,
    daemon_manager,
    plan: BrowserExecutionPlan,
) -> None:
    if not host_daemon_enabled(plan=plan):
        return
    service_key = host_daemon_service_key(profile_name=plan.profile.name)
    stop_service = getattr(daemon_manager, "stop_service", None)
    if callable(stop_service):
        try:
            stop_service(service_key)
        except Exception as exc:  # noqa: BLE001
            raise BrowserValidationError(
                f"Failed to stop browser daemon service '{service_key}': {exc}",
            ) from exc
        return
    sync_host_daemon_stopped(daemon_service=daemon_service, plan=plan)


__all__ = [
    "clear_user_data_dir",
    "default_list_processes",
    "find_matching_managed_process",
    "find_process_by_pid",
    "find_process_for_cdp_port",
    "host_daemon_cdp_base_urls",
    "host_daemon_metadata",
    "resolve_executable_path",
    "resolve_user_data_dir",
    "stop_host_daemon_process",
    "sync_host_daemon_failed",
    "sync_host_daemon_ready",
    "sync_host_daemon_stopped",
    "try_resolve_user_data_dir",
]
