"""Daemon module app assembly."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from crxzipple.app.assembly.browser_runtime import (
    browser_profile_cdp_endpoint,
    browser_profile_cdp_port,
)
from crxzipple.app.keys import AppKey
from crxzipple.app.plan import ActivationTask, ApplicationFactory, AssemblyTarget
from crxzipple.core.config import PROJECT_ROOT, Settings
from crxzipple.modules.daemon import (
    DaemonApplicationService,
    DaemonManager,
    DaemonServiceSpec,
    FileBackedDaemonInstanceStore,
    FileBackedDaemonLeaseEventLog,
    FileBackedDaemonLeaseStore,
    FileBackedDaemonServiceSpecStore,
    apply_daemon_state_migrations,
    bootstrap_daemon_state_root,
)

DaemonBootstrapSpecsProvider = Callable[[Settings], tuple[DaemonServiceSpec, ...]]


def daemon_factories(
    *,
    bootstrap_specs_provider: DaemonBootstrapSpecsProvider | None = None,
) -> tuple[ApplicationFactory, ...]:
    """Build Daemon module-local service/spec/lease management."""

    provider = bootstrap_specs_provider or _empty_daemon_bootstrap_specs
    return (
        ApplicationFactory(
            key="daemon.service",
            provides=(AppKey.DAEMON_SERVICE,),
            requires=(AppKey.CORE_SETTINGS,),
            build=lambda ctx: _build_daemon_service(ctx, provider),
        ),
    )


def daemon_manager_factories() -> tuple[ApplicationFactory, ...]:
    """Build Daemon + Process runtime manager integration."""

    return (
        ApplicationFactory(
            key="daemon.manager",
            provides=(AppKey.DAEMON_MANAGER,),
            requires=(AppKey.DAEMON_SERVICE, AppKey.PROCESS_SERVICE),
            build=lambda ctx: build_daemon_manager(
                daemon_service=ctx.require(AppKey.DAEMON_SERVICE),
                process_service=ctx.require(AppKey.PROCESS_SERVICE),
            ),
        ),
    )


def daemon_activation_tasks() -> tuple[ActivationTask, ...]:
    """Register runtime daemon service specs after cross-module apps exist."""

    return (
        ActivationTask(
            key="daemon.bootstrap_specs",
            requires=(
                AppKey.CORE_SETTINGS,
                AppKey.DAEMON_SERVICE,
                AppKey.BROWSER_INFRASTRUCTURE,
                AppKey.RUNTIME_BOOTSTRAP_CONFIG,
            ),
            run=_activate_daemon_bootstrap_specs,
            targets=(
                AssemblyTarget.API,
                AssemblyTarget.CLI_ADMIN,
                AssemblyTarget.DAEMON_SUPERVISOR,
                AssemblyTarget.TEST,
            ),
        ),
    )


def _empty_daemon_bootstrap_specs(_settings: Settings) -> tuple[DaemonServiceSpec, ...]:
    return ()


def _activate_daemon_bootstrap_specs(ctx) -> None:
    service = ctx.require(AppKey.DAEMON_SERVICE)
    browser_infrastructure = ctx.require(AppKey.BROWSER_INFRASTRUCTURE)
    specs = build_runtime_daemon_specs(
        settings=ctx.require(AppKey.CORE_SETTINGS),
        browser_system_config=browser_infrastructure.system_config,
        runtime_bootstrap_config=ctx.require(AppKey.RUNTIME_BOOTSTRAP_CONFIG),
    )
    desired_keys = {spec.key for spec in specs}
    for spec in specs:
        service.register_service_spec(spec)
    service.remove_service_specs(
        lambda spec: spec.key.startswith("capability:appium:")
        or (spec.key.startswith("host:browser:") and spec.key not in desired_keys),
    )


def build_runtime_daemon_specs(
    *,
    settings: Settings,
    browser_system_config: Any,
    runtime_bootstrap_config: Any,
) -> tuple[DaemonServiceSpec, ...]:
    orchestration_executor_cli_args = [
        "orchestration-executor",
        "run-executor",
        "--max-concurrent-assignments",
        str(runtime_bootstrap_config.orchestration_executor_max_concurrent_assignments),
    ]
    tool_worker_cli_args = [
        "tool-worker",
        "run",
        "--max-in-flight",
        str(runtime_bootstrap_config.tool_worker_max_in_flight),
    ]
    specs: list[DaemonServiceSpec] = [
        DaemonServiceSpec(
            key="worker:orchestration-scheduler",
            display_name="Orchestration Scheduler",
            service_group="core",
            role="worker",
            managed_by="internal",
            transport="process",
            replica_mode="singleton",
            desired_replicas=1,
            start_policy="eager",
            restart_policy="on-failure",
            metadata={
                "module": "orchestration",
                "component": "scheduler",
                "application_service": "orchestration_scheduler_service",
                "run_method": "run_until_stopped",
                "cli_args": ["orchestration-scheduler", "run-scheduler"],
            },
        ),
        DaemonServiceSpec(
            key="worker:orchestration",
            display_name="Orchestration Executor",
            service_group="core",
            role="worker",
            managed_by="internal",
            transport="process",
            replica_mode="replicated",
            desired_replicas=1,
            start_policy="eager",
            restart_policy="on-failure",
            metadata={
                "module": "orchestration",
                "component": "executor",
                "application_service": "orchestration_executor_service",
                "run_method": "run_until_stopped",
                "cli_args": orchestration_executor_cli_args,
            },
        ),
        DaemonServiceSpec(
            key="worker:event-outbox",
            display_name="Event Outbox Publisher",
            service_group="core",
            role="worker",
            managed_by="internal",
            transport="process",
            replica_mode="singleton",
            desired_replicas=1,
            start_policy="eager",
            restart_policy="on-failure",
            metadata={
                "module": "events",
                "component": "outbox_publisher",
                "application_service": "events_outbox_publisher_service",
                "run_method": "run_until_stopped",
                "cli_args": ["event-outbox", "run"],
            },
        ),
        DaemonServiceSpec(
            key="worker:event-relay",
            display_name="Event Relay",
            service_group="core",
            role="worker",
            managed_by="internal",
            transport="process",
            replica_mode="singleton",
            desired_replicas=1,
            start_policy="eager",
            restart_policy="on-failure",
            metadata={
                "module": "event_relay",
                "component": "relay",
                "application_service": "event_relay_runtime_event_service",
                "run_method": "run_until_stopped",
                "cli_args": ["event-relay", "run"],
            },
        ),
        DaemonServiceSpec(
            key="worker:operations-observer",
            display_name="Operations Observer",
            service_group="core",
            role="worker",
            managed_by="internal",
            transport="process",
            replica_mode="singleton",
            desired_replicas=1,
            start_policy="eager",
            restart_policy="on-failure",
            metadata={
                "module": "operations",
                "component": "observer",
                "application_service": "operations_observer_runtime_event_service",
                "run_method": "run_until_stopped",
                "cli_args": ["operations-observer", "run"],
            },
        ),
        DaemonServiceSpec(
            key="worker:tool-scheduler",
            display_name="Tool Scheduler",
            service_group="core",
            role="worker",
            managed_by="internal",
            transport="process",
            replica_mode="singleton",
            desired_replicas=1,
            start_policy="eager",
            restart_policy="on-failure",
            metadata={
                "module": "tool",
                "component": "scheduler",
                "application_service": "tool_scheduler_service",
                "run_method": "run_until_stopped",
                "cli_args": ["tool-scheduler", "run-scheduler"],
            },
        ),
        DaemonServiceSpec(
            key="worker:tool",
            display_name="Tool Worker",
            service_group="core",
            role="worker",
            managed_by="internal",
            transport="process",
            replica_mode="replicated",
            desired_replicas=1,
            start_policy="eager",
            restart_policy="on-failure",
            metadata={
                "module": "tool",
                "component": "worker",
                "application_service": "tool_worker_service",
                "run_method": "run_until_stopped",
                "cli_args": tool_worker_cli_args,
            },
        ),
    ]
    for index, profile in enumerate(browser_system_config.profiles):
        specs.append(
            browser_profile_daemon_service_spec(
                browser_system_config=browser_system_config,
                profile=profile,
                index=index,
            ),
        )
    if (
        settings.ocr_enabled
        and settings.ocr_backend == "local"
        and settings.ocr_provider == "host"
    ):
        specs.append(
            DaemonServiceSpec(
                key="capability:ocr:default",
                display_name="OCR Host",
                service_group="ocr",
                role="capability",
                managed_by="internal",
                transport="process",
                start_policy="lazy",
                restart_policy="on-failure",
                metadata={
                    "server_url": settings.ocr_base_url,
                    "cli_args": [
                        "ocr",
                        "host",
                        "run",
                        "--max-concurrent-requests",
                        str(settings.ocr_max_concurrent_requests),
                    ],
                },
            ),
        )
    return tuple(specs)


def browser_profile_daemon_service_spec(
    *,
    browser_system_config: Any,
    profile: Any,
    index: int,
) -> DaemonServiceSpec:
    cdp_port = browser_profile_cdp_port(browser_system_config, profile, index)
    browser_server_url = browser_profile_cdp_endpoint(
        browser_system_config,
        profile,
        cdp_port=cdp_port,
    )
    host_service_key = f"host:browser:{profile.name}"
    metadata = {
        "profile_name": profile.name,
        "driver": profile.driver,
        "attach_only": profile.attach_only,
        "cdp_url": profile.cdp_url,
        "cdp_port": cdp_port,
        "user_data_dir": profile.user_data_dir,
        "profile_directory": profile.profile_directory,
        "autostart": profile.autostart,
        "proxy_mode": profile.proxy_mode,
        "proxy_server": profile.proxy_server,
        "proxy_bypass_list": list(profile.proxy_bypass_list),
        "proxy_binding_id": profile.proxy_binding_id,
        "proxy_credential_kind": getattr(profile, "proxy_credential_kind", "basic"),
        "close_targets_on_release": getattr(profile, "close_targets_on_release", True),
        "close_targets_on_expire": getattr(profile, "close_targets_on_expire", True),
        "server_url": browser_server_url,
    }
    if profile.driver == "existing-session":
        return DaemonServiceSpec(
            key=host_service_key,
            display_name=f"Browser Host ({profile.name})",
            service_group="browser",
            role="host",
            managed_by="external",
            transport="endpoint",
            start_policy="attach-only",
            restart_policy="manual",
            healthcheck_policy="cdp-version",
            match_policy="cdp-port",
            metadata=metadata,
        )
    return DaemonServiceSpec(
        key=host_service_key,
        display_name=f"Managed Browser ({profile.name})",
        service_group="browser",
        role="host",
        managed_by="internal",
        transport="process",
        start_policy="ensure",
        restart_policy="on-failure",
        healthcheck_policy="cdp-version",
        match_policy="cdp-port",
        metadata={
            **metadata,
            "cli_args": [
                "browser",
                "host",
                "run",
                "--profile",
                profile.name,
                "--poll-interval-seconds",
                "0.25",
            ],
        },
    )


def _build_daemon_service(
    ctx,
    bootstrap_specs_provider: DaemonBootstrapSpecsProvider,
) -> DaemonApplicationService:
    settings = ctx.require(AppKey.CORE_SETTINGS)
    state_root = bootstrap_daemon_state_root(settings.daemon_state_dir)
    apply_daemon_state_migrations(state_root)
    service_spec_store = FileBackedDaemonServiceSpecStore(
        state_root.config_dir,
        bootstrap_specs=tuple(bootstrap_specs_provider(settings)),
    )
    instance_store = FileBackedDaemonInstanceStore(state_root.instances_dir)
    lease_store = FileBackedDaemonLeaseStore(state_root.leases_dir)
    lease_event_log = FileBackedDaemonLeaseEventLog(state_root.leases_dir)
    return DaemonApplicationService(
        service_spec_store=service_spec_store,
        instance_store=instance_store,
        lease_store=lease_store,
        lease_event_log=lease_event_log,
    )


def build_daemon_manager(
    *,
    daemon_service: DaemonApplicationService,
    process_service: Any,
) -> DaemonManager:
    return DaemonManager(
        daemon_service=daemon_service,
        process_service=process_service,
        working_directory=str(PROJECT_ROOT),
        shell_resolver=lambda: "/bin/sh",
    )


__all__ = [
    "DaemonBootstrapSpecsProvider",
    "browser_profile_cdp_port",
    "build_daemon_manager",
    "build_runtime_daemon_specs",
    "daemon_activation_tasks",
    "daemon_factories",
    "daemon_manager_factories",
]
