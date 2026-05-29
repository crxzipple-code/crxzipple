from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import time
from typing import Any

import requests
import websocket

from crxzipple.modules.daemon import (
    DaemonApplicationService,
)
from crxzipple.modules.browser.domain import (
    BrowserActionFamily,
    BrowserActionResult,
    BrowserExecutionPlan,
    BrowserPageActionCommand,
    BrowserProfileRuntimeState,
    BrowserTab,
    BrowserValidationError,
)

from ..application.ports import BrowserActionEngine, BrowserControlEngine
from .cdp_urls import (
    append_cdp_path,
    build_cdp_json_new_endpoint,
    candidate_cdp_http_bases,
    json_tab_endpoints,
    normalize_cdp_http_base,
    normalize_cdp_ws_url,
)
from .daemon_leases import (
    host_daemon_enabled,
    host_daemon_lease,
    host_daemon_service_key,
)

_METADATA_TABS_KEY = "tabs"
_METADATA_TABS_REFRESHED_AT_KEY = "tabs_refreshed_at"
_METADATA_NEXT_TAB_ID_KEY = "next_tab_id"
_METADATA_ACTIVE_TARGET_KEY = "active_target_id"
_METADATA_CDP_BASE_URL_KEY = "cdp_base_url"
_PAGE_TAB_TYPES = {"page"}
_BACKGROUND_TAB_TYPES = {"background_page", "background"}
_WORKER_TAB_TYPES = {"worker", "service_worker", "shared_worker"}
_TABS_CACHE_FRESHNESS_SECONDS = 2.0


def _copy_tab_payloads(runtime_state: BrowserProfileRuntimeState) -> list[dict[str, Any]]:
    raw = runtime_state.metadata.get(_METADATA_TABS_KEY, [])
    if not isinstance(raw, list):
        return []
    payloads: list[dict[str, Any]] = []
    for item in raw:
        if isinstance(item, dict):
            payloads.append(dict(item))
    return payloads


def _load_tabs(runtime_state: BrowserProfileRuntimeState) -> tuple[BrowserTab, ...]:
    return tuple(
        BrowserTab(
            target_id=str(payload.get("target_id", "")).strip(),
            url=str(payload.get("url", "")).strip(),
            title=str(payload.get("title", "")).strip(),
            type=str(payload.get("type", "page")).strip() or "page",
            ws_url=(
                str(payload["ws_url"])
                if payload.get("ws_url") is not None
                else None
            ),
            json_endpoints=(
                dict(payload["json_endpoints"])
                if isinstance(payload.get("json_endpoints"), dict)
                else None
            ),
        )
        for payload in _copy_tab_payloads(runtime_state)
        if str(payload.get("target_id", "")).strip()
    )


def _store_tabs(
    runtime_state: BrowserProfileRuntimeState,
    tabs: tuple[BrowserTab, ...],
) -> None:
    runtime_state.metadata[_METADATA_TABS_KEY] = [
        {
            "target_id": tab.target_id,
            "url": tab.url,
            "title": tab.title,
            "type": tab.type,
            "ws_url": tab.ws_url,
            "json_endpoints": dict(tab.json_endpoints) if tab.json_endpoints else None,
        }
        for tab in tabs
    ]
    runtime_state.metadata[_METADATA_TABS_REFRESHED_AT_KEY] = time.time()


def _tabs_cache_is_fresh(runtime_state: BrowserProfileRuntimeState) -> bool:
    if not _load_tabs(runtime_state):
        return False
    raw = runtime_state.metadata.get(_METADATA_TABS_REFRESHED_AT_KEY)
    try:
        refreshed_at = float(raw)
    except (TypeError, ValueError):
        return False
    return (time.time() - refreshed_at) <= _TABS_CACHE_FRESHNESS_SECONDS


