from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from crxzipple.modules.operations.application.read_models.browser import (
    BrowserOperationsReadModelProvider,
)
from crxzipple.modules.operations.application.observation import OperationsObservedEvent
from crxzipple.modules.operations.application.projections import (
    OPERATIONS_PROJECTION_MODULES,
)
from crxzipple.modules.operations.interfaces.http_models import BrowserOperationsResponse


class _BrowserProfiles:
    def list_profiles(self):
        return (
            SimpleNamespace(
                name="crxzipple",
                driver="managed",
                mode="managed-cdp",
                resolved_cdp_url="http://127.0.0.1:9222",
                configured_cdp_url=None,
                proxy_mode="none",
                proxy_binding_id=None,
                runtime={
                    "attachment_status": "attached",
                    "host_generation": "abcdef1234567890",
                    "page_state": {
                        "active_target_id": "tab-1",
                        "page_count": 1,
                        "active_page": {
                            "target_id": "tab-1",
                            "page_generation": 2,
                            "page_generation_reason": "navigate",
                            "snapshot_generation": None,
                            "current_ref_generation": None,
                            "last_action_kind": None,
                            "last_snapshot_ref_count": 0,
                            "last_snapshot_frame_count": 0,
                        },
                        "pages": [
                            {
                                "target_id": "tab-1",
                                "page_generation": 2,
                                "page_generation_reason": "navigate",
                                "snapshot_generation": None,
                                "current_ref_generation": None,
                                "last_action_kind": None,
                                "last_snapshot_ref_count": 0,
                                "last_snapshot_frame_count": 0,
                            },
                        ],
                    },
                },
            ),
        )

    def list_pools(self):
        return (
            SimpleNamespace(
                pool_id="collector",
                display_name="Collector Pool",
                enabled=True,
                status="active",
                profile_names=("crxzipple",),
                target_hosts=("ctrip.com",),
                selection_strategy="least_busy",
                max_concurrency_per_profile=1,
                max_concurrency_total=3,
                allocation_ttl_seconds=900,
                cooldown_seconds=30,
                failure_cooldown_seconds=300,
                allow_attach_only=False,
                profile_count=1,
                ready_profile_count=1,
                missing_profile_names=(),
                disabled_profile_names=(),
                attach_only_profile_names=(),
                active_allocation_count=1,
                diagnostics={"ok": True},
            ),
        )

    def list_allocations(self):
        return (
            SimpleNamespace(
                allocation_id="browser_alloc_1",
                pool_id="collector",
                profile_name="crxzipple",
                consumer_kind="tool_run",
                consumer_id="tool_run_1",
                target_host="ctrip.com",
                status="active",
                raw_status="active",
                acquired_at=datetime(2026, 5, 25, 15, 0, 0, tzinfo=timezone.utc),
                expires_at=datetime(2026, 5, 25, 15, 15, 0, tzinfo=timezone.utc),
                released_at=None,
                release_reason=None,
                metadata={},
            ),
        )


class _DaemonService:
    def list_service_specs(self):
        return (
            SimpleNamespace(
                key="host:browser:crxzipple",
                display_name="Browser Host",
                service_group="browser",
                role="host",
                managed_by="daemon",
                transport="process",
                replica_mode="singleton",
                desired_replicas=1,
                start_policy="on-demand",
                restart_policy="never",
                healthcheck_policy="cdp",
                match_policy="service_key",
                metadata={},
            ),
        )


class _DaemonManager:
    def list_instances(self):
        return (
            SimpleNamespace(
                id="browser-host-1",
                service_key="host:browser:crxzipple",
                status="ready",
                worker_id="daemon",
                pid=12345,
                endpoint="http://127.0.0.1:9222",
                started_at=None,
                last_healthcheck_at=None,
                last_error=None,
                metadata={
                    "browser_pid": 54321,
                    "manifest_status": "ready",
                    "cdp_url": "http://127.0.0.1:9222",
                },
            ),
        )


class _Readiness:
    ready = True
    status = "ready"

    def to_payload(self):
        return {"ready": True, "status": "ready"}


