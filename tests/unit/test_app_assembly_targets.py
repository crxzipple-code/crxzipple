from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from crxzipple.app import AppKey
from crxzipple.app.assembly.daemon import build_runtime_daemon_specs
from crxzipple.app.assembly.runtime import runtime_plan
from crxzipple.app.assembly.tool import (
    browser_function_catalog_candidates,
    browser_source_records_from_system_config,
)
from crxzipple.app.assembly.targets import (
    ALL_TARGET_ENTRYPOINTS,
    DAEMON_SERVICE_TARGETS,
    ENTRYPOINTS_BY_TARGET,
    UnknownDaemonServiceTargetError,
    all_runtime_targets,
    entrypoint_for_target,
    target_for_daemon_service,
)
from crxzipple.app.plan import AssemblyTarget
from crxzipple.interfaces.runtime_container import (
    MEMORY_WATCHER_TARGETS,
    memory_watchers_enabled_for_target,
)
from crxzipple.modules.daemon.application.services import DEFAULT_DAEMON_SERVICE_SETS

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_entrypoint_metadata_covers_every_assembly_target() -> None:
    assert set(ENTRYPOINTS_BY_TARGET) == set(AssemblyTarget)
    assert len(ALL_TARGET_ENTRYPOINTS) == len(AssemblyTarget)
    assert all_runtime_targets() == (
        AssemblyTarget.API,
        AssemblyTarget.CLI_ADMIN,
        AssemblyTarget.DAEMON_SUPERVISOR,
        AssemblyTarget.ORCHESTRATION_SCHEDULER,
        AssemblyTarget.ORCHESTRATION_EXECUTOR,
        AssemblyTarget.TOOL_SCHEDULER,
        AssemblyTarget.TOOL_WORKER,
        AssemblyTarget.OPERATIONS_OBSERVER,
        AssemblyTarget.EVENT_RELAY_WORKER,
        AssemblyTarget.CHANNEL_RUNTIME,
    )


def test_known_daemon_services_map_to_runtime_targets() -> None:
    assert DAEMON_SERVICE_TARGETS == {
        "worker:orchestration-scheduler": AssemblyTarget.ORCHESTRATION_SCHEDULER,
        "worker:orchestration": AssemblyTarget.ORCHESTRATION_EXECUTOR,
        "worker:tool-scheduler": AssemblyTarget.TOOL_SCHEDULER,
        "worker:tool": AssemblyTarget.TOOL_WORKER,
        "worker:operations-observer": AssemblyTarget.OPERATIONS_OBSERVER,
        "worker:event-relay": AssemblyTarget.EVENT_RELAY_WORKER,
    }
    assert target_for_daemon_service("channel:web") is AssemblyTarget.CHANNEL_RUNTIME
    assert target_for_daemon_service("channel:lark") is AssemblyTarget.CHANNEL_RUNTIME


def test_daemon_service_sets_only_reference_known_runtime_targets() -> None:
    service_keys = {
        service_key
        for service_set in DEFAULT_DAEMON_SERVICE_SETS
        for service_key in service_set.service_keys
    }

    assert service_keys
    for service_key in service_keys:
        assert target_for_daemon_service(service_key) in set(all_runtime_targets())


def test_runtime_daemon_specs_match_entrypoint_target_metadata() -> None:
    specs = build_runtime_daemon_specs(
        settings=SimpleNamespace(
            ocr_enabled=False,
            ocr_backend="local",
            ocr_provider="host",
            ocr_base_url="http://127.0.0.1:8001",
        ),
        browser_system_config=SimpleNamespace(profiles=()),
        runtime_bootstrap_config=SimpleNamespace(
            orchestration_executor_max_concurrent_assignments=1,
            tool_worker_max_in_flight=4,
        ),
    )
    specs_by_key = {spec.key: spec for spec in specs}

    assert set(DAEMON_SERVICE_TARGETS).issubset(specs_by_key)
    for service_key, target in DAEMON_SERVICE_TARGETS.items():
        cli_args = tuple(specs_by_key[service_key].metadata["cli_args"])
        assert cli_args[: len(entrypoint_for_target(target).cli_args)] == (
            entrypoint_for_target(target).cli_args
        )
        assert target_for_daemon_service(service_key) is target


