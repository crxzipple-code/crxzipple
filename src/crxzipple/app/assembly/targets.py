"""Assembly target to entrypoint and daemon service mappings."""

from __future__ import annotations

from dataclasses import dataclass

from crxzipple.app.plan import AssemblyTarget


class UnknownDaemonServiceTargetError(ValueError):
    """Raised when a daemon service key has no assembly target mapping."""


@dataclass(frozen=True, slots=True)
class AssemblyTargetEntrypoint:
    """Stable metadata for routing a process entrypoint to an assembly target."""

    target: AssemblyTarget
    cli_args: tuple[str, ...]
    daemon_service_key: str | None = None
    daemon_service_key_prefix: str | None = None


API_ENTRYPOINT = AssemblyTargetEntrypoint(
    target=AssemblyTarget.API,
    cli_args=("serve",),
)
CLI_ADMIN_ENTRYPOINT = AssemblyTargetEntrypoint(
    target=AssemblyTarget.CLI_ADMIN,
    cli_args=(),
)
DAEMON_SUPERVISOR_ENTRYPOINT = AssemblyTargetEntrypoint(
    target=AssemblyTarget.DAEMON_SUPERVISOR,
    cli_args=("daemon", "supervise-internal"),
)
ORCHESTRATION_SCHEDULER_ENTRYPOINT = AssemblyTargetEntrypoint(
    target=AssemblyTarget.ORCHESTRATION_SCHEDULER,
    cli_args=("orchestration-scheduler", "run-scheduler"),
    daemon_service_key="worker:orchestration-scheduler",
)
ORCHESTRATION_EXECUTOR_ENTRYPOINT = AssemblyTargetEntrypoint(
    target=AssemblyTarget.ORCHESTRATION_EXECUTOR,
    cli_args=("orchestration-executor", "run-executor"),
    daemon_service_key="worker:orchestration",
)
TOOL_SCHEDULER_ENTRYPOINT = AssemblyTargetEntrypoint(
    target=AssemblyTarget.TOOL_SCHEDULER,
    cli_args=("tool-scheduler", "run-scheduler"),
    daemon_service_key="worker:tool-scheduler",
)
TOOL_WORKER_ENTRYPOINT = AssemblyTargetEntrypoint(
    target=AssemblyTarget.TOOL_WORKER,
    cli_args=("tool-worker", "run"),
    daemon_service_key="worker:tool",
)
OPERATIONS_OBSERVER_ENTRYPOINT = AssemblyTargetEntrypoint(
    target=AssemblyTarget.OPERATIONS_OBSERVER,
    cli_args=("operations-observer", "run"),
    daemon_service_key="worker:operations-observer",
)
EVENT_RELAY_WORKER_ENTRYPOINT = AssemblyTargetEntrypoint(
    target=AssemblyTarget.EVENT_RELAY_WORKER,
    cli_args=("event-relay", "run"),
    daemon_service_key="worker:event-relay",
)
EVENT_OUTBOX_PUBLISHER_ENTRYPOINT = AssemblyTargetEntrypoint(
    target=AssemblyTarget.EVENT_OUTBOX_PUBLISHER,
    cli_args=("event-outbox", "run"),
    daemon_service_key="worker:event-outbox",
)
CHANNEL_RUNTIME_ENTRYPOINT = AssemblyTargetEntrypoint(
    target=AssemblyTarget.CHANNEL_RUNTIME,
    cli_args=("channel-runtime", "run"),
    daemon_service_key_prefix="channel:",
)
TEST_ENTRYPOINT = AssemblyTargetEntrypoint(
    target=AssemblyTarget.TEST,
    cli_args=(),
)

ALL_TARGET_ENTRYPOINTS: tuple[AssemblyTargetEntrypoint, ...] = (
    API_ENTRYPOINT,
    CLI_ADMIN_ENTRYPOINT,
    DAEMON_SUPERVISOR_ENTRYPOINT,
    ORCHESTRATION_SCHEDULER_ENTRYPOINT,
    ORCHESTRATION_EXECUTOR_ENTRYPOINT,
    TOOL_SCHEDULER_ENTRYPOINT,
    TOOL_WORKER_ENTRYPOINT,
    OPERATIONS_OBSERVER_ENTRYPOINT,
    EVENT_RELAY_WORKER_ENTRYPOINT,
    EVENT_OUTBOX_PUBLISHER_ENTRYPOINT,
    CHANNEL_RUNTIME_ENTRYPOINT,
    TEST_ENTRYPOINT,
)