class _AccessService:
    def __init__(self) -> None:
        self.checked: list[tuple[str, str | None]] = []

    def check_credential_binding(self, binding_id: str, *, expected_kind: str | None = None):
        self.checked.append((binding_id, expected_kind))
        return _Readiness()


def _utc(hour: int, minute: int, second: int) -> datetime:
    return datetime(2026, 5, 25, hour, minute, second, tzinfo=timezone.utc)


def _browser_event(
    name: str,
    *,
    cursor: str,
    status: str = "observed",
    level: str = "info",
    payload: dict[str, object] | None = None,
) -> OperationsObservedEvent:
    return OperationsObservedEvent(
        id=f"event-{cursor}",
        cursor=cursor,
        topic=f"events.named.{name}",
        event_name=name,
        module="browser",
        owner="browser",
        kind="observe",
        level=level,
        status=status,
        entity_id=str((payload or {}).get("entity_id") or name),
        run_id=None,
        trace_id=None,
        source_event_name=None,
        occurred_at=_utc(15, 10, int(cursor)),
        payload=dict(payload or {}),
    )


class _BrowserObservation:
    def __init__(self, events: tuple[OperationsObservedEvent, ...]) -> None:
        self.events = events

    def get_module_observation(self, module: str):
        if module != "browser":
            return None
        return SimpleNamespace(recent_events=self.events)


def test_browser_operations_projects_profiles_pages_and_daemon_runtime() -> None:
    provider = BrowserOperationsReadModelProvider(
        browser_profile_service=_BrowserProfiles(),
        daemon_service=_DaemonService(),
        daemon_manager=_DaemonManager(),
    )

    page = provider.page()

    assert page.module == "browser"
    assert page.health == "warning"
    assert page.profiles.total == 1
    profile_row = page.profiles.rows[0]
    assert profile_row.cells["profile"] == "crxzipple"
    assert profile_row.cells["status"] == "attached"
    assert profile_row.cells["host_generation"] == "abcdef123456"
    assert profile_row.cells["snapshot_generation"] == "-"
    assert page.profile_pools.total == 1
    pool_row = page.profile_pools.rows[0]
    assert pool_row.cells["pool"] == "collector"
    assert pool_row.cells["active_allocations"] == "1"
    assert page.profile_allocations.total == 1
    allocation_row = page.profile_allocations.rows[0]
    assert allocation_row.cells["allocation"] == "browser_alloc_1"
    assert allocation_row.cells["profile"] == "crxzipple"
    assert page.page_observations.total == 1
    page_row = page.page_observations.rows[0]
    assert page_row.status == "stale"
    assert page_row.cells["reason"] == "navigate"
    assert page_row.cells["stale"] == "Yes"
    assert page.daemon_runtimes.total == 1
    runtime_kinds = {row.cells["runtime"] for row in page.daemon_runtimes.rows}
    assert runtime_kinds == {"Browser Host"}
    response = BrowserOperationsResponse.from_view(page)
    assert response.module == "browser"
    assert response.profile_pools.rows[0].cells["pool"] == "collector"
    assert response.profile_allocations.rows[0].cells["allocation"] == "browser_alloc_1"
    assert response.page_observations.rows[0].cells["stale"] == "Yes"
    assert response.network_activity.total == 0
    assert response.diagnostics.total == 0


def test_browser_operations_projects_network_and_diagnostic_events() -> None:
    events = (
        _browser_event(
            "browser.diagnostics.collected",
            cursor="1",
            status="warning",
            level="warning",
            payload={
                "profile_name": "crxzipple",
                "target_id": "tab-1",
                "diagnostic_kind": "diagnostics-collect",
                "issue_count": 2,
                "console_count": 5,
                "error_count": 2,
                "ready_state": "complete",
                "display_summary": "diagnostics-collect found 2 issue(s).",
            },
        ),
        _browser_event(
            "browser.network.request.failed",
            cursor="2",
            status="failed",
            level="warning",
            payload={
                "profile_name": "crxzipple",
                "target_id": "tab-1",
                "capture_id": "cap-1",
                "request_id": "req-1",
                "method": "GET",
                "url": "https://example.com/api",
                "failure_text": "net::ERR_FAILED",
            },
        ),
    )
    provider = BrowserOperationsReadModelProvider(
        browser_profile_service=_BrowserProfiles(),
        operations_observation=_BrowserObservation(events),
    )

    page = provider.page()

    assert page.network_activity.total == 1
    network_row = page.network_activity.rows[0]
    assert network_row.tone == "danger"
    assert network_row.cells["capture"] == "cap-1"
    assert network_row.cells["summary"] == "net::ERR_FAILED"
    assert page.diagnostics.total == 1
    diagnostic_row = page.diagnostics.rows[0]
    assert diagnostic_row.tone == "warning"
    assert diagnostic_row.cells["issues"] == "2"
    assert diagnostic_row.cells["ready_state"] == "complete"
    assert page.health == "error"


