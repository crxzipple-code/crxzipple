from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field
from pathlib import Path
from typing import Any

import requests
import websocket

from crxzipple.modules.daemon import (
    DaemonApplicationService,
)
from crxzipple.modules.browser.domain import (
    BrowserExecutionPlan,
    BrowserProfileRuntimeState,
    BrowserValidationError,
)

from ..application.ports import BrowserControlEngine
from .cdp_urls import (
    append_cdp_path,
    candidate_cdp_http_bases,
)
from .daemon_leases import host_daemon_enabled, host_daemon_service_key
from .engines_cdp_io import (
    has_expected_remote_allow_origins as _has_expected_remote_allow_origins,
    missing_cdp_endpoint_message as _missing_cdp_endpoint_message,
    push_cdp_base as _push_cdp_base,
    read_json_response as _read_json_response,
    request_error_message as _request_error_message,
)
from .engines_control_tabs import CdpControlTabMixin
from .engines_host_lifecycle import (
    clear_user_data_dir,
    default_list_processes,
    find_matching_managed_process,
    find_process_by_pid,
    find_process_for_cdp_port,
    host_daemon_cdp_base_urls,
    host_daemon_metadata,
    resolve_executable_path,
    resolve_user_data_dir,
    stop_host_daemon_process,
    sync_host_daemon_failed,
    sync_host_daemon_ready,
    sync_host_daemon_stopped,
    try_resolve_user_data_dir,
)
from .engines_in_memory import (
    InMemoryCdpBackedPlaywrightActionEngine,
    InMemoryCdpControlEngine,
)
from .engines_tab_state import (
    METADATA_CDP_BASE_URL_KEY as _METADATA_CDP_BASE_URL_KEY,
    host_generation as _host_generation,
    store_tabs as _store_tabs,
    tabs_cache_is_fresh as _tabs_cache_is_fresh,
)


@dataclass(slots=True)
class CdpControlEngine(CdpControlTabMixin, BrowserControlEngine):
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
            object.__setattr__(self, "list_processes", default_list_processes)

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
        return host_daemon_cdp_base_urls(
            daemon_service=self.daemon_service,
            plan=plan,
        )

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
        return resolve_executable_path(plan=plan)

    def _resolve_user_data_dir(self, *, plan: BrowserExecutionPlan) -> str:
        return resolve_user_data_dir(plan=plan, profiles_root=self.profiles_root)

    def _find_matching_managed_process(
        self,
        *,
        plan: BrowserExecutionPlan,
    ) -> dict[str, Any] | None:
        return find_matching_managed_process(
            plan=plan,
            list_processes=self.list_processes,
            user_data_dir=self._try_resolve_user_data_dir(plan=plan),
        )

    def _find_process_for_cdp_port(
        self,
        *,
        plan: BrowserExecutionPlan,
    ) -> dict[str, Any] | None:
        return find_process_for_cdp_port(
            plan=plan,
            list_processes=self.list_processes,
        )

    def _try_resolve_user_data_dir(
        self,
        *,
        plan: BrowserExecutionPlan,
    ) -> str | None:
        return try_resolve_user_data_dir(plan=plan, profiles_root=self.profiles_root)

    @staticmethod
    def _clear_user_data_dir(path: Path) -> None:
        clear_user_data_dir(path)

    def _find_process_by_pid(self, pid: int) -> dict[str, Any] | None:
        return find_process_by_pid(list_processes=self.list_processes, pid=pid)

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
        return host_daemon_metadata(
            plan=plan,
            user_data_dir=self._try_resolve_user_data_dir(plan=plan),
            pid=pid,
        )

    def _sync_host_daemon_ready(
        self,
        *,
        plan: BrowserExecutionPlan,
        pid: int | None,
        endpoint: str | None,
    ) -> None:
        sync_host_daemon_ready(
            daemon_service=self.daemon_service,
            plan=plan,
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
        sync_host_daemon_failed(
            daemon_service=self.daemon_service,
            plan=plan,
            reason=reason,
            metadata=self._host_daemon_metadata(plan=plan),
        )

    def _sync_host_daemon_stopped(self, *, plan: BrowserExecutionPlan) -> None:
        sync_host_daemon_stopped(daemon_service=self.daemon_service, plan=plan)

    def _stop_host_daemon_process(self, *, plan: BrowserExecutionPlan) -> None:
        stop_host_daemon_process(
            daemon_service=self.daemon_service,
            daemon_manager=self.daemon_manager,
            plan=plan,
        )


__all__ = [
    "CdpControlEngine",
    "InMemoryCdpBackedPlaywrightActionEngine",
    "InMemoryCdpControlEngine",
]
