"""Target-specific app assembly modules live here."""

from crxzipple.app.assembly.access import access_factories
from crxzipple.app.assembly.agent import agent_activation_tasks, agent_factories
from crxzipple.app.assembly.artifacts import artifact_factories
from crxzipple.app.assembly.authorization import (
    AuthorizationBootstrapConfig,
    authorization_factories,
)
from crxzipple.app.assembly.browser import (
    BrowserInfrastructure,
    browser_factories,
    build_browser_infrastructure,
    build_browser_system_config,
)
from crxzipple.app.assembly.channels import (
    ChannelInfrastructure,
    build_channel_infrastructure,
    channel_control_factories,
    channel_factories,
)
from crxzipple.app.assembly.channel_runtime import (
    channel_runtime_activation_tasks,
    channel_runtime_factories,
)
from crxzipple.app.assembly.context_workspace import (
    context_workspace_factories,
    context_workspace_integration_factories,
)
from crxzipple.app.assembly.daemon import (
    build_daemon_manager,
    daemon_factories,
    daemon_manager_factories,
)
from crxzipple.app.assembly.database import (
    database_factories,
    settings_with_database_url,
)
from crxzipple.app.assembly.dispatch import dispatch_factories
from crxzipple.app.assembly.events import (
    build_event_contract_registry,
    build_event_definition_registry,
    build_events_backend,
    events_factories,
)
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
from crxzipple.app.assembly.llm import (
    build_llm_adapter_registry,
    llm_adapter_registry_factories,
    llm_factories,
)
from crxzipple.app.assembly.memory import (
    build_memory_embedding_provider,
    build_memory_event_emitter,
    memory_context_factories,
    memory_factories,
)
from crxzipple.app.assembly.mobile import (
    MobileInfrastructure,
    build_mobile_infrastructure,
    build_mobile_system_config,
    mobile_factories,
)
from crxzipple.app.assembly.ocr import build_ocr_engine, ocr_factories
from crxzipple.app.assembly.orchestration import (
    OrchestrationIngressSubmissionService,
    orchestration_factories,
)
from crxzipple.app.assembly.process import build_process_service, process_factories
from crxzipple.app.assembly.runtime_defaults import (
    RuntimeSettingsBootstrapConfig,
    runtime_defaults_factories,
)
from crxzipple.app.assembly.settings import settings_factories
from crxzipple.app.assembly.session import session_factories
from crxzipple.app.assembly.session_runtime import session_runtime_factories
from crxzipple.app.assembly.skills import (
    build_skill_event_emitter,
    skills_activation_tasks,
    skills_factories,
)
from crxzipple.app.assembly.tool import (
    ToolExecutionServicesAssembly,
    build_tool_execution_capability_bindings,
    build_tool_execution_services,
    tool_activation_tasks,
    tool_core_factories,
    tool_execution_factories,
    tool_factories,
    tool_queue_factories,
)
from crxzipple.app.assembly.unit_of_work import unit_of_work_factories
from crxzipple.app.assembly.targets import (
    ALL_RUNTIME_TARGETS,
    ALL_TARGET_ENTRYPOINTS,
    API_ENTRYPOINT,
    CHANNEL_RUNTIME_ENTRYPOINT,
    CLI_ADMIN_ENTRYPOINT,
    DAEMON_SERVICE_TARGETS,
    DAEMON_SERVICE_TARGET_PREFIXES,
    DAEMON_SUPERVISOR_ENTRYPOINT,
    ENTRYPOINTS_BY_TARGET,
    EVENT_RELAY_WORKER_ENTRYPOINT,
    OPERATIONS_OBSERVER_ENTRYPOINT,
    ORCHESTRATION_EXECUTOR_ENTRYPOINT,
    ORCHESTRATION_SCHEDULER_ENTRYPOINT,
    TEST_ENTRYPOINT,
    TOOL_SCHEDULER_ENTRYPOINT,
    TOOL_WORKER_ENTRYPOINT,
    AssemblyTargetEntrypoint,
    UnknownDaemonServiceTargetError,
    all_runtime_targets,
    entrypoint_for_target,
    target_for_daemon_service,
)

__all__ = [
    "ALL_RUNTIME_TARGETS",
    "ALL_TARGET_ENTRYPOINTS",
    "API_ENTRYPOINT",
    "AssemblyTargetEntrypoint",
    "AuthorizationBootstrapConfig",
    "BROWSER_CLEANUP_ORDER",
    "BrowserInfrastructure",
    "CHANNEL_RUNTIME_ENTRYPOINT",
    "CLI_ADMIN_ENTRYPOINT",
    "DAEMON_SERVICE_TARGETS",
    "DAEMON_SERVICE_TARGET_PREFIXES",
    "DAEMON_SUPERVISOR_ENTRYPOINT",
    "DATABASE_CLEANUP_ORDER",
    "ENTRYPOINTS_BY_TARGET",
    "EVENTS_CLEANUP_ORDER",
    "EVENT_RELAY_WORKER_ENTRYPOINT",
    "HTTP_CLIENTS_CLEANUP_ORDER",
    "ChannelInfrastructure",
    "MEMORY_WATCHER_CLEANUP_ORDER",
    "MobileInfrastructure",
    "OPERATIONS_OBSERVER_ENTRYPOINT",
    "ORCHESTRATION_EXECUTOR_ENTRYPOINT",
    "OrchestrationIngressSubmissionService",
    "PROCESS_CLEANUP_ORDER",
    "ORCHESTRATION_SCHEDULER_ENTRYPOINT",
    "RuntimeSettingsBootstrapConfig",
    "TEST_ENTRYPOINT",
    "TOOL_SCHEDULER_ENTRYPOINT",
    "TOOL_WORKER_ENTRYPOINT",
    "TOOL_CLEANUP_ORDER",
    "ToolExecutionServicesAssembly",
    "UnknownDaemonServiceTargetError",
    "access_factories",
    "agent_activation_tasks",
    "agent_factories",
    "artifact_factories",
    "all_runtime_targets",
    "authorization_factories",
    "browser_factories",
    "build_browser_infrastructure",
    "build_browser_system_config",
    "build_channel_infrastructure",
    "build_daemon_manager",
    "build_event_contract_registry",
    "build_event_definition_registry",
    "build_events_backend",
    "build_llm_adapter_registry",
    "build_memory_embedding_provider",
    "build_memory_event_emitter",
    "build_mobile_infrastructure",
    "build_mobile_system_config",
    "build_ocr_engine",
    "build_process_service",
    "build_skill_event_emitter",
    "build_tool_execution_capability_bindings",
    "build_tool_execution_services",
    "channel_control_factories",
    "channel_factories",
    "channel_runtime_activation_tasks",
    "channel_runtime_factories",
    "context_workspace_factories",
    "context_workspace_integration_factories",
    "daemon_factories",
    "daemon_manager_factories",
    "database_factories",
    "dispatch_factories",
    "entrypoint_for_target",
    "events_factories",
    "llm_adapter_registry_factories",
    "llm_factories",
    "memory_factories",
    "memory_context_factories",
    "mobile_factories",
    "ocr_factories",
    "orchestration_factories",
    "process_factories",
    "runtime_defaults_factories",
    "runtime_lifecycle_factories",
    "session_runtime_factories",
    "session_factories",
    "settings_factories",
    "settings_with_database_url",
    "skills_activation_tasks",
    "skills_factories",
    "target_for_daemon_service",
    "tool_activation_tasks",
    "tool_core_factories",
    "tool_execution_factories",
    "tool_factories",
    "tool_queue_factories",
    "unit_of_work_factories",
]