def _host_generation(
    *,
    base_url: str,
    browser_ref: str | None,
    running_pid: int | None,
) -> str:
    payload = {
        "base_url": str(base_url).strip(),
        "browser_ref": str(browser_ref).strip() if browser_ref else None,
        "running_pid": int(running_pid) if running_pid is not None else None,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _next_tab_id(runtime_state: BrowserProfileRuntimeState, *, prefix: str) -> str:
    current = runtime_state.metadata.get(_METADATA_NEXT_TAB_ID_KEY, 1)
    try:
        numeric = int(current)
    except (TypeError, ValueError):
        numeric = 1
    runtime_state.metadata[_METADATA_NEXT_TAB_ID_KEY] = numeric + 1
    return f"{prefix}-{numeric}"


def _set_active_target(runtime_state: BrowserProfileRuntimeState, target_id: str | None) -> None:
    normalized = target_id.strip() if isinstance(target_id, str) else ""
    runtime_state.metadata[_METADATA_ACTIVE_TARGET_KEY] = normalized or None


def _find_tab(
    runtime_state: BrowserProfileRuntimeState,
    *,
    target_id: str,
) -> BrowserTab:
    for tab in _load_tabs(runtime_state):
        if tab.target_id == target_id:
            return tab
    raise BrowserValidationError(f"Browser tab '{target_id}' was not found.")


def _tab_by_id(*, tabs: tuple[BrowserTab, ...], target_id: str) -> BrowserTab:
    for tab in tabs:
        if tab.target_id == target_id:
            return tab
    raise BrowserValidationError(f"Browser tab '{target_id}' was not found.")


def _canonicalize_opened_tab(
    *,
    opened_tab: BrowserTab,
    live_tabs: tuple[BrowserTab, ...],
) -> BrowserTab:
    if not live_tabs:
        return opened_tab
    for tab in live_tabs:
        if tab.target_id == opened_tab.target_id:
            return tab
    same_ws_url = [
        tab for tab in live_tabs if tab.ws_url and opened_tab.ws_url and tab.ws_url == opened_tab.ws_url
    ]
    if len(same_ws_url) == 1:
        return same_ws_url[0]
    same_url = [
        tab
        for tab in live_tabs
        if str(tab.url or "").strip() and str(tab.url or "").strip() == str(opened_tab.url or "").strip()
    ]
    if same_url:
        return same_url[-1]
    return live_tabs[-1]


def _browser_tab_type(raw_type: object) -> str:
    normalized = str(raw_type or "page").strip().lower()
    if normalized in _PAGE_TAB_TYPES:
        return "page"
    if normalized in _BACKGROUND_TAB_TYPES:
        return "background"
    if normalized in _WORKER_TAB_TYPES:
        return "worker"
    return "other"


def _tab_from_cdp_payload(
    payload: dict[str, Any],
    *,
    include_ws_url: bool,
    include_json_endpoints: bool,
    base_url: str,
) -> BrowserTab:
    target_id = str(payload.get("id", "")).strip()
    return BrowserTab(
        target_id=target_id,
        url=str(payload.get("url", "")).strip(),
        title=str(payload.get("title", "")).strip(),
        type=_browser_tab_type(payload.get("type")),
        ws_url=(
            normalize_cdp_ws_url(
                str(payload.get("webSocketDebuggerUrl", "")).strip(),
                base_url,
            )
            if include_ws_url and payload.get("webSocketDebuggerUrl")
            else None
        ),
        json_endpoints=(
            json_tab_endpoints(base_url, target_id)
            if include_json_endpoints and target_id
            else None
        ),
    )


def _request_error_message(
    *,
    method: str,
    url: str,
    exc: Exception,
) -> str:
    return f"Browser CDP request {method.upper()} {url} failed: {exc}"


def _read_json_response(
    *,
    method: str,
    url: str,
    response: requests.Response,
) -> Any:
    try:
        response.raise_for_status()
    except requests.RequestException as exc:
        raise BrowserValidationError(
            _request_error_message(method=method, url=url, exc=exc),
        ) from exc
    try:
        return response.json()
    except ValueError as exc:
        raise BrowserValidationError(
            f"Browser CDP request {method.upper()} {url} returned non-JSON content.",
        ) from exc


def _send_cdp_command(
    *,
    ws_connect,
    ws_url: str,
    method: str,
    params: dict[str, Any] | None = None,
    timeout_s: float,
) -> None:
    request_id = 1
    try:
        socket = ws_connect(ws_url, timeout=timeout_s)
    except Exception as exc:  # noqa: BLE001
        raise BrowserValidationError(
            f"Browser CDP websocket {ws_url} could not be opened: {exc}",
        ) from exc

    try:
        socket.send(
            json.dumps(
                {
                    "id": request_id,
                    "method": method,
                    "params": dict(params or {}),
                },
            ),
        )
        while True:
            raw_message = socket.recv()
            if not isinstance(raw_message, str):
                continue
            try:
                payload = json.loads(raw_message)
            except ValueError:
                continue
            if not isinstance(payload, dict):
                continue
            if payload.get("id") != request_id:
                continue
            error = payload.get("error")
            if isinstance(error, dict):
                message = str(error.get("message") or method)
                raise BrowserValidationError(
                    f"Browser CDP command '{method}' failed: {message}",
                )
            return
    except BrowserValidationError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise BrowserValidationError(
            f"Browser CDP command '{method}' failed: {exc}",
        ) from exc
    finally:
        try:
            socket.close()
        except Exception:  # noqa: BLE001
            pass


def _remote_allow_origins(*, host: str, port: int) -> str:
    normalized_host = str(host).strip().lower()
    if normalized_host in {"127.0.0.1", "localhost", "::1"}:
        return ",".join(
            (
                f"http://127.0.0.1:{port}",
                f"http://localhost:{port}",
                f"http://[::1]:{port}",
            )
        )
    return f"http://{host}:{port}"


def _has_expected_remote_allow_origins(
    *,
    command: str,
    host: str,
    port: int,
) -> bool:
    expected = f"--remote-allow-origins={_remote_allow_origins(host=host, port=port)}"
    return expected in command


@dataclass(frozen=True, slots=True)
class InMemoryCdpControlEngine(BrowserControlEngine):
    family: str = "cdp-control"

    def ensure_attached(
        self,
        *,
        plan: BrowserExecutionPlan,
        runtime_state: BrowserProfileRuntimeState,
    ) -> BrowserProfileRuntimeState:
        runtime_state.mark_attached(
            browser_ref=f"cdp:{plan.profile.name}",
            running_pid=runtime_state.running_pid or 1,
        )
        runtime_state.metadata.setdefault(_METADATA_TABS_KEY, [])
        runtime_state.metadata.setdefault(_METADATA_NEXT_TAB_ID_KEY, 1)
        runtime_state.metadata.setdefault(_METADATA_ACTIVE_TARGET_KEY, None)
        return runtime_state

    def list_tabs(
        self,
        *,
        plan: BrowserExecutionPlan,
        runtime_state: BrowserProfileRuntimeState,
    ) -> tuple[BrowserTab, ...]:
        del plan
        return _load_tabs(runtime_state)

    def open_tab(
        self,
        *,
        plan: BrowserExecutionPlan,
        runtime_state: BrowserProfileRuntimeState,
        url: str,
    ) -> BrowserTab:
        target_id = _next_tab_id(runtime_state, prefix=plan.profile.name)
        tab = BrowserTab(
            target_id=target_id,
            url=url,
            title=url,
            type="page",
            ws_url=(
                f"ws://127.0.0.1/devtools/page/{target_id}"
                if plan.capabilities.supports_per_tab_ws
                else None
            ),
            json_endpoints=(
                json_tab_endpoints(
                    plan.profile.cdp_url or "http://127.0.0.1",
                    target_id,
                )
                if plan.capabilities.supports_json_tab_endpoints
                else None
            ),
        )
        tabs = _load_tabs(runtime_state) + (tab,)
        _store_tabs(runtime_state, tabs)
        _set_active_target(runtime_state, tab.target_id)
        return tab

    def navigate_tab(
        self,
        *,
        plan: BrowserExecutionPlan,
        runtime_state: BrowserProfileRuntimeState,
        target_id: str,
        url: str,
    ) -> BrowserTab:
        del plan
        tabs = []
        updated: BrowserTab | None = None
        for tab in _load_tabs(runtime_state):
            if tab.target_id == target_id:
                updated = BrowserTab(
                    target_id=tab.target_id,
                    url=url,
                    title=url,
                    type=tab.type,
                    ws_url=tab.ws_url,
                    json_endpoints=tab.json_endpoints,
                )
                tabs.append(updated)
            else:
                tabs.append(tab)
        if updated is None:
            raise BrowserValidationError(f"Browser tab '{target_id}' was not found.")
        _store_tabs(runtime_state, tuple(tabs))
        _set_active_target(runtime_state, updated.target_id)
        return updated

    def focus_tab(
        self,
        *,
        plan: BrowserExecutionPlan,
        runtime_state: BrowserProfileRuntimeState,
        target_id: str,
    ) -> BrowserTab:
        del plan
        tab = _find_tab(runtime_state, target_id=target_id)
        _set_active_target(runtime_state, tab.target_id)
        return tab

    def close_tab(
        self,
        *,
        plan: BrowserExecutionPlan,
        runtime_state: BrowserProfileRuntimeState,
        target_id: str,
    ) -> None:
        del plan
        current_tabs = _load_tabs(runtime_state)
        tabs = tuple(tab for tab in current_tabs if tab.target_id != target_id)
        if len(tabs) == len(current_tabs):
            raise BrowserValidationError(f"Browser tab '{target_id}' was not found.")
        _store_tabs(runtime_state, tabs)
        active_target = runtime_state.metadata.get(_METADATA_ACTIVE_TARGET_KEY)
        if active_target == target_id:
            _set_active_target(runtime_state, tabs[0].target_id if tabs else None)

    def reset_profile(
        self,
        *,
        plan: BrowserExecutionPlan,
        runtime_state: BrowserProfileRuntimeState,
    ) -> None:
        del plan
        runtime_state.metadata.clear()
        runtime_state.remember_target(None)
        runtime_state.mark_closed()

    def stop_profile(
        self,
        *,
        plan: BrowserExecutionPlan,
        runtime_state: BrowserProfileRuntimeState,
    ) -> None:
        del plan
        runtime_state.metadata.clear()
        runtime_state.remember_target(None)
        runtime_state.mark_closed()


@dataclass(slots=True)
class CdpControlEngine(BrowserControlEngine):
    daemon_service: DaemonApplicationService = field(repr=False)
    daemon_manager: Any | None = field(default=None, repr=False)
    family: str = "cdp-control"
    request_timeout_s: float = 5.0
    profiles_root: str | Path | None = None
    ws_connect: Any = field(default=websocket.create_connection, repr=False)
    list_processes: Any = field(default=None, repr=False)
    _http: requests.Session = field(
        default_factory=requests.Session,
        init=False,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        self._http.trust_env = False
        if self.list_processes is None:
            object.__setattr__(self, "list_processes", self._default_list_processes)

    def ensure_attached(
        self,
        *,
        plan: BrowserExecutionPlan,
        runtime_state: BrowserProfileRuntimeState,
    ) -> BrowserProfileRuntimeState:
        previous_running_pid = runtime_state.running_pid
        previous_base_url = str(runtime_state.metadata.get(_METADATA_CDP_BASE_URL_KEY) or "").strip()
        cached_tabs_fresh = _tabs_cache_is_fresh(runtime_state)
        try:
            payload, base_url = self._request_cdp_json(
                plan=plan,
                runtime_state=runtime_state,
                path="/json/version",
            )
        except BrowserValidationError as exc:
            validation_error = exc
            if plan.launch_policy == "launch-if-missing":
                self._sync_host_daemon_failed(
                    plan=plan,
                    reason=str(validation_error),
                )
                raise BrowserValidationError(
                    f"Managed browser host '{self._host_daemon_service_key(profile_name=plan.profile.name)}' "
                    f"is not ready. Start or ensure the daemon service and retry. Original CDP error: {validation_error}",
                ) from validation_error
            else:
                self._sync_host_daemon_failed(
                    plan=plan,
                    reason=str(validation_error),
                )
                raise

        browser_ref = None
        if isinstance(payload, dict):
            raw_browser_ref = payload.get("webSocketDebuggerUrl")
            browser_ref = str(raw_browser_ref).strip() if raw_browser_ref else None
        managed_process = self._find_matching_managed_process(plan=plan)
        port_process = self._find_process_for_cdp_port(plan=plan)
        if (
            plan.launch_policy == "launch-if-missing"
            and managed_process is not None
            and managed_process["headless"] != bool(plan.system.headless)
        ):
            raise BrowserValidationError(
                "Managed browser host is running with a headless mode that does not match "
                "the configured profile. Stop the daemon host service and retry.",
            )
        if (
            plan.launch_policy == "launch-if-missing"
            and managed_process is None
            and port_process is not None
        ):
            expected_user_data_dir = self._try_resolve_user_data_dir(plan=plan)
            port_command = str(port_process.get("command", "")).strip()
            expected_headless = bool(plan.system.headless)
            actual_headless = "--headless" in port_command
            matches_remote_allow_origins = _has_expected_remote_allow_origins(
                command=port_command,
                host=plan.system.cdp_host,
                port=int(plan.profile.cdp_port or 0),
            )
            matches_user_data_dir = (
                expected_user_data_dir is not None
                and f"--user-data-dir={expected_user_data_dir}" in port_command
            )
            if (
                not matches_user_data_dir
                or actual_headless != expected_headless
                or not matches_remote_allow_origins
            ):
                raise BrowserValidationError(
                    "CDP port is occupied by a browser process that does not match the "
                    "configured managed profile. Stop or reconcile the daemon host service.",
                )

        runtime_state.mark_attached(
            browser_ref=browser_ref or base_url,
            running_pid=(
                int(managed_process["pid"])
                if managed_process is not None
                else (int(port_process["pid"]) if port_process is not None else None)
            ),
        )
        if managed_process is None and port_process is None:
            runtime_state.running_pid = None
        user_data_dir = self._try_resolve_user_data_dir(plan=plan)
        if user_data_dir is not None:
            runtime_state.metadata["user_data_dir"] = user_data_dir
        runtime_state.metadata[_METADATA_CDP_BASE_URL_KEY] = base_url
        runtime_state.remember_host_generation(
            _host_generation(
                base_url=base_url,
                browser_ref=runtime_state.browser_ref,
                running_pid=runtime_state.running_pid,
            ),
        )
        self._sync_host_daemon_ready(
            plan=plan,
            pid=runtime_state.running_pid,
            endpoint=base_url,
        )
        browser_endpoint_changed = previous_base_url != base_url
        browser_pid_changed = previous_running_pid != runtime_state.running_pid
        if not cached_tabs_fresh or browser_endpoint_changed or browser_pid_changed:
            tabs = self.list_tabs(plan=plan, runtime_state=runtime_state)
            _store_tabs(runtime_state, tabs)
        return runtime_state

    def list_tabs(
        self,
        *,
        plan: BrowserExecutionPlan,
        runtime_state: BrowserProfileRuntimeState,
    ) -> tuple[BrowserTab, ...]:
        with host_daemon_lease(
            daemon_service=self.daemon_service,
            plan=plan,
            user_data_dir=self._try_resolve_user_data_dir(plan=plan),
        ):
            return self._list_tabs_unleased(plan=plan, runtime_state=runtime_state)

    def open_tab(
        self,
        *,
        plan: BrowserExecutionPlan,
        runtime_state: BrowserProfileRuntimeState,
        url: str,
    ) -> BrowserTab:
        with host_daemon_lease(
            daemon_service=self.daemon_service,
            plan=plan,
            user_data_dir=self._try_resolve_user_data_dir(plan=plan),
        ):
            base_url = self._current_cdp_base_url(plan=plan, runtime_state=runtime_state)
            payload, base_url = self._request_cdp_json(
                plan=plan,
                runtime_state=runtime_state,
                path=build_cdp_json_new_endpoint(base_url, url).removeprefix(base_url),
                methods=("put", "get"),
            )

            if not isinstance(payload, dict):
                raise BrowserValidationError("Browser CDP open-tab returned an invalid payload.")
            tab = _tab_from_cdp_payload(
                payload,
                include_ws_url=plan.capabilities.supports_per_tab_ws,
                include_json_endpoints=plan.capabilities.supports_json_tab_endpoints,
                base_url=base_url,
            )
            tabs = (
                self._list_tabs_unleased(plan=plan, runtime_state=runtime_state)
                if self._host_daemon_enabled(plan=plan)
                else self.list_tabs(plan=plan, runtime_state=runtime_state)
            )
            tab = _canonicalize_opened_tab(opened_tab=tab, live_tabs=tabs)
            _store_tabs(runtime_state, tabs)
            _set_active_target(runtime_state, tab.target_id)
            return tab

    def navigate_tab(
        self,
        *,
        plan: BrowserExecutionPlan,
        runtime_state: BrowserProfileRuntimeState,
        target_id: str,
        url: str,
    ) -> BrowserTab:
        with host_daemon_lease(
            daemon_service=self.daemon_service,
            plan=plan,
            user_data_dir=self._try_resolve_user_data_dir(plan=plan),
        ):
            base_url = self._current_cdp_base_url(plan=plan, runtime_state=runtime_state)
            payload = self._require_tab_payload(plan=plan, target_id=target_id)
            ws_url = str(payload.get("webSocketDebuggerUrl", "")).strip()
            if not ws_url:
                raise BrowserValidationError(
                    f"Browser tab '{target_id}' does not expose a websocket debugger URL.",
                )
            _send_cdp_command(
                ws_connect=self.ws_connect,
                ws_url=ws_url,
                method="Page.navigate",
                params={"url": url},
                timeout_s=self.request_timeout_s,
            )
            refreshed_payload = self._require_tab_payload(plan=plan, target_id=target_id)
            tab = _tab_from_cdp_payload(
                refreshed_payload,
                include_ws_url=plan.capabilities.supports_per_tab_ws,
                include_json_endpoints=plan.capabilities.supports_json_tab_endpoints,
                base_url=base_url,
            )
            tabs = (
                self._list_tabs_unleased(plan=plan, runtime_state=runtime_state)
                if self._host_daemon_enabled(plan=plan)
                else self.list_tabs(plan=plan, runtime_state=runtime_state)
            )
            _store_tabs(runtime_state, tabs)
            _set_active_target(runtime_state, tab.target_id)
            return tab

    def focus_tab(
        self,
        *,
        plan: BrowserExecutionPlan,
        runtime_state: BrowserProfileRuntimeState,
        target_id: str,
    ) -> BrowserTab:
        with host_daemon_lease(
            daemon_service=self.daemon_service,
            plan=plan,
            user_data_dir=self._try_resolve_user_data_dir(plan=plan),
        ):
            base_url = self._current_cdp_base_url(plan=plan, runtime_state=runtime_state)
            request_url = append_cdp_path(base_url, f"/json/activate/{target_id}")
            try:
                response = self._http.get(request_url, timeout=self.request_timeout_s)
                response.raise_for_status()
            except requests.RequestException as exc:
                raise BrowserValidationError(
                    _request_error_message(method="get", url=request_url, exc=exc),
                ) from exc
            tab = _tab_from_cdp_payload(
                self._require_tab_payload(plan=plan, target_id=target_id),
                include_ws_url=plan.capabilities.supports_per_tab_ws,
                include_json_endpoints=plan.capabilities.supports_json_tab_endpoints,
                base_url=base_url,
            )
            tabs = (
                self._list_tabs_unleased(plan=plan, runtime_state=runtime_state)
                if self._host_daemon_enabled(plan=plan)
                else self.list_tabs(plan=plan, runtime_state=runtime_state)
            )
            _store_tabs(runtime_state, tabs)
            _set_active_target(runtime_state, tab.target_id)
            return tab

    def close_tab(
        self,
        *,
        plan: BrowserExecutionPlan,
        runtime_state: BrowserProfileRuntimeState,
        target_id: str,
    ) -> None:
        with host_daemon_lease(
            daemon_service=self.daemon_service,
            plan=plan,
            user_data_dir=self._try_resolve_user_data_dir(plan=plan),
        ):
            base_url = self._current_cdp_base_url(plan=plan, runtime_state=runtime_state)
            request_url = append_cdp_path(base_url, f"/json/close/{target_id}")
            try:
                response = self._http.get(request_url, timeout=self.request_timeout_s)
                response.raise_for_status()
            except requests.RequestException as exc:
                raise BrowserValidationError(
                    _request_error_message(method="get", url=request_url, exc=exc),
                ) from exc
            tabs = (
                self._list_tabs_unleased(plan=plan, runtime_state=runtime_state)
                if self._host_daemon_enabled(plan=plan)
                else self.list_tabs(plan=plan, runtime_state=runtime_state)
            )
            _store_tabs(runtime_state, tabs)
            active_target = runtime_state.metadata.get(_METADATA_ACTIVE_TARGET_KEY)
            if active_target == target_id:
                _set_active_target(runtime_state, tabs[0].target_id if tabs else None)

    def reset_profile(
        self,
        *,
        plan: BrowserExecutionPlan,
        runtime_state: BrowserProfileRuntimeState,
    ) -> None:
        user_data_dir = self._resolve_user_data_dir(plan=plan)
        self._stop_host_daemon_process(plan=plan)
        self._clear_user_data_dir(Path(user_data_dir))
        runtime_state.metadata.clear()
        runtime_state.remember_target(None)
        runtime_state.mark_closed()

    def stop_profile(
        self,
        *,
        plan: BrowserExecutionPlan,
        runtime_state: BrowserProfileRuntimeState,
    ) -> None:
        runtime_state.metadata.clear()
        runtime_state.remember_target(None)
        runtime_state.mark_closed()
        self._stop_host_daemon_process(plan=plan)

    def close(self) -> None:
        self._http.close()

    def _list_tab_payloads(
        self,
        *,
        plan: BrowserExecutionPlan,
    ) -> tuple[dict[str, Any], ...]:
        payload, _ = self._request_cdp_json(
            plan=plan,
            runtime_state=None,
            path="/json/list",
        )
        if not isinstance(payload, list):
            raise BrowserValidationError("Browser CDP list-tabs returned an invalid payload.")
        resolved: list[dict[str, Any]] = []
        for item in payload:
            if isinstance(item, dict):
                resolved.append(dict(item))
        return tuple(resolved)

    def _list_tabs_unleased(
        self,
        *,
        plan: BrowserExecutionPlan,
        runtime_state: BrowserProfileRuntimeState,
    ) -> tuple[BrowserTab, ...]:
        base_url = self._current_cdp_base_url(plan=plan, runtime_state=runtime_state)
        payloads = self._list_tab_payloads(plan=plan)
        return tuple(
            _tab_from_cdp_payload(
                payload,
                include_ws_url=plan.capabilities.supports_per_tab_ws,
                include_json_endpoints=plan.capabilities.supports_json_tab_endpoints,
                base_url=base_url,
            )
            for payload in payloads
            if str(payload.get("id", "")).strip()
        )

    def _require_tab_payload(
        self,
        *,
        plan: BrowserExecutionPlan,
        target_id: str,
    ) -> dict[str, Any]:
        for payload in self._list_tab_payloads(plan=plan):
            if str(payload.get("id", "")).strip() == target_id:
                return payload
        raise BrowserValidationError(f"Browser tab '{target_id}' was not found.")

    def _current_cdp_base_url(
        self,
        *,
        plan: BrowserExecutionPlan,
        runtime_state: BrowserProfileRuntimeState | None,
    ) -> str:
        return self._candidate_cdp_base_urls(
            plan=plan,
            runtime_state=runtime_state,
        )[0]

    def _candidate_cdp_base_urls(
        self,
        *,
        plan: BrowserExecutionPlan,
        runtime_state: BrowserProfileRuntimeState | None,
    ) -> tuple[str, ...]:
        cached = None
        browser_ref = None
        if runtime_state is not None:
            raw_cached = runtime_state.metadata.get(_METADATA_CDP_BASE_URL_KEY)
            cached = raw_cached if isinstance(raw_cached, str) else None
            browser_ref = runtime_state.browser_ref
        candidates: list[str] = []
        for endpoint in self._host_daemon_cdp_base_urls(plan=plan):
            _push_cdp_base(candidates, endpoint)
        if (
            plan.profile.driver == "existing-session"
            and plan.profile.cdp_url is None
            and plan.profile.cdp_port is None
        ):
            return tuple(candidates)
        for endpoint in candidate_cdp_http_bases(
            plan.profile.cdp_url,
            cached_base_url=cached,
            browser_ref=browser_ref,
        ):
            _push_cdp_base(candidates, endpoint)
        return tuple(candidates)

    def _host_daemon_cdp_base_urls(
        self,
        *,
        plan: BrowserExecutionPlan,
    ) -> tuple[str, ...]:
        if not self._host_daemon_enabled(plan=plan):
            return ()
        try:
            instances = self.daemon_service.list_instances(
                service_key=self._host_daemon_service_key(profile_name=plan.profile.name),
            )
        except Exception:  # noqa: BLE001
            return ()
        endpoints: list[str] = []
        for instance in instances:
            if getattr(instance, "status", "") not in {"ready", "degraded"}:
                continue
            _push_cdp_base(endpoints, getattr(instance, "endpoint", None))
            metadata = getattr(instance, "metadata", None)
            if not isinstance(metadata, dict):
                continue
            _push_cdp_base(endpoints, metadata.get("server_url"))
            _push_cdp_base(endpoints, metadata.get("cdp_url"))
        return tuple(endpoints)

    def _request_cdp_json(
        self,
        *,
        plan: BrowserExecutionPlan,
        runtime_state: BrowserProfileRuntimeState | None,
        path: str,
        methods: tuple[str, ...] = ("get",),
    ) -> tuple[Any, str]:
        last_error: BrowserValidationError | None = None
        candidates = self._candidate_cdp_base_urls(
            plan=plan,
            runtime_state=runtime_state,
        )
        if not candidates:
            raise BrowserValidationError(_missing_cdp_endpoint_message(plan=plan))
        for base_url in candidates:
            request_url = append_cdp_path(base_url, path)
            for method in methods:
                try:
                    response = getattr(self._http, method)(
                        request_url,
                        timeout=self.request_timeout_s,
                    )
                except requests.RequestException as exc:
                    last_error = BrowserValidationError(
                        _request_error_message(method=method, url=request_url, exc=exc),
                    )
                    continue
                if method == "put" and response.status_code in {404, 405, 501}:
                    continue
                payload = _read_json_response(
                    method=method,
                    url=request_url,
                    response=response,
                )
                if runtime_state is not None:
                    runtime_state.metadata[_METADATA_CDP_BASE_URL_KEY] = base_url
                return payload, base_url
        if last_error is not None:
            raise last_error
        raise BrowserValidationError(f"Browser CDP request for '{path}' failed.")

    def _resolve_executable_path(self, *, plan: BrowserExecutionPlan) -> str:
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

    def _resolve_user_data_dir(self, *, plan: BrowserExecutionPlan) -> str:
        configured = plan.profile.user_data_dir
        if configured is not None:
            path = Path(configured).expanduser()
        elif self.profiles_root is not None:
            path = (
                Path(self.profiles_root).expanduser().resolve()
                / plan.profile.name
                / "userdata"
            )
        else:
            raise BrowserValidationError(
                "Local managed browser launch requires a user_data_dir or profiles_root.",
            )
        path.mkdir(parents=True, exist_ok=True)
        return str(path.resolve())

    def _find_matching_managed_process(
        self,
        *,
        plan: BrowserExecutionPlan,
    ) -> dict[str, Any] | None:
        cdp_port = plan.profile.cdp_port
        if cdp_port is None:
            return None
        try:
            user_data_dir = self._resolve_user_data_dir(plan=plan)
        except BrowserValidationError:
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
            if f"--user-data-dir={user_data_dir}" not in command:
                continue
            if not _has_expected_remote_allow_origins(
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

    def _find_process_for_cdp_port(
        self,
        *,
        plan: BrowserExecutionPlan,
    ) -> dict[str, Any] | None:
        cdp_port = plan.profile.cdp_port
        if cdp_port is None:
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
                "command": command,
                "headless": "--headless" in command,
            }
        return None

    def _try_resolve_user_data_dir(
        self,
        *,
        plan: BrowserExecutionPlan,
    ) -> str | None:
        try:
            return self._resolve_user_data_dir(plan=plan)
        except BrowserValidationError:
            return None

    @staticmethod
    def _clear_user_data_dir(path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True)
        for child in path.iterdir():
            if child.is_dir() and not child.is_symlink():
                shutil.rmtree(child, ignore_errors=True)
            else:
                child.unlink(missing_ok=True)

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

    def _find_process_by_pid(self, pid: int) -> dict[str, Any] | None:
        for item in self.list_processes():
            if item.get("pid") == pid:
                return item
        return None

    def _host_daemon_enabled(self, *, plan: BrowserExecutionPlan) -> bool:
        return host_daemon_enabled(plan=plan)

    def _host_daemon_service_key(self, *, profile_name: str) -> str:
        return host_daemon_service_key(profile_name=profile_name)

    def _host_daemon_metadata(
        self,
        *,
        plan: BrowserExecutionPlan,
        pid: int | None = None,
    ) -> dict[str, Any]:
        user_data_dir = self._try_resolve_user_data_dir(plan=plan)
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

    def _sync_host_daemon_ready(
        self,
        *,
        plan: BrowserExecutionPlan,
        pid: int | None,
        endpoint: str | None,
    ) -> None:
        if not self._host_daemon_enabled(plan=plan):
            return
        self.daemon_service.report_service_ready(
            service_key=self._host_daemon_service_key(profile_name=plan.profile.name),
            pid=pid,
            endpoint=endpoint,
            metadata=self._host_daemon_metadata(plan=plan, pid=pid),
        )

    def _sync_host_daemon_failed(
        self,
        *,
        plan: BrowserExecutionPlan,
        reason: str,
    ) -> None:
        if not self._host_daemon_enabled(plan=plan):
            return
        self.daemon_service.report_service_failed(
            service_key=self._host_daemon_service_key(profile_name=plan.profile.name),
            reason=reason,
            metadata=self._host_daemon_metadata(plan=plan),
        )

    def _sync_host_daemon_stopped(self, *, plan: BrowserExecutionPlan) -> None:
        if not self._host_daemon_enabled(plan=plan):
            return
        self.daemon_service.report_service_stopped(
            service_key=self._host_daemon_service_key(profile_name=plan.profile.name),
            clear_metadata_keys=("browser_pid",),
        )

    def _stop_host_daemon_process(self, *, plan: BrowserExecutionPlan) -> None:
        if not self._host_daemon_enabled(plan=plan):
            return
        service_key = self._host_daemon_service_key(profile_name=plan.profile.name)
        stop_service = getattr(self.daemon_manager, "stop_service", None)
        if callable(stop_service):
            try:
                stop_service(service_key)
            except Exception as exc:  # noqa: BLE001
                raise BrowserValidationError(
                    f"Failed to stop browser daemon service '{service_key}': {exc}",
                ) from exc
            return
        self._sync_host_daemon_stopped(plan=plan)


def _push_cdp_base(candidates: list[str], value: object) -> None:
    try:
        normalized = normalize_cdp_http_base(value if isinstance(value, str) else None)
    except BrowserValidationError:
        return
    if normalized not in candidates:
        candidates.append(normalized)


def _missing_cdp_endpoint_message(*, plan: BrowserExecutionPlan) -> str:
    if plan.profile.driver == "existing-session":
        return (
            f"Existing-session browser profile '{plan.profile.name}' requires a "
            "configured CDP URL or port. Start the target browser with remote "
            "debugging enabled and set cdp_url/cdp_port before using this profile."
        )
    if plan.capabilities.is_remote:
        return (
            f"Remote browser profile '{plan.profile.name}' requires a configured "
            "CDP URL or port."
        )
    return f"Browser profile '{plan.profile.name}' does not expose a CDP endpoint."


@dataclass(frozen=True, slots=True)
class InMemoryCdpBackedPlaywrightActionEngine(BrowserActionEngine):
    family: BrowserActionFamily = "cdp-backed-playwright"

    def supports(
        self,
        *,
        command: BrowserPageActionCommand,
    ) -> bool:
        del command
        return True

    def execute(
        self,
        *,
        plan: BrowserExecutionPlan,
        runtime_state: BrowserProfileRuntimeState,
        tab: BrowserTab | None,
        command: BrowserPageActionCommand,
    ) -> BrowserActionResult:
        del runtime_state
        if tab is None:
            raise BrowserValidationError("cdp-backed-playwright actions require a tab.")
        return BrowserActionResult(
            command=command,
            ok=True,
            target_id=tab.target_id,
            value={
                "engine": self.family,
                "control_family": plan.control_family,
                "profile": plan.profile.name,
                "tab": {
                    "target_id": tab.target_id,
                    "url": tab.url,
                    "title": tab.title,
                    "type": tab.type,
                },
                "ref": command.target.ref,
                "selector": command.target.selector,
                "payload": dict(command.payload),
            },
            message=f"Executed {command.kind} via cdp-backed-playwright.",
        )

    def clear_profile(
        self,
        *,
        profile_name: str,
    ) -> None:
        del profile_name