def test_browser_host_daemon_spec_carries_profile_runtime_metadata() -> None:
    specs = build_runtime_daemon_specs(
        settings=SimpleNamespace(
            ocr_enabled=False,
            ocr_backend="local",
            ocr_provider="host",
            ocr_base_url="http://127.0.0.1:8001",
        ),
        browser_system_config=SimpleNamespace(
            cdp_host="127.0.0.1",
            profiles=(
                SimpleNamespace(
                    name="work",
                    driver="managed",
                    attach_only=False,
                    cdp_url=None,
                    cdp_port=18800,
                    user_data_dir="/tmp/crx-browser-work",
                    profile_directory="Profile 1",
                    autostart=True,
                    proxy_mode="static",
                    proxy_server="socks5://127.0.0.1:7890",
                    proxy_bypass_list=("127.0.0.1", "localhost"),
                    proxy_binding_id=None,
                    proxy_credential_kind="bearer_token",
                ),
            ),
        ),
        runtime_bootstrap_config=SimpleNamespace(
            orchestration_executor_max_concurrent_assignments=1,
            tool_worker_max_in_flight=4,
        ),
    )

    spec = next(item for item in specs if item.key == "host:browser:work")

    assert spec.metadata["profile_directory"] == "Profile 1"
    assert spec.metadata["user_data_dir"] == "/tmp/crx-browser-work"
    assert spec.metadata["autostart"] is True
    assert spec.metadata["proxy_mode"] == "static"
    assert spec.metadata["proxy_server"] == "socks5://127.0.0.1:7890"
    assert spec.metadata["proxy_bypass_list"] == ["127.0.0.1", "localhost"]
    assert spec.metadata["proxy_credential_kind"] == "bearer_token"


def test_browser_profile_daemon_specs_do_not_create_mcp_services() -> None:
    specs = build_runtime_daemon_specs(
        settings=SimpleNamespace(
            ocr_enabled=False,
            ocr_backend="local",
            ocr_provider="host",
            ocr_base_url="http://127.0.0.1:8001",
        ),
        browser_system_config=SimpleNamespace(
            cdp_host="127.0.0.1",
            cdp_port_range_start=18800,
            profiles=(
                SimpleNamespace(
                    name="user",
                    driver="existing-session",
                    attach_only=True,
                    cdp_url="http://127.0.0.1:9222",
                    cdp_port=None,
                    user_data_dir=None,
                    profile_directory=None,
                    autostart=False,
                    proxy_mode="none",
                    proxy_server=None,
                    proxy_bypass_list=(),
                    proxy_binding_id=None,
                ),
                SimpleNamespace(
                    name="crxzipple",
                    driver="managed",
                    attach_only=False,
                    cdp_url=None,
                    cdp_port=18800,
                    user_data_dir="/tmp/crx-browser-work",
                    profile_directory=None,
                    autostart=True,
                    proxy_mode="none",
                    proxy_server=None,
                    proxy_bypass_list=(),
                    proxy_binding_id=None,
                ),
            ),
        ),
        runtime_bootstrap_config=SimpleNamespace(
            orchestration_executor_max_concurrent_assignments=1,
            tool_worker_max_in_flight=4,
        ),
    )

    specs_by_key = {spec.key: spec for spec in specs}

    assert "host:browser:user" in specs_by_key
    assert "host:browser:crxzipple" in specs_by_key
    assert "mcp:browser:user" not in specs_by_key
    assert "mcp:browser:crxzipple" not in specs_by_key
    assert not any(spec.key.startswith("mcp:browser:") for spec in specs)

    user_spec = specs_by_key["host:browser:user"]
    assert user_spec.managed_by == "external"
    assert user_spec.transport == "endpoint"
    assert user_spec.start_policy == "attach-only"
    assert user_spec.metadata["server_url"] == "http://127.0.0.1:9222"

    managed_spec = specs_by_key["host:browser:crxzipple"]
    assert managed_spec.managed_by == "internal"
    assert managed_spec.transport == "process"
    assert managed_spec.metadata["server_url"] == "http://127.0.0.1:18800"


