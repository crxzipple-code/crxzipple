from __future__ import annotations

from types import SimpleNamespace

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

    def list_tools(self):
        return ()

    def list_enabled_tools(self):
        return ()

    def list_tool_runs(self):
        return self._runs

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


def test_tool_operations_source_health_exposes_single_browser_source() -> None:
    source = browser_source_records_from_package()[0]
    functions = tuple(
        ToolFunctionCatalogRecord.from_candidate(candidate)
        for candidate in browser_function_catalog_candidates()
    )

    page = ToolOperationsReadModelProvider(
        tool_service=_ToolService(sources=(source,), functions=functions),
    ).page()

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
    run = ToolRun.create(
        run_id="run-browser-1",
        tool_id="browser.navigate",
        function_id="browser.navigate",
        source_id="bundled.local_package.browser",
        input_payload={"url": "https://example.com"},
        target=ToolExecutionTarget(
            mode=ToolMode.INLINE,
            strategy=ToolExecutionStrategy.ASYNC,
            environment=ToolEnvironment.LOCAL,
        ),
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
    assert row.cells["browser"] == "user · pool:collector · alloc:browser_alloc_1 · example.com"
    detail = page.tool_run_details[0]
    summary = {item.label: item.value for item in detail.summary}
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
