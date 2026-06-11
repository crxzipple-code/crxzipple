"""Stable application registry keys used by app assembly."""

from __future__ import annotations

from enum import StrEnum


class AppKey(StrEnum):
    """Named applications exposed by assembled containers."""

    CORE_SETTINGS = "core.settings"
    RUNTIME_CLEANUP_TASKS = "runtime.cleanup_tasks"
    DATABASE_ENGINE = "database.engine"
    DATABASE_SESSION_FACTORY = "database.session_factory"
    UNIT_OF_WORK_FACTORY = "database.unit_of_work_factory"

    EVENTS_BACKEND = "events.backend"
    EVENTS_SERVICE = "events.service"
    EVENTS_BUS = "events.bus"
    EVENT_OUTBOX_PUBLISHER_SERVICE = "events.outbox_publisher_service"
    EVENT_CONTRACT_REGISTRY = "events.contract_registry"
    EVENT_DEFINITION_REGISTRY = "events.definition_registry"

    SETTINGS_SERVICES = "settings.services"
    SETTINGS_QUERY_SERVICE = "settings.query_service"
    SETTINGS_ACTION_SERVICE = "settings.action_service"
    SETTINGS_RESOLVER = "settings.resolver"
    SETTINGS_MATERIALIZER = "settings.materializer"
    SETTINGS_BOOTSTRAP_RESULT = "settings.bootstrap_result"

    ACCESS_SERVICE = "access.service"
    ACCESS_GOVERNANCE_REPOSITORY = "access.governance_repository"
    ACCESS_ACTION_AUDIT_REPOSITORY = "access.action_audit_repository"
    ACCESS_OAUTH_TOKEN_STORE = "access.oauth_token_store"
    ACCESS_OAUTH_SERVICE = "access.oauth_service"

    AUTHORIZATION_SERVICE = "authorization.service"
    AUTHORIZATION_BOOTSTRAP_POLICY_COUNT = "authorization.bootstrap_policy_count"

    AGENT_SERVICE = "agent.service"
    AGENT_BOOTSTRAP_PROFILE_COUNT = "agent.bootstrap_profile_count"

    SESSION_SERVICE = "session.service"
    SESSION_RESOLUTION_SERVICE = "session.resolution_service"
    SESSION_WORKSPACE_LOOKUP = "session.workspace_lookup"
    SESSION_RUNTIME_CONTROL = "session.runtime_control"

    CONTEXT_OWNER_REGISTRY = "context_workspace.owner_registry"
    CONTEXT_WORKSPACE_SERVICE = "context_workspace.workspace_service"
    CONTEXT_TREE_SERVICE = "context_workspace.tree_service"
    CONTEXT_RENDER_SERVICE = "context_workspace.render_service"
    CONTEXT_SESSION_NODE_PROVIDER = "context_workspace.session_node_provider"
    CONTEXT_AGENT_HOME_NODE_PROVIDER = "context_workspace.agent_home_node_provider"
    CONTEXT_SKILL_NODE_PROVIDER = "context_workspace.skill_node_provider"
    CONTEXT_TOOL_NODE_PROVIDER = "context_workspace.tool_node_provider"
    CONTEXT_MEMORY_NODE_PROVIDER = "context_workspace.memory_node_provider"
    CONTEXT_ARTIFACT_NODE_PROVIDER = "context_workspace.artifact_node_provider"
    CONTEXT_WORKSPACE_NODE_PROVIDER = "context_workspace.workspace_node_provider"

    DISPATCH_SERVICE = "dispatch.service"
    CHANNEL_INFRASTRUCTURE = "channels.infrastructure"
    CHANNEL_PROFILE_SERVICE = "channels.profile_service"
    CHANNEL_RUNTIME_MANAGER = "channels.runtime_manager"
    CHANNEL_CONTROL_SERVICE = "channels.control_service"
    LARK_CHANNEL_RUNTIME_SERVICE = "channels.lark_runtime_service"
    WEB_CHANNEL_RUNTIME_SERVICE = "channels.web_runtime_service"
    WEBHOOK_CHANNEL_RUNTIME_SERVICE = "channels.webhook_runtime_service"
    PROCESS_SERVICE = "process.service"
    DAEMON_SERVICE = "daemon.service"
    DAEMON_MANAGER = "daemon.manager"
    ARTIFACT_SERVICE = "artifacts.service"
    SKILL_MANAGER = "skills.manager"
    BROWSER_INFRASTRUCTURE = "browser.infrastructure"
    BROWSER_SYSTEM_CONFIG_STORE = "browser.system_config_store"
    BROWSER_PROFILE_POOL_STORE = "browser.profile_pool_store"
    BROWSER_PROFILE_ALLOCATION_STORE = "browser.profile_allocation_store"
    BROWSER_PROFILE_ADMIN_SERVICE = "browser.profile_admin_service"
    BROWSER_PROFILE_POOL_SERVICE = "browser.profile_pool_service"
    BROWSER_PROFILE_ALLOCATOR_SERVICE = "browser.profile_allocator_service"
    BROWSER_QUERY_SERVICE = "browser.query_service"
    BROWSER_TOOL_APPLICATION_SERVICE = "browser.tool_application_service"
    BROWSER_OBSERVATION_SERVICE = "browser.observation_service"
    BROWSER_FACADE = "browser.facade"
    BROWSER_RESULT_SERIALIZER = "browser.result_serializer"
    MOBILE_INFRASTRUCTURE = "mobile.infrastructure"
    MOBILE_SYSTEM_CONFIG_STORE = "mobile.system_config_store"
    MOBILE_FACADE = "mobile.facade"
    MOBILE_RESULT_SERIALIZER = "mobile.result_serializer"
    OCR_SERVICE = "ocr.service"
    OCR_RESULT_SERIALIZER = "ocr.result_serializer"

    MEMORY_BOOTSTRAP_CONFIG = "memory.bootstrap_config"
    MEMORY_SPACE_SERVICE = "memory.space_service"
    MEMORY_POLICY_SERVICE = "memory.policy_service"
    FILE_MEMORY_SERVICE = "memory.file_service"
    MEMORY_CONTEXT_RESOLVER = "memory.context_resolver"
    MEMORY_LEGACY_MIGRATION_SERVICE = "memory.legacy_migration_service"
    MEMORY_QUERY_SERVICE = "memory.query_service"
    MEMORY_RUNTIME_SERVICE = "memory.runtime_service"
    MEMORY_WATCH_REGISTRY = "memory.watch_registry"

    TOOL_BOOTSTRAP_CONFIG = "tool.bootstrap_config"
    TOOL_CAPABILITY_CATALOG = "tool.capability_catalog"
    TOOL_CAPABILITY_BINDINGS = "tool.capability_bindings"
    TOOL_PACKAGE_PLANS = "tool.package_plans"
    TOOL_LOCAL_RUNTIME_REGISTRY = "tool.local_runtime_registry"
    TOOL_DISCOVERY_REGISTRY = "tool.discovery_registry"
    TOOL_FUNCTION_COMMAND_SERVICE = "tool.function_command_service"
    TOOL_SOURCE_COMMAND_SERVICE = "tool.source_command_service"
    TOOL_SOURCE_QUERY_SERVICE = "tool.source_query_service"
    TOOL_SOURCE_DISCOVERY_SERVICE = "tool.source_discovery_service"
    TOOL_CONFIGURED_RUNTIME_ACTIVATOR = "tool.configured_runtime_activator"
    TOOL_REMOTE_RUNTIME_REGISTRY = "tool.remote_runtime_registry"
    TOOL_SANDBOX_RUNTIME_REGISTRY = "tool.sandbox_runtime_registry"
    TOOL_RUNTIME_GATEWAY = "tool.runtime_gateway"
    TOOL_RUNTIME_POOL_SERVICE = "tool.runtime_pool_service"
    TOOL_SERVICE = "tool.service"
    TOOL_QUERY_SERVICE = "tool.query_service"
    TOOL_RUN_CONTROL_SERVICE = "tool.run_control_service"
    TOOL_ORCHESTRATION_PORT = "tool.orchestration_port"
    TOOL_SCHEDULER_SERVICE = "tool.scheduler_service"
    TOOL_WORKER_REGISTRY_SERVICE = "tool.worker_registry_service"
    TOOL_WORKER_SERVICE = "tool.worker_service"
    TOOL_CLEANUP_CALLBACKS = "tool.cleanup_callbacks"

    LLM_ADAPTER_REGISTRY = "llm.adapter_registry"
    LLM_SERVICE = "llm.service"

    RUNTIME_BOOTSTRAP_CONFIG = "runtime.bootstrap_config"
    ORCHESTRATION_RUN_QUERY_SERVICE = "orchestration.run_query_service"
    ORCHESTRATION_SUBMISSION_SERVICE = "orchestration.submission_service"
    ORCHESTRATION_INSPECTION_SERVICE = "orchestration.inspection_service"
    ORCHESTRATION_APPROVAL_CONTROL_SERVICE = "orchestration.approval_control_service"
    ORCHESTRATION_CANCELLATION_SERVICE = "orchestration.cancellation_service"
    ORCHESTRATION_INTAKE_SERVICE = "orchestration.intake_service"
    ORCHESTRATION_INGRESS_PROCESSING_SERVICE = (
        "orchestration.ingress_processing_service"
    )
    ORCHESTRATION_SCHEDULER_MAINTENANCE_SERVICE = (
        "orchestration.scheduler_maintenance_service"
    )
    ORCHESTRATION_EXECUTOR_CONTROL_SERVICE = "orchestration.executor_control_service"
    ORCHESTRATION_RUN_ENQUEUED_CALLBACK_BINDING_SERVICE = (
        "orchestration.run_enqueued_callback_binding_service"
    )
    ORCHESTRATION_SCHEDULER_SERVICE = "orchestration.scheduler_service"
    ORCHESTRATION_EXECUTOR_SERVICE = "orchestration.executor_service"
    ORCHESTRATION_SCHEDULER_RUNTIME_EVENT_SERVICE = (
        "orchestration.scheduler_runtime_event_service"
    )
    EVENT_RELAY_RUNTIME_EVENT_SERVICE = "event_relay.runtime_event_service"
    TOOL_RUNTIME_EVENT_SERVICE = "tool.runtime_event_service"

    OPERATIONS_OBSERVATION_STORE = "operations.observation_store"
    OPERATIONS_ACTION_AUDIT_STORE = "operations.action_audit_store"
    OPERATIONS_PROJECTION_STORE = "operations.projection_store"
    OPERATIONS_SOURCE_READ_MODEL_CONTEXT = "operations.source_read_model_context"
    OPERATIONS_READ_MODEL_PROVIDER = "operations.read_model_provider"
    OPERATIONS_PROJECTION_MATERIALIZER = "operations.projection_materializer"
    OPERATIONS_OBSERVER_RUNTIME_EVENT_SERVICE = (
        "operations.observer_runtime_event_service"
    )


__all__ = ["AppKey"]