def test_daemon_assembly_does_not_clean_browser_mcp_in_activation_path() -> None:
    assembly_source = (
        REPO_ROOT / "src" / "crxzipple" / "app" / "assembly" / "daemon.py"
    ).read_text(encoding="utf-8")

    assert "mcp:browser:" not in assembly_source


def test_browser_source_catalog_is_not_tied_to_profile_mcp_ports() -> None:
    browser_system_config = SimpleNamespace(
        cdp_host="127.0.0.1",
        cdp_port_range_start=65_000,
        profiles=(
            SimpleNamespace(
                name="high",
                driver="managed",
                attach_only=False,
                cdp_url=None,
                cdp_port=65_000,
                user_data_dir="/tmp/crx-browser-high",
                profile_directory=None,
                autostart=True,
                proxy_mode="none",
                proxy_server=None,
                proxy_bypass_list=(),
                proxy_binding_id=None,
            ),
        ),
    )

    specs = build_runtime_daemon_specs(
        settings=SimpleNamespace(
            ocr_enabled=False,
            ocr_backend="local",
            ocr_provider="host",
            ocr_base_url="http://127.0.0.1:8001",
        ),
        browser_system_config=browser_system_config,
        runtime_bootstrap_config=SimpleNamespace(
            orchestration_executor_max_concurrent_assignments=1,
            tool_worker_max_in_flight=4,
        ),
    )
    sources = browser_source_records_from_system_config(browser_system_config)

    keys = {spec.key for spec in specs}
    assert "host:browser:high" in keys
    assert "mcp:browser:high" not in keys
    assert [source.source_id for source in sources] == ["configured.browser"]
    assert not any(
        source.source_id.startswith("configured.mcp.browser_") for source in sources
    )


def test_browser_tool_source_registers_single_profile_context_source() -> None:
    sources = browser_source_records_from_system_config(
        SimpleNamespace(
            cdp_host="127.0.0.1",
            cdp_port_range_start=18800,
            profiles=(
                SimpleNamespace(
                    name="work",
                    driver="managed",
                    cdp_url=None,
                    cdp_port=18800,
                ),
                SimpleNamespace(
                    name="user",
                    driver="existing-session",
                    cdp_url="http://127.0.0.1:9222",
                    cdp_port=None,
                ),
            ),
        ),
    )

    assert [source.source_id for source in sources] == ["configured.browser"]
    source = sources[0]
    assert source.display_name == "Browser"
    assert source.config["provider"] == "crxzipple.browser"
    assert source.config["profile_mode"] == "runtime_context"
    assert source.config["default_profile_source"] == "browser_system_config"
    assert source.config["function_prefix"] == "browser."
    assert source.config["runtime_requirement"] == "browser-profile-runtime"
    assert source.runtime_requirements == ("browser-profile-runtime",)
    assert "browser_profile" not in source.config