def test_browser_operations_prefers_ready_daemon_instance_over_stale_history() -> None:
    class _HistoryDaemonManager:
        def list_instances(self, *, refresh: bool = True):
            del refresh
            return (
                SimpleNamespace(
                    id="browser-host-current",
                    service_key="host:browser:crxzipple",
                    status="ready",
                    worker_id="daemon",
                    pid=12345,
                    endpoint="http://127.0.0.1:9222",
                    started_at=_utc(15, 29, 6),
                    updated_at=_utc(15, 40, 52),
                    last_healthcheck_at=_utc(15, 40, 52),
                    last_error=None,
                    metadata={
                        "profile_name": "crxzipple",
                        "browser_pid": 54321,
                        "manifest_status": "ready",
                        "cdp_url": "http://127.0.0.1:9222",
                    },
                ),
                SimpleNamespace(
                    id="browser-host-old",
                    service_key="host:browser:crxzipple",
                    status="stopped",
                    worker_id="daemon",
                    pid=None,
                    endpoint="http://127.0.0.1:9222",
                    started_at=_utc(15, 28, 6),
                    updated_at=_utc(15, 41, 52),
                    last_healthcheck_at=_utc(15, 41, 52),
                    last_error=None,
                    metadata={
                        "profile_name": "crxzipple",
                        "manifest_status": "stopped",
                        "cdp_url": "http://127.0.0.1:9222",
                    },
                ),
            )

    provider = BrowserOperationsReadModelProvider(
        browser_profile_service=_BrowserProfiles(),
        daemon_service=_DaemonService(),
        daemon_manager=_HistoryDaemonManager(),
    )

    page = provider.page()
    row = page.daemon_runtimes.rows[0]

    assert row.cells["status"] == "ready"
    assert row.cells["pid"] == "12345"
    assert row.cells["manifest"] == "ready"
    daemon_metric = next(item for item in page.metrics if item.id == "daemon_runtimes")
    assert daemon_metric.delta == "1 ready"


def test_browser_operations_treats_existing_session_attach_failure_as_warning() -> None:
    class _Profiles:
        def list_profiles(self):
            return (
                SimpleNamespace(
                    name="user",
                    driver="existing-session",
                    mode="local-existing-session",
                    resolved_cdp_url=None,
                    configured_cdp_url=None,
                    proxy_mode="none",
                    proxy_binding_id=None,
                    runtime={
                        "attachment_status": "failed",
                        "page_state": {
                            "active_target_id": None,
                            "page_count": 0,
                            "pages": [],
                        },
                    },
                ),
            )

    provider = BrowserOperationsReadModelProvider(
        browser_profile_service=_Profiles(),
        daemon_service=_DaemonService(),
        daemon_manager=_DaemonManager(),
    )

    page = provider.page()

    assert page.health == "warning"
    assert page.profiles.rows[0].cells["status"] == "failed"
    assert page.profiles.rows[0].cells["endpoint"] == "-"
    assert page.profiles.rows[0].tone == "warning"


