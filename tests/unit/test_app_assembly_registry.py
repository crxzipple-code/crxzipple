from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from crxzipple.app.assembly.lifecycle import (
    BROWSER_CLEANUP_ORDER,
    DATABASE_CLEANUP_ORDER,
    EVENTS_CLEANUP_ORDER,
    HTTP_CLIENTS_CLEANUP_ORDER,
    MEMORY_WATCHER_CLEANUP_ORDER,
    PROCESS_CLEANUP_ORDER,
    TOOL_CLEANUP_ORDER,
    runtime_lifecycle_factories,
)
from crxzipple.app import (
    ActivationTask,
    AppContainer,
    AppKey,
    ApplicationDependencyCycleError,
    ApplicationFactory,
    AssemblyPlan,
    AssemblyTarget,
    DuplicateApplicationProviderError,
    MissingApplicationDependencyError,
    RuntimeCleanupError,
    RuntimeCleanupTask,
    UnknownApplicationError,
    build_app_container,
)


@dataclass(frozen=True)
class PlainApplication:
    value: str


def test_builds_factories_in_dependency_order_without_framework_base() -> None:
    events: list[str] = []

    plan = AssemblyPlan.from_factories(
        (
            ApplicationFactory(
                key="integration",
                provides=("integration",),
                requires=("module.local",),
                build=lambda ctx: events.append("integration")
                or PlainApplication(ctx.require("module.local").value + "+wired"),
            ),
            ApplicationFactory(
                key="module",
                provides=("module.local",),
                build=lambda _ctx: events.append("module")
                or PlainApplication("plain"),
            ),
        )
    )

    container = build_app_container(plan, target=AssemblyTarget.TEST)

    assert isinstance(container, AppContainer)
    assert container.require("integration") == PlainApplication("plain+wired")
    assert events == ["module", "integration"]


def test_runs_activation_tasks_after_required_applications_exist() -> None:
    activated: list[str] = []
    plan = AssemblyPlan(
        module_local_factories=(
            ApplicationFactory(
                key="settings",
                provides=("settings.service",),
                build=lambda _ctx: PlainApplication("settings"),
            ),
        ),
        activation_tasks=(
            ActivationTask(
                key="seed-settings",
                requires=("settings.service",),
                run=lambda ctx: activated.append(
                    ctx.require("settings.service").value
                ),
            ),
        ),
    )

    build_app_container(plan, target="test")

    assert activated == ["settings"]


def test_overrides_supply_fakes_without_module_code_changes() -> None:
    fake = PlainApplication("fake-access")
    plan = AssemblyPlan.from_factories(
        (
            ApplicationFactory(
                key="llm",
                provides=("llm.service",),
                requires=("access.credentials",),
                build=lambda ctx: PlainApplication(
                    f"llm-with-{ctx.require('access.credentials').value}"
                ),
            ),
        )
    )

    container = build_app_container(
        plan,
        target=AssemblyTarget.TEST,
        overrides={"access.credentials": fake},
    )

    assert container.require("llm.service") == PlainApplication("llm-with-fake-access")


def test_override_shadows_active_factory_provider() -> None:
    built: list[str] = []
    plan = AssemblyPlan.from_factories(
        (
            ApplicationFactory(
                key="real-access",
                provides=("access.credentials",),
                build=lambda _ctx: built.append("real") or PlainApplication("real"),
            ),
        )
    )

    container = build_app_container(
        plan,
        target=AssemblyTarget.TEST,
        overrides={"access.credentials": PlainApplication("fake")},
    )

    assert container.require("access.credentials") == PlainApplication("fake")
    assert built == []


def test_override_cannot_partially_shadow_multi_provider_factory() -> None:
    plan = AssemblyPlan.from_factories(
        (
            ApplicationFactory(
                key="core",
                provides=("one", "two"),
                build=lambda _ctx: {"one": PlainApplication("1")},
            ),
        )
    )

    with pytest.raises(DuplicateApplicationProviderError, match="partially shadows"):
        build_app_container(
            plan,
            target=AssemblyTarget.TEST,
            overrides={"one": PlainApplication("fake")},
        )