def test_browser_function_catalog_uses_profile_context_not_profile_ids() -> None:
    candidates = browser_function_catalog_candidates()
    function_ids = [candidate.function_id for candidate in candidates]

    assert function_ids == [
        "browser.snapshot",
        "browser.navigate",
        "browser.click",
        "browser.type",
        "browser.evaluate",
        "browser.screenshot",
        "browser.dom.inspect",
        "browser.dom.box_model",
        "browser.dom.computed_style",
        "browser.dom.clickability",
        "browser.dom.highlight",
        "browser.dom.mutation_wait",
        "browser.storage.indexeddb.list",
        "browser.storage.indexeddb.query",
        "browser.storage.indexeddb.get",
        "browser.storage.cache.list",
        "browser.storage.cache.get",
        "browser.service_worker.list",
        "browser.service_worker.inspect",
        "browser.emulation.set",
        "browser.emulation.reset",
        "browser.permissions.grant",
        "browser.permissions.clear",
        "browser.geolocation.set",
        "browser.network_conditions.set",
        "browser.diagnostics.collect",
        "browser.performance.metrics",
        "browser.trace.start",
        "browser.trace.stop",
        "browser.trace.export",
        "browser.page.lifecycle",
        "browser.page.errors",
        "browser.context.acquire",
        "browser.context.current",
        "browser.context.heartbeat",
        "browser.context.release",
        "browser.context.reconcile",
        "browser.network.start_capture",
        "browser.network.stop_capture",
        "browser.network.list_requests",
        "browser.network.get_request",
        "browser.network.get_response_body",
        "browser.network.get_request_body",
        "browser.network.fetch_as_page",
        "browser.network.replay_request",
        "browser.network.clear_capture",
        "browser.tabs.list",
        "browser.tabs.select",
        "browser.tabs.close",
    ]
    assert "configured.mcp.browser_user" not in {
        candidate.source_id for candidate in candidates
    }
    assert "configured.mcp.browser_crxzipple" not in {
        candidate.source_id for candidate in candidates
    }
    assert not any("browser_user" in function_id for function_id in function_ids)
    assert not any("browser_crxzipple" in function_id for function_id in function_ids)
    for candidate in candidates:
        assert candidate.source_id == "configured.browser"
        assert candidate.function_id.startswith("browser.")
        assert candidate.input_schema["properties"]["profile"]["type"] == "string"
        assert candidate.metadata["runtime_requirement"] == "browser-profile-runtime"
        runtime_requirements = candidate.requirements.runtime_requirement_sets
        assert runtime_requirements == (("browser-profile-runtime",),)
        assert not any(
            requirement.startswith("daemon:mcp:browser:")
            for requirement_set in runtime_requirements
            for requirement in requirement_set
        )


def test_existing_session_daemon_spec_uses_attach_only_browser_host() -> None:
    specs = build_runtime_daemon_specs(
        settings=SimpleNamespace(
            ocr_enabled=False,
            ocr_backend="local",
            ocr_provider="host",
            ocr_base_url="http://127.0.0.1:8001",
        ),
        browser_system_config=SimpleNamespace(
            cdp_host="127.0.0.1",
            cdp_port_range_start=9222,
            profiles=(
                SimpleNamespace(
                    name="user",
                    driver="existing-session",
                    attach_only=True,
                    cdp_url="http://127.0.0.1:9222",
                    cdp_port=None,
                    user_data_dir=None,
                    profile_directory=None,
                    autostart=False,
                    proxy_mode="none",
                    proxy_server=None,
                    proxy_bypass_list=(),
                    proxy_binding_id=None,
                ),
            ),
        ),
        runtime_bootstrap_config=SimpleNamespace(
            orchestration_executor_max_concurrent_assignments=1,
            tool_worker_max_in_flight=4,
        ),
    )

    keys = {spec.key for spec in specs}
    assert "capability:chrome-mcp:user" not in keys
    assert "mcp:browser:user" not in keys
    spec = next(item for item in specs if item.key == "host:browser:user")
    assert spec.managed_by == "external"
    assert spec.transport == "endpoint"
    assert spec.start_policy == "attach-only"
    assert spec.restart_policy == "manual"
    assert spec.metadata["cdp_url"] == "http://127.0.0.1:9222"
    assert spec.metadata["server_url"] == "http://127.0.0.1:9222"


def test_existing_session_daemon_spec_does_not_allocate_implicit_cdp_endpoint() -> None:
    specs = build_runtime_daemon_specs(
        settings=SimpleNamespace(
            ocr_enabled=False,
            ocr_backend="local",
            ocr_base_url="http://127.0.0.1:8001",
            ocr_provider="host",
        ),
        browser_system_config=SimpleNamespace(
            cdp_host="127.0.0.1",
            cdp_port_range_start=18800,
            profiles=(
                SimpleNamespace(
                    name="crxzipple",
                    driver="managed",
                    attach_only=False,
                    cdp_url=None,
                    cdp_port=18800,
                    user_data_dir="/tmp/crx-browser-work",
                    profile_directory=None,
                    autostart=True,
                    proxy_mode="none",
                    proxy_server=None,
                    proxy_bypass_list=(),
                    proxy_binding_id=None,
                ),
                SimpleNamespace(
                    name="user",
                    driver="existing-session",
                    attach_only=True,
                    cdp_url=None,
                    cdp_port=None,
                    user_data_dir=None,
                    profile_directory=None,
                    autostart=False,
                    proxy_mode="none",
                    proxy_server=None,
                    proxy_bypass_list=(),
                    proxy_binding_id=None,
                ),
            ),
        ),
        runtime_bootstrap_config=SimpleNamespace(
            orchestration_executor_max_concurrent_assignments=1,
            tool_worker_max_in_flight=4,
        ),
    )

    spec = next(item for item in specs if item.key == "host:browser:user")

    assert spec.managed_by == "external"
    assert spec.transport == "endpoint"
    assert spec.start_policy == "attach-only"
    assert spec.metadata["cdp_url"] is None
    assert spec.metadata["cdp_port"] is None
    assert spec.metadata["server_url"] is None