ALL_RUNTIME_TARGETS: tuple[AssemblyTarget, ...] = (
    AssemblyTarget.API,
    AssemblyTarget.CLI_ADMIN,
    AssemblyTarget.DAEMON_SUPERVISOR,
    AssemblyTarget.ORCHESTRATION_SCHEDULER,
    AssemblyTarget.ORCHESTRATION_EXECUTOR,
    AssemblyTarget.TOOL_SCHEDULER,
    AssemblyTarget.TOOL_WORKER,
    AssemblyTarget.OPERATIONS_OBSERVER,
    AssemblyTarget.EVENT_RELAY_WORKER,
    AssemblyTarget.EVENT_OUTBOX_PUBLISHER,
    AssemblyTarget.CHANNEL_RUNTIME,
)

ENTRYPOINTS_BY_TARGET: dict[AssemblyTarget, AssemblyTargetEntrypoint] = {
    entrypoint.target: entrypoint for entrypoint in ALL_TARGET_ENTRYPOINTS
}

DAEMON_SERVICE_TARGETS: dict[str, AssemblyTarget] = {
    entrypoint.daemon_service_key: entrypoint.target
    for entrypoint in ALL_TARGET_ENTRYPOINTS
    if entrypoint.daemon_service_key is not None
}
DAEMON_SERVICE_TARGET_PREFIXES: tuple[tuple[str, AssemblyTarget], ...] = tuple(
    (entrypoint.daemon_service_key_prefix, entrypoint.target)
    for entrypoint in ALL_TARGET_ENTRYPOINTS
    if entrypoint.daemon_service_key_prefix is not None
)


def all_runtime_targets() -> tuple[AssemblyTarget, ...]:
    """Return non-test targets that should receive runtime assembly paths."""

    return ALL_RUNTIME_TARGETS


def entrypoint_for_target(
    target: AssemblyTarget | str,
) -> AssemblyTargetEntrypoint:
    """Return entrypoint metadata for an assembly target."""

    return ENTRYPOINTS_BY_TARGET[AssemblyTarget.parse(target)]


def target_for_daemon_service(service_key: str) -> AssemblyTarget:
    """Resolve a managed daemon service key to its app assembly target."""

    normalized = service_key.strip()
    if normalized in DAEMON_SERVICE_TARGETS:
        return DAEMON_SERVICE_TARGETS[normalized]
    for prefix, target in DAEMON_SERVICE_TARGET_PREFIXES:
        if normalized.startswith(prefix):
            return target
    raise UnknownDaemonServiceTargetError(
        f"Unknown daemon service assembly target: {service_key!r}"
    )


__all__ = [
    "ALL_RUNTIME_TARGETS",
    "ALL_TARGET_ENTRYPOINTS",
    "API_ENTRYPOINT",
    "AssemblyTargetEntrypoint",
    "CHANNEL_RUNTIME_ENTRYPOINT",
    "CLI_ADMIN_ENTRYPOINT",
    "DAEMON_SERVICE_TARGETS",
    "DAEMON_SERVICE_TARGET_PREFIXES",
    "DAEMON_SUPERVISOR_ENTRYPOINT",
    "ENTRYPOINTS_BY_TARGET",
    "EVENT_RELAY_WORKER_ENTRYPOINT",
    "EVENT_OUTBOX_PUBLISHER_ENTRYPOINT",
    "OPERATIONS_OBSERVER_ENTRYPOINT",
    "ORCHESTRATION_EXECUTOR_ENTRYPOINT",
    "ORCHESTRATION_SCHEDULER_ENTRYPOINT",
    "TEST_ENTRYPOINT",
    "TOOL_SCHEDULER_ENTRYPOINT",
    "TOOL_WORKER_ENTRYPOINT",
    "UnknownDaemonServiceTargetError",
    "all_runtime_targets",
    "entrypoint_for_target",
    "target_for_daemon_service",
]
