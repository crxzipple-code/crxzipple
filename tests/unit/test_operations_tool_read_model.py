from __future__ import annotations

from tests.unit.browser_tool_package_support import (
    browser_function_catalog_candidates,
    browser_source_records_from_package,
)
from crxzipple.modules.operations.application.read_models.tool import (
    ToolOperationsReadModelProvider,
)
from crxzipple.modules.tool.application.catalog_models import (
    ToolFunctionCatalogRecord,
)
from crxzipple.modules.tool.application.concurrency import ToolRunConcurrencyPolicy
from crxzipple.modules.tool.domain import (
    ToolEnvironment,
    ToolExecutionStrategy,
    ToolExecutionTarget,
    ToolMode,
    ToolRun,
    ToolRunResult,
)


class _ToolService:
    concurrency_policy = ToolRunConcurrencyPolicy()

    def __init__(self, *, sources=(), functions=(), runs=()) -> None:  # noqa: ANN001
        self._sources = tuple(sources)
        self._functions = tuple(functions)
        self._runs = tuple(runs)
        self.list_tool_runs_limits: list[int | None] = []

    def list_tools(self):
        return ()

    def list_enabled_tools(self):
        return ()

    def list_tool_runs(self, *, limit: int | None = None):
        self.list_tool_runs_limits.append(limit)
        return self._runs[:limit] if limit is not None else self._runs

    def list_tool_workers(self):
        return ()

    def list_tool_run_assignments(self):
        return ()

    def check_readiness(self, _tool_id: str):
        return None

    def check_access_readiness(self, _tool_id: str):
        return None

    def list_sources(self):
        return self._sources

    def list_functions(self):
        return self._functions

    def list_provider_backends(self):
        return ()

    def check_provider_backend_readiness(self, _backend):
        return None

    def list_source_discovery_runs(self, _source_id: str, *, limit: int = 20):
        del limit
        return ()


class _ReadinessPoisonedToolService(_ToolService):
    def check_readiness(self, _tool_id: str):
        raise AssertionError("source health must not query tool runtime readiness")

    def check_access_readiness(self, _tool_id: str):
        raise AssertionError("source health must not query access readiness")


def _browser_run(
    *,
    run_id: str,
    tool_id: str,
    call_id: str,
    source_id: str,
    input_payload: dict[str, object],
) -> ToolRun:
    return ToolRun.create(
        run_id=run_id,
        tool_id=tool_id,
        call_id=call_id,
        tool_surface_id="tool_surface:browser",
        function_id=tool_id,
        source_id=source_id,
        input_payload=input_payload,
        target=ToolExecutionTarget(
            mode=ToolMode.INLINE,
            strategy=ToolExecutionStrategy.ASYNC,
            environment=ToolEnvironment.LOCAL,
        ),
    )


def test_tool_operations_page_contract_ids_and_counts_are_stable() -> None:
    source = browser_source_records_from_package()[0]
    functions = tuple(
        ToolFunctionCatalogRecord.from_candidate(candidate)
        for candidate in browser_function_catalog_candidates()
    )
    succeeded_run = _browser_run(
        run_id="run-terminal-1",
        tool_id="browser.navigate",
        call_id="call-terminal-1",
        source_id=source.source_id,
        input_payload={"url": "https://example.com"},
    )
    succeeded_run.start()
    succeeded_run.succeed(ToolRunResult.text("Browser tab opened."))
    queued_run = _browser_run(
        run_id="run-active-1",
        tool_id="browser.click",
        call_id="call-active-1",
        source_id=source.source_id,
        input_payload={"ref": "button"},
    )

    page = ToolOperationsReadModelProvider(
        tool_service=_ToolService(
            sources=(source,),
            functions=functions,
            runs=(succeeded_run, queued_run),
        ),
    ).page()

    assert [metric.id for metric in page.metrics] == [
        "health",
        "catalog",
        "active_runs",
        "failed_runs",
        "avg_latency",
        "p95_latency",
        "throughput",
        "confirmation",
        "access_gated",
    ]
    assert [tab.id for tab in page.tabs] == [
        "runs",
        "sources",
        "workers",
        "queue",
        "capabilities",
        "provider_limits",
        "provider_history",
        "diagnostics",
        "risk",
        "artifacts",
        "events",
        "strategies",
    ]
    assert {
        "runs": 2,
        "sources": 1,
        "workers": 0,
        "queue": 1,
        "provider_history": 1,
        "diagnostics": 1,
        "risk": 0,
        "artifacts": 0,
        "events": 0,
    }.items() <= {tab.id: tab.count for tab in page.tabs}.items()

    table_counts = {
        name: (getattr(page, name).id, getattr(page, name).total)
        for name in (
            "active_tool_runs",
            "tool_queue_runs",
            "tool_waiting_io",
            "tool_runs",
            "source_health",
            "discovery_failures",
            "provider_backend_health",
            "cli_process_health",
            "auth_missing",
            "workers",
            "tool_queue",
            "capability_limits",
            "provider_limits",
            "provider_history",
            "run_blockers",
            "recent_artifacts",
            "tool_lifecycle_events",
            "strategies",
        )
    }
    assert table_counts == {
        "active_tool_runs": ("active_tool_runs", 1),
        "tool_queue_runs": ("tool_queue_runs", 1),
        "tool_waiting_io": ("tool_waiting_io", 1),
        "tool_runs": ("tool_runs", 2),
        "source_health": ("source_health", 1),
        "discovery_failures": ("discovery_failures", 0),
        "provider_backend_health": ("provider_backend_health", 0),
        "cli_process_health": ("cli_process_health", 0),
        "auth_missing": ("auth_missing", 0),
        "workers": ("workers", 1),
        "tool_queue": ("tool_queue", 1),
        "capability_limits": ("capability_limits", 1),
        "provider_limits": ("provider_limits", 0),
        "provider_history": ("provider_history", 1),
        "run_blockers": ("run_blockers", 1),
        "recent_artifacts": ("recent_artifacts", 0),
        "tool_lifecycle_events": ("tool_lifecycle_events", 0),
        "strategies": ("strategies", 1),
    }
    assert (page.tool_types.id, page.tool_types.total) == ("tool_types", 2)
    assert (page.worker_pool.id, page.worker_pool.total) == ("worker_pool", 1)
    assert page.inline_risk.id == "inline_risk"

    detail_contract = {
        detail.run_id: (
            detail.assignments.id,
            detail.events.id,
            detail.artifacts.id,
            detail.error_facts.id,
            detail.result_summary,
        )
        for detail in page.tool_run_details
    }
    assert detail_contract == {
        "run-active-1": (
            "assignment_history",
            "run_events",
            "run_artifacts",
            "error_facts",
            "-",
        ),
        "run-terminal-1": (
            "assignment_history",
            "run_events",
            "run_artifacts",
            "error_facts",
            "Browser tab opened.",
        ),
    }