def test_memory_watcher_policy_is_target_owned() -> None:
    assert MEMORY_WATCHER_TARGETS == frozenset(
        {
            AssemblyTarget.API,
            AssemblyTarget.ORCHESTRATION_SCHEDULER,
            AssemblyTarget.ORCHESTRATION_EXECUTOR,
        }
    )
    for target in AssemblyTarget:
        assert memory_watchers_enabled_for_target(target) is (
            target in MEMORY_WATCHER_TARGETS
        )


def test_event_relay_worker_is_an_independent_target() -> None:
    metadata = entrypoint_for_target(AssemblyTarget.EVENT_RELAY_WORKER)

    assert metadata.target is AssemblyTarget.EVENT_RELAY_WORKER
    assert metadata.daemon_service_key == "worker:event-relay"
    assert metadata.cli_args == ("event-relay", "run")
    assert target_for_daemon_service("worker:event-relay") is (
        AssemblyTarget.EVENT_RELAY_WORKER
    )
    assert target_for_daemon_service("worker:operations-observer") is (
        AssemblyTarget.OPERATIONS_OBSERVER
    )


def test_unknown_daemon_service_target_fails_fast() -> None:
    with pytest.raises(
        UnknownDaemonServiceTargetError,
        match="Unknown daemon service assembly target",
    ):
        target_for_daemon_service("mcp:browser:user")