def test_browser_operations_projects_proxy_access_binding_readiness() -> None:
    class _ProxyProfiles:
        def list_profiles(self):
            return (
                SimpleNamespace(
                    name="work",
                    driver="managed",
                    mode="local-managed",
                    resolved_cdp_url="http://127.0.0.1:9223",
                    configured_cdp_url=None,
                    proxy_mode="access_binding",
                    proxy_binding_id="proxy-basic",
                    runtime={
                        "attachment_status": "attached",
                        "host_generation": "abcdef1234567890",
                        "page_state": {"active_target_id": None, "page_count": 0, "pages": []},
                    },
                ),
            )

    class _ProxyDaemonManager:
        def list_instances(self, *, refresh: bool = True):
            del refresh
            return (
                SimpleNamespace(
                    id="browser-host-work",
                    service_key="host:browser:work",
                    status="ready",
                    worker_id="daemon",
                    pid=45678,
                    endpoint="http://127.0.0.1:9223",
                    started_at=None,
                    last_healthcheck_at=None,
                    last_error=None,
                    metadata={
                        "profile_name": "work",
                        "proxy_mode": "access_binding",
                        "proxy_binding_id": "proxy-basic",
                        "proxy_egress": {
                            "status": "ready",
                            "ip": "203.0.113.10",
                        },
                    },
                ),
            )

    access = _AccessService()
    provider = BrowserOperationsReadModelProvider(
        browser_profile_service=_ProxyProfiles(),
        access_service=access,
        daemon_service=_DaemonService(),
        daemon_manager=_ProxyDaemonManager(),
    )

    page = provider.page()

    row = page.profiles.rows[0]
    assert row.cells["proxy"] == "access_binding · basic · proxy-basic"
    assert row.cells["proxy_readiness"] == "ready"
    assert row.cells["proxy_egress"] == "ready · 203.0.113.10"
    daemon_by_key = {item.cells["service_key"]: item for item in page.daemon_runtimes.rows}
    assert daemon_by_key["host:browser:work"].cells["proxy_egress"] == "ready · 203.0.113.10"
    assert access.checked == [("proxy-basic", "basic")]


def test_browser_operations_projects_bearer_proxy_readiness() -> None:
    class _BearerProxyProfiles:
        def list_profiles(self):
            return (
                SimpleNamespace(
                    name="work",
                    driver="managed",
                    mode="local-managed",
                    resolved_cdp_url="http://127.0.0.1:9223",
                    configured_cdp_url=None,
                    proxy_mode="access_binding",
                    proxy_binding_id="proxy-bearer",
                    proxy_credential_kind="bearer_token",
                    runtime={"attachment_status": "closed"},
                ),
            )

    access = _AccessService()
    provider = BrowserOperationsReadModelProvider(
        browser_profile_service=_BearerProxyProfiles(),
        access_service=access,
    )

    page = provider.page()

    row = page.profiles.rows[0]
    assert row.cells["proxy"] == "access_binding · bearer_token · proxy-bearer"
    assert row.cells["proxy_readiness"] == "ready"
    assert access.checked == [("proxy-bearer", "bearer_token")]


def test_browser_operations_reads_runtime_egress_when_daemon_metadata_is_absent() -> None:
    class _RuntimeEgressProfiles:
        def list_profiles(self):
            return (
                SimpleNamespace(
                    name="work",
                    driver="managed",
                    mode="local-managed",
                    resolved_cdp_url="http://127.0.0.1:9223",
                    configured_cdp_url=None,
                    proxy_mode="static",
                    proxy_binding_id=None,
                    runtime={
                        "attachment_status": "idle",
                        "proxy_egress": {
                            "status": "ready",
                            "ip": "203.0.113.44",
                        },
                        "page_state": {
                            "active_target_id": None,
                            "page_count": 0,
                            "pages": [],
                        },
                    },
                ),
            )

        def list_pools(self):
            return ()

        def list_allocations(self):
            return ()

    provider = BrowserOperationsReadModelProvider(
        browser_profile_service=_RuntimeEgressProfiles(),
        daemon_service=_DaemonService(),
        daemon_manager=_DaemonManager(),
    )

    page = provider.page()

    assert page.profiles.rows[0].cells["proxy_egress"] == "ready · 203.0.113.44"