def test_missing_factory_dependency_fails_before_building_any_factory() -> None:
    built: list[str] = []
    plan = AssemblyPlan.from_factories(
        (
            ApplicationFactory(
                key="needs-access",
                provides=("llm.service",),
                requires=("access.credentials",),
                build=lambda _ctx: built.append("llm") or PlainApplication("llm"),
            ),
        )
    )

    with pytest.raises(MissingApplicationDependencyError) as error:
        build_app_container(plan, target=AssemblyTarget.TEST)

    assert error.value.owner_key == "needs-access"
    assert error.value.dependency_key == "access.credentials"
    assert built == []


def test_missing_activation_dependency_fails_before_building_any_factory() -> None:
    built: list[str] = []
    plan = AssemblyPlan(
        module_local_factories=(
            ApplicationFactory(
                key="settings",
                provides=("settings.service",),
                build=lambda _ctx: built.append("settings")
                or PlainApplication("settings"),
            ),
        ),
        activation_tasks=(
            ActivationTask(
                key="activate-tools",
                requires=("tool.catalog",),
                run=lambda _ctx: None,
            ),
        ),
    )

    with pytest.raises(MissingApplicationDependencyError) as error:
        build_app_container(plan, target=AssemblyTarget.TEST)

    assert error.value.owner_key == "activate-tools"
    assert error.value.dependency_key == "tool.catalog"
    assert built == []


def test_dependency_cycle_fails_with_diagnostic_path() -> None:
    plan = AssemblyPlan.from_factories(
        (
            ApplicationFactory(
                key="agent",
                provides=("agent.service",),
                requires=("tool.service",),
                build=lambda _ctx: PlainApplication("agent"),
            ),
            ApplicationFactory(
                key="tool",
                provides=("tool.service",),
                requires=("agent.service",),
                build=lambda _ctx: PlainApplication("tool"),
            ),
        )
    )

    with pytest.raises(ApplicationDependencyCycleError) as error:
        build_app_container(plan, target=AssemblyTarget.TEST)

    assert error.value.cycle == ("agent", "tool", "agent")
    assert "agent -> tool -> agent" in str(error.value)


def test_target_filtering_loads_only_active_factories_and_tasks() -> None:
    activated: list[str] = []
    plan = AssemblyPlan(
        module_local_factories=(
            ApplicationFactory(
                key="api-only",
                provides=("api.service",),
                targets=(AssemblyTarget.API,),
                build=lambda _ctx: PlainApplication("api"),
            ),
            ApplicationFactory(
                key="worker-only",
                provides=("worker.service",),
                targets=(AssemblyTarget.TOOL_WORKER,),
                build=lambda _ctx: PlainApplication("worker"),
            ),
        ),
        activation_tasks=(
            ActivationTask(
                key="worker-activation",
                requires=("worker.service",),
                targets=(AssemblyTarget.TOOL_WORKER,),
                run=lambda _ctx: activated.append("worker"),
            ),
        ),
    )

    api_container = build_app_container(plan, target=AssemblyTarget.API)
    worker_container = build_app_container(plan, target=AssemblyTarget.TOOL_WORKER)

    assert api_container.has("api.service")
    assert not api_container.has("worker.service")
    assert worker_container.has("worker.service")
    assert not worker_container.has("api.service")
    assert activated == ["worker"]


def test_event_relay_worker_is_an_explicit_runtime_target() -> None:
    plan = AssemblyPlan.from_factories(
        (
            ApplicationFactory(
                key="event-relay",
                provides=("event-relay.runtime",),
                targets=(AssemblyTarget.EVENT_RELAY_WORKER,),
                build=lambda _ctx: PlainApplication("event-relay"),
            ),
        )
    )

    relay_container = build_app_container(plan, target="event-relay-worker")
    api_container = build_app_container(plan, target=AssemblyTarget.API)

    assert relay_container.require("event-relay.runtime") == PlainApplication(
        "event-relay"
    )
    assert not api_container.has("event-relay.runtime")