def test_runtime_plan_scopes_sidecar_services_to_worker_targets() -> None:
    plan = runtime_plan()
    factories_by_key = {factory.key: factory for factory in plan.factories}
    tasks_by_key = {task.key: task for task in plan.activation_tasks}

    assert factories_by_key["tool.queue_services"].targets == (
        AssemblyTarget.TOOL_SCHEDULER,
        AssemblyTarget.OPERATIONS_OBSERVER,
        AssemblyTarget.EVENT_RELAY_WORKER,
        AssemblyTarget.CHANNEL_RUNTIME,
    )
    assert factories_by_key["tool.orchestration_queue_services"].targets == (
        AssemblyTarget.ORCHESTRATION_SCHEDULER,
    )
    assert factories_by_key["tool.execution_services"].targets == (
        AssemblyTarget.API,
        AssemblyTarget.CLI_ADMIN,
        AssemblyTarget.ORCHESTRATION_EXECUTOR,
        AssemblyTarget.TOOL_WORKER,
        AssemblyTarget.TEST,
    )
    assert factories_by_key["orchestration.runtime"].targets == (
        AssemblyTarget.API,
        AssemblyTarget.CLI_ADMIN,
    )
    assert factories_by_key["orchestration.test_runtime"].targets == (
        AssemblyTarget.TEST,
    )
    assert factories_by_key["orchestration.scheduler_runtime"].targets == (
        AssemblyTarget.ORCHESTRATION_SCHEDULER,
    )
    assert factories_by_key["orchestration.executor_runtime"].targets == (
        AssemblyTarget.ORCHESTRATION_EXECUTOR,
    )
    assert factories_by_key["orchestration.run_query_service"].targets == (
        AssemblyTarget.EVENT_RELAY_WORKER,
        AssemblyTarget.OPERATIONS_OBSERVER,
        AssemblyTarget.TOOL_WORKER,
        AssemblyTarget.CHANNEL_RUNTIME,
        AssemblyTarget.ORCHESTRATION_EXECUTOR,
    )
    assert factories_by_key["orchestration.submission_service"].targets == (
        AssemblyTarget.CHANNEL_RUNTIME,
    )
    assert factories_by_key["orchestration.ingress_runtime_service"].targets == (
        AssemblyTarget.ORCHESTRATION_EXECUTOR,
        AssemblyTarget.TOOL_WORKER,
    )
    assert factories_by_key["orchestration.cancellation_service"].targets == (
        AssemblyTarget.ORCHESTRATION_EXECUTOR,
        AssemblyTarget.TOOL_WORKER,
    )
    assert factories_by_key["session.runtime_control"].targets == (
        AssemblyTarget.API,
        AssemblyTarget.CLI_ADMIN,
        AssemblyTarget.TEST,
    )
    assert factories_by_key["session.ingress_runtime_control"].targets == (
        AssemblyTarget.ORCHESTRATION_EXECUTOR,
        AssemblyTarget.TOOL_WORKER,
    )
    assert factories_by_key["orchestration.scheduler_runtime_event_service"].targets == (
        AssemblyTarget.ORCHESTRATION_SCHEDULER,
        AssemblyTarget.TEST,
    )
    assert factories_by_key["orchestration.run_enqueued_callback_binding"].targets == (
        AssemblyTarget.API,
        AssemblyTarget.TEST,
    )
    assert factories_by_key[
        "orchestration.scheduler_run_enqueued_callback_binding"
    ].targets == (
        AssemblyTarget.ORCHESTRATION_SCHEDULER,
    )
    assert factories_by_key["event_relay.runtime_event_service"].targets == (
        AssemblyTarget.EVENT_RELAY_WORKER,
        AssemblyTarget.TEST,
    )
    assert factories_by_key["tool.runtime_event_service"].targets == (
        AssemblyTarget.TOOL_WORKER,
        AssemblyTarget.TEST,
    )
    assert factories_by_key["operations.observer_runtime_event_service"].targets == (
        AssemblyTarget.OPERATIONS_OBSERVER,
        AssemblyTarget.TEST,
    )
    assert factories_by_key["channels.runtime_services"].targets == (
        AssemblyTarget.API,
        AssemblyTarget.CHANNEL_RUNTIME,
        AssemblyTarget.TEST,
    )
    assert factories_by_key["runtime.cleanup_tasks"].provides == (
        AppKey.RUNTIME_CLEANUP_TASKS,
    )
    assert tasks_by_key["agent.bootstrap_profiles"].targets == (
        AssemblyTarget.API,
        AssemblyTarget.CLI_ADMIN,
        AssemblyTarget.DAEMON_SUPERVISOR,
        AssemblyTarget.TEST,
    )
    assert tasks_by_key["daemon.bootstrap_specs"].targets == (
        AssemblyTarget.API,
        AssemblyTarget.CLI_ADMIN,
        AssemblyTarget.DAEMON_SUPERVISOR,
        AssemblyTarget.TEST,
    )
    assert tasks_by_key["tool.register_browser_source_catalog"].targets == (
        AssemblyTarget.API,
        AssemblyTarget.CLI_ADMIN,
        AssemblyTarget.ORCHESTRATION_EXECUTOR,
        AssemblyTarget.TOOL_WORKER,
        AssemblyTarget.TEST,
    )


