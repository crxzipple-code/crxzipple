"""Target-specific app assembly modules live here.

The package exports common assembly helpers lazily. Importing one submodule,
for example ``crxzipple.app.assembly.access``, must not load every runtime
assembly such as browser, daemon, mobile, or operations.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

_EXPORTS: dict[str, tuple[str, str]] = {
    "ALL_RUNTIME_TARGETS": ("crxzipple.app.assembly.targets", "ALL_RUNTIME_TARGETS"),
    "ALL_TARGET_ENTRYPOINTS": (
        "crxzipple.app.assembly.targets",
        "ALL_TARGET_ENTRYPOINTS",
    ),
    "API_ENTRYPOINT": ("crxzipple.app.assembly.targets", "API_ENTRYPOINT"),
    "AssemblyTargetEntrypoint": (
        "crxzipple.app.assembly.targets",
        "AssemblyTargetEntrypoint",
    ),
    "AuthorizationBootstrapConfig": (
        "crxzipple.app.assembly.authorization",
        "AuthorizationBootstrapConfig",
    ),
    "BROWSER_CLEANUP_ORDER": (
        "crxzipple.app.assembly.lifecycle",
        "BROWSER_CLEANUP_ORDER",
    ),
    "BrowserInfrastructure": (
        "crxzipple.app.assembly.browser",
        "BrowserInfrastructure",
    ),
    "CHANNEL_RUNTIME_ENTRYPOINT": (
        "crxzipple.app.assembly.targets",
        "CHANNEL_RUNTIME_ENTRYPOINT",
    ),
    "CLI_ADMIN_ENTRYPOINT": ("crxzipple.app.assembly.targets", "CLI_ADMIN_ENTRYPOINT"),
    "DAEMON_SERVICE_TARGETS": (
        "crxzipple.app.assembly.targets",
        "DAEMON_SERVICE_TARGETS",
    ),
    "DAEMON_SERVICE_TARGET_PREFIXES": (
        "crxzipple.app.assembly.targets",
        "DAEMON_SERVICE_TARGET_PREFIXES",
    ),
    "DAEMON_SUPERVISOR_ENTRYPOINT": (
        "crxzipple.app.assembly.targets",
        "DAEMON_SUPERVISOR_ENTRYPOINT",
    ),
    "DATABASE_CLEANUP_ORDER": (
        "crxzipple.app.assembly.lifecycle",
        "DATABASE_CLEANUP_ORDER",
    ),
    "ENTRYPOINTS_BY_TARGET": (
        "crxzipple.app.assembly.targets",
        "ENTRYPOINTS_BY_TARGET",
    ),
    "EVENTS_CLEANUP_ORDER": (
        "crxzipple.app.assembly.lifecycle",
        "EVENTS_CLEANUP_ORDER",
    ),
    "EVENT_OUTBOX_PUBLISHER_ENTRYPOINT": (
        "crxzipple.app.assembly.targets",
        "EVENT_OUTBOX_PUBLISHER_ENTRYPOINT",
    ),
    "EVENT_RELAY_WORKER_ENTRYPOINT": (
        "crxzipple.app.assembly.targets",
        "EVENT_RELAY_WORKER_ENTRYPOINT",
    ),
    "HTTP_CLIENTS_CLEANUP_ORDER": (
        "crxzipple.app.assembly.lifecycle",
        "HTTP_CLIENTS_CLEANUP_ORDER",
    ),
    "ChannelInfrastructure": (
        "crxzipple.app.assembly.channels",
        "ChannelInfrastructure",
    ),
    "MEMORY_WATCHER_CLEANUP_ORDER": (
        "crxzipple.app.assembly.lifecycle",
        "MEMORY_WATCHER_CLEANUP_ORDER",
    ),
    "MobileInfrastructure": (
        "crxzipple.app.assembly.mobile",
        "MobileInfrastructure",
    ),
    "OPERATIONS_OBSERVER_ENTRYPOINT": (
        "crxzipple.app.assembly.targets",
        "OPERATIONS_OBSERVER_ENTRYPOINT",
    ),
    "ORCHESTRATION_EXECUTOR_ENTRYPOINT": (
        "crxzipple.app.assembly.targets",
        "ORCHESTRATION_EXECUTOR_ENTRYPOINT",
    ),
    "ORCHESTRATION_SCHEDULER_ENTRYPOINT": (
        "crxzipple.app.assembly.targets",
        "ORCHESTRATION_SCHEDULER_ENTRYPOINT",
    ),
    "OrchestrationIngressSubmissionService": (
        "crxzipple.app.assembly.orchestration",
        "OrchestrationIngressSubmissionService",
    ),
    "PROCESS_CLEANUP_ORDER": (
        "crxzipple.app.assembly.lifecycle",
        "PROCESS_CLEANUP_ORDER",
    ),
    "RuntimeSettingsBootstrapConfig": (
        "crxzipple.app.assembly.runtime_defaults",
        "RuntimeSettingsBootstrapConfig",
    ),
    "TEST_ENTRYPOINT": ("crxzipple.app.assembly.targets", "TEST_ENTRYPOINT"),
    "TOOL_CLEANUP_ORDER": ("crxzipple.app.assembly.lifecycle", "TOOL_CLEANUP_ORDER"),
    "TOOL_SCHEDULER_ENTRYPOINT": (
        "crxzipple.app.assembly.targets",
        "TOOL_SCHEDULER_ENTRYPOINT",
    ),
    "TOOL_WORKER_ENTRYPOINT": (
        "crxzipple.app.assembly.targets",
        "TOOL_WORKER_ENTRYPOINT",
    ),
    "ToolExecutionServicesAssembly": (
        "crxzipple.app.assembly.tool",
        "ToolExecutionServicesAssembly",
    ),
    "UnknownDaemonServiceTargetError": (
        "crxzipple.app.assembly.targets",
        "UnknownDaemonServiceTargetError",
    ),
    "access_factories": ("crxzipple.app.assembly.access", "access_factories"),
    "agent_activation_tasks": (
        "crxzipple.app.assembly.agent",
        "agent_activation_tasks",
    ),
    "agent_factories": ("crxzipple.app.assembly.agent", "agent_factories"),
    "artifact_factories": ("crxzipple.app.assembly.artifacts", "artifact_factories"),
    "all_runtime_targets": ("crxzipple.app.assembly.targets", "all_runtime_targets"),
    "authorization_factories": (
        "crxzipple.app.assembly.authorization",
        "authorization_factories",
    ),
    "browser_factories": ("crxzipple.app.assembly.browser", "browser_factories"),
    "build_browser_infrastructure": (
        "crxzipple.app.assembly.browser",
        "build_browser_infrastructure",
    ),
    "build_browser_system_config": (
        "crxzipple.app.assembly.browser",
        "build_browser_system_config",
    ),
    "build_channel_infrastructure": (
        "crxzipple.app.assembly.channels",
        "build_channel_infrastructure",
    ),
    "build_daemon_manager": (
        "crxzipple.app.assembly.daemon",
        "build_daemon_manager",
    ),
    "build_event_contract_registry": (
        "crxzipple.app.assembly.events",
        "build_event_contract_registry",
    ),
    "build_event_definition_registry": (
        "crxzipple.app.assembly.events",
        "build_event_definition_registry",
    ),
    "build_events_backend": ("crxzipple.app.assembly.events", "build_events_backend"),
    "build_llm_adapter_registry": (
        "crxzipple.app.assembly.llm",
        "build_llm_adapter_registry",
    ),
    "build_memory_embedding_provider": (
        "crxzipple.app.assembly.memory",
        "build_memory_embedding_provider",
    ),
    "build_memory_event_emitter": (
        "crxzipple.app.assembly.memory",
        "build_memory_event_emitter",
    ),
    "build_mobile_infrastructure": (
        "crxzipple.app.assembly.mobile",
        "build_mobile_infrastructure",
    ),
    "build_mobile_system_config": (
        "crxzipple.app.assembly.mobile",
        "build_mobile_system_config",
    ),
    "build_ocr_engine": ("crxzipple.app.assembly.ocr", "build_ocr_engine"),
    "build_process_service": (
        "crxzipple.app.assembly.process",
        "build_process_service",
    ),
    "build_skill_event_emitter": (
        "crxzipple.app.assembly.skills",
        "build_skill_event_emitter",
    ),
    "build_tool_execution_capability_bindings": (
        "crxzipple.app.assembly.tool_packages",
        "build_tool_execution_capability_bindings",
    ),
    "build_tool_execution_services": (
        "crxzipple.app.assembly.tool",
        "build_tool_execution_services",
    ),
    "channel_control_factories": (
        "crxzipple.app.assembly.channels",
        "channel_control_factories",
    ),
    "channel_factories": ("crxzipple.app.assembly.channels", "channel_factories"),
    "channel_runtime_activation_tasks": (
        "crxzipple.app.assembly.channel_runtime",
        "channel_runtime_activation_tasks",
    ),
    "channel_runtime_factories": (
        "crxzipple.app.assembly.channel_runtime",
        "channel_runtime_factories",
    ),
    "context_workspace_factories": (
        "crxzipple.app.assembly.context_workspace",
        "context_workspace_factories",
    ),
    "context_workspace_integration_factories": (
        "crxzipple.app.assembly.context_workspace",
        "context_workspace_integration_factories",
    ),
    "daemon_factories": ("crxzipple.app.assembly.daemon", "daemon_factories"),
    "daemon_manager_factories": (
        "crxzipple.app.assembly.daemon",
        "daemon_manager_factories",
    ),
    "database_factories": ("crxzipple.app.assembly.database", "database_factories"),
    "dispatch_factories": ("crxzipple.app.assembly.dispatch", "dispatch_factories"),
    "entrypoint_for_target": (
        "crxzipple.app.assembly.targets",
        "entrypoint_for_target",
    ),
    "events_factories": ("crxzipple.app.assembly.events", "events_factories"),
    "llm_adapter_registry_factories": (
        "crxzipple.app.assembly.llm",
        "llm_adapter_registry_factories",
    ),
    "llm_factories": ("crxzipple.app.assembly.llm", "llm_factories"),
    "memory_context_factories": (
        "crxzipple.app.assembly.memory",
        "memory_context_factories",
    ),
    "memory_factories": ("crxzipple.app.assembly.memory", "memory_factories"),
    "mobile_factories": ("crxzipple.app.assembly.mobile", "mobile_factories"),
    "ocr_factories": ("crxzipple.app.assembly.ocr", "ocr_factories"),
    "orchestration_factories": (
        "crxzipple.app.assembly.orchestration",
        "orchestration_factories",
    ),
    "process_factories": ("crxzipple.app.assembly.process", "process_factories"),
    "runtime_defaults_factories": (
        "crxzipple.app.assembly.runtime_defaults",
        "runtime_defaults_factories",
    ),
    "runtime_lifecycle_factories": (
        "crxzipple.app.assembly.lifecycle",
        "runtime_lifecycle_factories",
    ),
    "session_factories": ("crxzipple.app.assembly.session", "session_factories"),
    "session_runtime_factories": (
        "crxzipple.app.assembly.session_runtime",
        "session_runtime_factories",
    ),
    "settings_factories": ("crxzipple.app.assembly.settings", "settings_factories"),
    "settings_with_database_url": (
        "crxzipple.app.assembly.database",
        "settings_with_database_url",
    ),
    "skills_activation_tasks": (
        "crxzipple.app.assembly.skills",
        "skills_activation_tasks",
    ),
    "skills_factories": ("crxzipple.app.assembly.skills", "skills_factories"),
    "target_for_daemon_service": (
        "crxzipple.app.assembly.targets",
        "target_for_daemon_service",
    ),
    "tool_activation_tasks": ("crxzipple.app.assembly.tool", "tool_activation_tasks"),
    "tool_core_factories": ("crxzipple.app.assembly.tool", "tool_core_factories"),
    "tool_execution_factories": (
        "crxzipple.app.assembly.tool",
        "tool_execution_factories",
    ),
    "tool_factories": ("crxzipple.app.assembly.tool", "tool_factories"),
    "tool_queue_factories": ("crxzipple.app.assembly.tool", "tool_queue_factories"),
    "tool_request_preview_factories": (
        "crxzipple.app.assembly.tool",
        "tool_request_preview_factories",
    ),
    "unit_of_work_factories": (
        "crxzipple.app.assembly.unit_of_work",
        "unit_of_work_factories",
    ),
}

__all__ = sorted(_EXPORTS)


def __getattr__(name: str) -> Any:
    try:
        module_name, attr_name = _EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(name) from exc
    value = getattr(import_module(module_name), attr_name)
    globals()[name] = value
    return value