def test_browser_operations_surfaces_pool_cooldown_and_failures() -> None:
    class _CoolingProfiles(_BrowserProfiles):
        def list_pools(self):
            return (
                SimpleNamespace(
                    pool_id="collector",
                    display_name="Collector Pool",
                    enabled=True,
                    status="active",
                    profile_names=("crawler-a", "crawler-b"),
                    target_hosts=("ctrip.com",),
                    selection_strategy="least_busy",
                    max_concurrency_per_profile=1,
                    max_concurrency_total=2,
                    allocation_ttl_seconds=900,
                    cooldown_seconds=30,
                    failure_cooldown_seconds=300,
                    allow_attach_only=False,
                    profile_count=2,
                    ready_profile_count=2,
                    missing_profile_names=(),
                    disabled_profile_names=(),
                    attach_only_profile_names=(),
                    active_allocation_count=1,
                    diagnostics={
                        "ok": True,
                        "available_profile_count": 1,
                        "cooling_profiles": ("crawler-a",),
                        "failure_cooldown_profiles": ("crawler-a",),
                        "release_cooldown_profiles": (),
                        "failed_allocation_count": 1,
                    },
                ),
            )

        def list_allocations(self):
            return (
                SimpleNamespace(
                    allocation_id="browser_alloc_failed",
                    pool_id="collector",
                    profile_name="crawler-a",
                    consumer_kind="tool_run",
                    consumer_id="tool_run_failed",
                    target_host="ctrip.com",
                    status="failed",
                    raw_status="failed",
                    acquired_at=datetime(2026, 5, 25, 15, 0, 0, tzinfo=timezone.utc),
                    expires_at=datetime(2026, 5, 25, 15, 15, 0, tzinfo=timezone.utc),
                    released_at=datetime(2026, 5, 25, 15, 0, 2, tzinfo=timezone.utc),
                    release_reason="proxy_failed",
                    metadata={},
                ),
                SimpleNamespace(
                    allocation_id="browser_alloc_active",
                    pool_id="collector",
                    profile_name="crawler-b",
                    consumer_kind="tool_run",
                    consumer_id="tool_run_active",
                    target_host="ctrip.com",
                    status="active",
                    raw_status="active",
                    acquired_at=datetime(2026, 5, 25, 15, 0, 3, tzinfo=timezone.utc),
                    expires_at=datetime(2026, 5, 25, 15, 15, 3, tzinfo=timezone.utc),
                    released_at=None,
                    release_reason=None,
                    metadata={},
                ),
            )

    provider = BrowserOperationsReadModelProvider(
        browser_profile_service=_CoolingProfiles(),
        daemon_service=_DaemonService(),
        daemon_manager=_DaemonManager(),
    )

    page = provider.page()
    pool_row = page.profile_pools.rows[0]
    allocation_rows = {row.cells["allocation"]: row for row in page.profile_allocations.rows}
    pool_metric = next(item for item in page.metrics if item.id == "profile_pools")
    allocation_metric = next(
        item for item in page.metrics if item.id == "profile_allocations"
    )

    assert page.health == "error"
    assert pool_row.tone == "warning"
    assert pool_row.cells["available_profiles"] == "1"
    assert pool_row.cells["cooling"] == "crawler-a"
    assert pool_row.cells["failure_cooldown"] == "crawler-a"
    assert pool_row.cells["recent_failures"] == "1"
    assert allocation_rows["browser_alloc_failed"].tone == "danger"
    assert allocation_rows["browser_alloc_failed"].cells["release_reason"] == "proxy_failed"
    assert pool_metric.delta == "1 active · 1 cooling"
    assert allocation_metric.delta == "1 active · 1 failed"


def test_browser_operations_overview_reuses_browser_page_tables() -> None:
    provider = BrowserOperationsReadModelProvider(
        browser_profile_service=_BrowserProfiles(),
        daemon_service=_DaemonService(),
        daemon_manager=_DaemonManager(),
    )

    overview = provider.overview()

    assert overview.module == "browser"
    assert overview.metrics[0].id == "health"
    assert overview.queue[0]["profile"] == "crxzipple"
    assert overview.lane_locks[0]["stale"] == "Yes"
    assert overview.executor[0]["runtime"] == "Browser Host"


def test_browser_operations_is_materialized_as_first_class_projection() -> None:
    assert "browser" in OPERATIONS_PROJECTION_MODULES