def test_worker_targets_do_not_load_unrelated_sidecar_surfaces() -> None:
    plan = runtime_plan()

    api_keys = _provided_keys(plan, AssemblyTarget.API)
    daemon_keys = _provided_keys(plan, AssemblyTarget.DAEMON_SUPERVISOR)
    orchestration_scheduler_keys = _provided_keys(
        plan,
        AssemblyTarget.ORCHESTRATION_SCHEDULER,
    )
    orchestration_executor_keys = _provided_keys(
        plan,
        AssemblyTarget.ORCHESTRATION_EXECUTOR,
    )
    tool_scheduler_keys = _provided_keys(plan, AssemblyTarget.TOOL_SCHEDULER)
    tool_worker_keys = _provided_keys(plan, AssemblyTarget.TOOL_WORKER)
    channel_runtime_keys = _provided_keys(plan, AssemblyTarget.CHANNEL_RUNTIME)
    event_relay_keys = _provided_keys(plan, AssemblyTarget.EVENT_RELAY_WORKER)
    operations_observer_keys = _provided_keys(plan, AssemblyTarget.OPERATIONS_OBSERVER)

    assert AppKey.TOOL_SERVICE not in daemon_keys
    assert "orchestration.runtime" not in daemon_keys
    assert AppKey.SESSION_RUNTIME_CONTROL not in daemon_keys

    assert AppKey.ORCHESTRATION_SUBMISSION_SERVICE in api_keys
    assert AppKey.ORCHESTRATION_SCHEDULER_MAINTENANCE_SERVICE in api_keys
    assert AppKey.ORCHESTRATION_EXECUTOR_CONTROL_SERVICE in api_keys
    assert AppKey.ORCHESTRATION_RUN_ENQUEUED_CALLBACK_BINDING_SERVICE in api_keys
    assert AppKey.ORCHESTRATION_SCHEDULER_SERVICE not in api_keys
    assert AppKey.ORCHESTRATION_EXECUTOR_SERVICE not in api_keys

    assert AppKey.ORCHESTRATION_SCHEDULER_SERVICE in orchestration_scheduler_keys
    assert AppKey.ORCHESTRATION_RUN_ENQUEUED_CALLBACK_BINDING_SERVICE in (
        orchestration_scheduler_keys
    )
    assert AppKey.ORCHESTRATION_SCHEDULER_RUNTIME_EVENT_SERVICE in (
        orchestration_scheduler_keys
    )
    assert AppKey.ORCHESTRATION_EXECUTOR_SERVICE not in orchestration_scheduler_keys
    assert "orchestration.runtime" not in orchestration_scheduler_keys
    assert AppKey.SESSION_RUNTIME_CONTROL not in orchestration_scheduler_keys

    assert AppKey.ORCHESTRATION_EXECUTOR_SERVICE in orchestration_executor_keys
    assert AppKey.ORCHESTRATION_SCHEDULER_SERVICE not in orchestration_executor_keys
    assert AppKey.ORCHESTRATION_SCHEDULER_RUNTIME_EVENT_SERVICE not in (
        orchestration_executor_keys
    )
    assert "orchestration.runtime" not in orchestration_executor_keys
    assert AppKey.SESSION_RUNTIME_CONTROL in orchestration_executor_keys
    assert AppKey.ORCHESTRATION_SUBMISSION_SERVICE in orchestration_executor_keys
    assert AppKey.ORCHESTRATION_INGRESS_PROCESSING_SERVICE in (
        orchestration_executor_keys
    )
    assert AppKey.ORCHESTRATION_CANCELLATION_SERVICE in orchestration_executor_keys

    assert AppKey.TOOL_SERVICE not in tool_scheduler_keys
    assert AppKey.TOOL_QUERY_SERVICE in tool_scheduler_keys
    assert AppKey.TOOL_ORCHESTRATION_PORT not in tool_scheduler_keys
    assert AppKey.TOOL_SCHEDULER_SERVICE in tool_scheduler_keys
    assert AppKey.TOOL_WORKER_REGISTRY_SERVICE in tool_scheduler_keys
    assert AppKey.TOOL_WORKER_SERVICE not in tool_scheduler_keys
    assert "orchestration.runtime" not in tool_scheduler_keys
    assert AppKey.SESSION_RUNTIME_CONTROL not in tool_scheduler_keys
    assert AppKey.TOOL_RUNTIME_EVENT_SERVICE not in tool_scheduler_keys

    assert AppKey.TOOL_RUNTIME_EVENT_SERVICE in tool_worker_keys
    assert AppKey.TOOL_QUERY_SERVICE in tool_worker_keys
    assert AppKey.TOOL_RUN_CONTROL_SERVICE in tool_worker_keys
    assert AppKey.TOOL_ORCHESTRATION_PORT in tool_worker_keys
    assert AppKey.SESSION_RUNTIME_CONTROL in tool_worker_keys
    assert AppKey.ORCHESTRATION_RUN_QUERY_SERVICE in tool_worker_keys
    assert AppKey.ORCHESTRATION_SUBMISSION_SERVICE in tool_worker_keys
    assert AppKey.ORCHESTRATION_INGRESS_PROCESSING_SERVICE in tool_worker_keys
    assert AppKey.ORCHESTRATION_CANCELLATION_SERVICE in tool_worker_keys
    assert "orchestration.runtime" not in tool_worker_keys
    assert AppKey.ORCHESTRATION_SCHEDULER_SERVICE not in tool_worker_keys
    assert AppKey.ORCHESTRATION_EXECUTOR_SERVICE not in tool_worker_keys
    assert AppKey.EVENT_RELAY_RUNTIME_EVENT_SERVICE not in tool_worker_keys
    assert AppKey.OPERATIONS_OBSERVER_RUNTIME_EVENT_SERVICE not in tool_worker_keys
    assert AppKey.OPERATIONS_PROJECTION_MATERIALIZER not in tool_worker_keys

    assert AppKey.LARK_CHANNEL_RUNTIME_SERVICE in channel_runtime_keys
    assert AppKey.TOOL_QUERY_SERVICE in channel_runtime_keys
    assert AppKey.TOOL_ORCHESTRATION_PORT not in channel_runtime_keys
    assert AppKey.ORCHESTRATION_SUBMISSION_SERVICE in channel_runtime_keys
    assert AppKey.ORCHESTRATION_RUN_QUERY_SERVICE in channel_runtime_keys
    assert "orchestration.runtime" not in channel_runtime_keys
    assert AppKey.ORCHESTRATION_SCHEDULER_SERVICE not in channel_runtime_keys
    assert AppKey.ORCHESTRATION_EXECUTOR_SERVICE not in channel_runtime_keys
    assert AppKey.TOOL_WORKER_SERVICE not in channel_runtime_keys

    assert AppKey.EVENT_RELAY_RUNTIME_EVENT_SERVICE in event_relay_keys
    assert AppKey.TOOL_QUERY_SERVICE in event_relay_keys
    assert AppKey.TOOL_ORCHESTRATION_PORT not in event_relay_keys
    assert AppKey.ORCHESTRATION_RUN_QUERY_SERVICE in event_relay_keys
    assert "orchestration.runtime" not in event_relay_keys
    assert AppKey.ORCHESTRATION_EXECUTOR_SERVICE not in event_relay_keys
    assert AppKey.ORCHESTRATION_SCHEDULER_SERVICE not in event_relay_keys
    assert AppKey.TOOL_WORKER_SERVICE not in event_relay_keys
    assert AppKey.TOOL_RUNTIME_EVENT_SERVICE not in event_relay_keys
    assert AppKey.OPERATIONS_OBSERVER_RUNTIME_EVENT_SERVICE not in event_relay_keys
    assert AppKey.OPERATIONS_PROJECTION_MATERIALIZER not in event_relay_keys

    assert AppKey.OPERATIONS_PROJECTION_MATERIALIZER in operations_observer_keys
    assert AppKey.OPERATIONS_OBSERVER_RUNTIME_EVENT_SERVICE in operations_observer_keys
    assert AppKey.TOOL_QUERY_SERVICE in operations_observer_keys
    assert AppKey.TOOL_ORCHESTRATION_PORT not in operations_observer_keys
    assert AppKey.ORCHESTRATION_RUN_QUERY_SERVICE in operations_observer_keys
    assert "orchestration.runtime" not in operations_observer_keys
    assert AppKey.ORCHESTRATION_EXECUTOR_SERVICE not in operations_observer_keys
    assert AppKey.ORCHESTRATION_SCHEDULER_SERVICE not in operations_observer_keys
    assert AppKey.TOOL_WORKER_SERVICE not in operations_observer_keys
    assert AppKey.LARK_CHANNEL_RUNTIME_SERVICE not in operations_observer_keys
    assert AppKey.WEB_CHANNEL_RUNTIME_SERVICE not in operations_observer_keys
    assert AppKey.WEBHOOK_CHANNEL_RUNTIME_SERVICE not in operations_observer_keys
    assert AppKey.EVENT_RELAY_RUNTIME_EVENT_SERVICE not in operations_observer_keys
    assert AppKey.TOOL_RUNTIME_EVENT_SERVICE not in operations_observer_keys


def _provided_keys(plan, target: AssemblyTarget) -> set[str]:
    return {
        provided
        for factory in plan.factories_for(target)
        for provided in factory.provides
    }