def test_tool_operations_source_health_exposes_single_browser_source() -> None:
    source = browser_source_records_from_package()[0]
    functions = tuple(
        ToolFunctionCatalogRecord.from_candidate(candidate)
        for candidate in browser_function_catalog_candidates()
    )
    tool_service = _ToolService(sources=(source,), functions=functions)

    page = ToolOperationsReadModelProvider(
        tool_service=tool_service,
    ).page()

    assert tool_service.list_tool_runs_limits == [500]
    assert page.projection_diagnostics is not None
    assert page.projection_diagnostics.module == "tool"
    assert page.projection_diagnostics.owner_call_count == 8
    assert page.projection_diagnostics.elapsed_ms >= 0
    assert page.projection_diagnostics.processed_item_count == len(functions) + 1
    assert {
        source.module
        for source in page.projection_diagnostics.owner_sources
    }.issuperset({"tool", "orchestration", "artifacts", "operations"})
    column_keys = {column.key for column in page.source_health.columns}
    assert {"endpoint", "runtime", "tools_list"}.issubset(column_keys)
    row = page.source_health.rows[0]
    assert row.id == "bundled.local_package.browser"
    assert row.cells["endpoint"] == "-"
    assert row.cells["runtime"] == "Browser profile context"
    assert row.cells["tools_list"] == "-"
    assert row.cells["functions"] == f"{len(functions)}/{len(functions)}"


def test_browser_source_health_is_not_downgraded_by_runtime_readiness() -> None:
    source = browser_source_records_from_package()[0]

    page = ToolOperationsReadModelProvider(
        tool_service=_ReadinessPoisonedToolService(sources=(source,)),
    ).page()

    row = page.source_health.rows[0]
    assert row.id == "bundled.local_package.browser"
    assert row.status == "active"
    assert row.tone == "success"
    assert row.cells["runtime"] == "Browser profile context"


def test_tool_run_detail_exposes_browser_profile_resolution() -> None:
    run = _browser_run(
        run_id="run-browser-1",
        tool_id="browser.navigate",
        call_id="call-browser-1",
        source_id="bundled.local_package.browser",
        input_payload={"url": "https://example.com"},
    )
    run.start()
    run.succeed(
        ToolRunResult.text(
            "Browser tab opened.",
            details={
                "command": {
                    "kind": "open-tab",
                    "profile_name": "user",
                },
            },
            metadata={
                "tool": "browser.navigate",
                "family": "control",
                "profile_name": "user",
                "profile_source": "browser.default_profile",
                "browser_profile_pool": "collector",
                "browser_allocation_id": "browser_alloc_1",
                "browser_host_service_key": "host:browser:user",
                "browser_target_host": "example.com",
                "browser_host_generation": "host-gen-1",
                "browser_target_id": "tab-1",
                "browser_page_generation": 2,
                "browser_snapshot_generation": 4,
                "browser_current_ref_generation": 4,
                "kind": "open-tab",
            },
        ),
    )

    page = ToolOperationsReadModelProvider(
        tool_service=_ToolService(runs=(run,)),
    ).page()

    row = page.tool_runs.rows[0]
    assert row.cells["call_id"] == "call-browser-1"
    assert row.cells["tool_surface_id"] == "tool_surface:browser"
    assert row.cells["browser"] == "user · pool:collector · alloc:browser_alloc_1 · example.com"
    detail = page.tool_run_details[0]
    summary = {item.label: item.value for item in detail.summary}
    assert summary["Call ID"] == "call-browser-1"
    assert summary["ToolSurface"] == "tool_surface:browser"
    assert summary["Browser Profile"] == "user"
    assert summary["Profile Source"] == "browser.default_profile"
    assert summary["Browser Profile Pool"] == "collector"
    assert summary["Browser Allocation"] == "browser_alloc_1"
    assert summary["Host Service"] == "host:browser:user"
    assert summary["Target Host"] == "example.com"
    assert summary["Host Generation"] == "host-gen-1"
    assert summary["Target"] == "tab-1"
    assert summary["Page Generation"] == "2"
    assert summary["Snapshot Generation"] == "4"
    assert summary["Ref Generation"] == "4"