def test_multiple_provides_require_mapping_result() -> None:
    plan = AssemblyPlan.from_factories(
        (
            ApplicationFactory(
                key="core",
                provides=("one", "two"),
                build=lambda _ctx: {
                    "one": PlainApplication("1"),
                    "two": PlainApplication("2"),
                },
            ),
        )
    )

    container = build_app_container(plan, target=AssemblyTarget.TEST)

    assert container.require("one") == PlainApplication("1")
    assert container.require("two") == PlainApplication("2")


def test_unknown_runtime_lookup_fails_explicitly() -> None:
    container = build_app_container(AssemblyPlan(), target=AssemblyTarget.TEST)

    with pytest.raises(UnknownApplicationError, match="missing"):
        container.require("missing")


def test_container_close_runs_registered_runtime_cleanup_tasks_in_order() -> None:
    closed: list[str] = []
    plan = AssemblyPlan.from_factories(
        (
            ApplicationFactory(
                key="runtime-cleanup",
                provides=(AppKey.RUNTIME_CLEANUP_TASKS,),
                build=lambda _ctx: (
                    RuntimeCleanupTask(
                        key="second",
                        order=20,
                        callback=lambda: closed.append("second"),
                    ),
                    RuntimeCleanupTask(
                        key="first",
                        order=10,
                        callback=lambda: closed.append("first"),
                    ),
                ),
            ),
        )
    )

    container = build_app_container(plan, target=AssemblyTarget.TEST)

    container.close()

    assert closed == ["first", "second"]


def test_container_close_isolates_cleanup_failures_until_all_tasks_run() -> None:
    closed: list[str] = []

    def fail() -> None:
        closed.append("failed")
        raise ValueError("simulated cleanup failure")

    plan = AssemblyPlan.from_factories(
        (
            ApplicationFactory(
                key="runtime-cleanup",
                provides=(AppKey.RUNTIME_CLEANUP_TASKS,),
                build=lambda _ctx: (
                    RuntimeCleanupTask(
                        key="first",
                        order=10,
                        callback=lambda: closed.append("first"),
                    ),
                    RuntimeCleanupTask(key="broken", order=20, callback=fail),
                    RuntimeCleanupTask(
                        key="last",
                        order=30,
                        callback=lambda: closed.append("last"),
                    ),
                ),
            ),
        )
    )

    container = build_app_container(plan, target=AssemblyTarget.TEST)

    with pytest.raises(RuntimeCleanupError) as error:
        container.close()

    assert closed == ["first", "failed", "last"]
    assert [failure.key for failure in error.value.failures] == ["broken"]
    assert isinstance(error.value.failures[0].error, ValueError)


def test_runtime_lifecycle_factory_declares_stable_cleanup_order() -> None:
    class _Closeable:
        def close(self) -> None:
            pass

    class _Engine:
        def dispose(self) -> None:
            pass

    container = build_app_container(
        AssemblyPlan.from_factories(runtime_lifecycle_factories()),
        target=AssemblyTarget.TEST,
        overrides={
            AppKey.TOOL_CLEANUP_CALLBACKS: (lambda: None,),
            AppKey.BROWSER_INFRASTRUCTURE: SimpleNamespace(
                cleanup_callbacks=(lambda: None, lambda: None),
            ),
            AppKey.PROCESS_SERVICE: _Closeable(),
            AppKey.MEMORY_WATCH_REGISTRY: _Closeable(),
            AppKey.EVENTS_SERVICE: _Closeable(),
            AppKey.DATABASE_ENGINE: _Engine(),
        },
    )

    tasks = container.require(AppKey.RUNTIME_CLEANUP_TASKS)

    assert [(task.key, task.order) for task in tasks] == [
        ("tool.cleanup.0", TOOL_CLEANUP_ORDER),
        ("browser.cleanup.0", BROWSER_CLEANUP_ORDER),
        ("browser.cleanup.1", BROWSER_CLEANUP_ORDER),
        ("process.service.close", PROCESS_CLEANUP_ORDER),
        ("memory.watch_registry.close", MEMORY_WATCHER_CLEANUP_ORDER),
        ("events.service.close", EVENTS_CLEANUP_ORDER),
        ("shared.http_clients.close", HTTP_CLIENTS_CLEANUP_ORDER),
        ("database.engine.dispose", DATABASE_CLEANUP_ORDER),
    ]
