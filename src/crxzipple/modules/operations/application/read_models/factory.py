from __future__ import annotations

from typing import Any

from crxzipple.modules.operations.application.read_models.access import (
    AccessOperationsReadModelProvider,
)
from crxzipple.modules.operations.application.read_models.channels import (
    ChannelsOperationsReadModelProvider,
)
from crxzipple.modules.operations.application.read_models.daemon import (
    DaemonOperationsReadModelProvider,
)
from crxzipple.modules.operations.application.read_models.events import (
    EventsOperationsReadModelProvider,
)
from crxzipple.modules.operations.application.read_models.facade import (
    OperationsReadModelProvider,
)
from crxzipple.modules.operations.application.read_models.llm import (
    LlmOperationsReadModelProvider,
)
from crxzipple.modules.operations.application.read_models.memory import (
    MemoryOperationsReadModelProvider,
)
from crxzipple.modules.operations.application.read_models.modules import (
    OperationsModuleQuerySet,
    OperationsModuleReadModelProvider,
)
from crxzipple.modules.operations.application.read_models.orchestration import (
    OrchestrationOperationsReadModelProvider,
)
from crxzipple.modules.operations.application.read_models.skills import (
    SkillsOperationsReadModelProvider,
)
from crxzipple.modules.operations.application.read_models.tool import (
    ToolOperationsReadModelProvider,
)
from crxzipple.shared.runtime_metrics import get_runtime_metrics_registry


def build_operations_source_read_model_provider(
    container: Any,
) -> OperationsReadModelProvider:
    """Builds the source projector used by the operations observer sidecar."""

    return OperationsReadModelProvider(
        orchestration=OrchestrationOperationsReadModelProvider(
            run_query=container.orchestration_run_query_service,
            executor_control=container.orchestration_executor_service,
            ingress_query=container.orchestration_run_query_service,
            scheduler_signal_query=container.orchestration_run_query_service,
            operations_observation=container.operations_observation_store,
            worker_lease_seconds=container.settings.orchestration_run_lease_seconds,
            worker_heartbeat_seconds=(
                container.settings.orchestration_run_heartbeat_seconds
            ),
        ),
        tool=ToolOperationsReadModelProvider(
            tool_service=container.tool_service,
            access_service=container.access_service,
            artifact_service=container.artifact_service,
            events_service=container.events_service,
            event_definition_registry=container.event_definition_registry,
            operations_observation=container.operations_observation_store,
            runtime_metrics=get_runtime_metrics_registry(),
            runtime_registry=container.remote_tool_registry,
        ),
        llm=LlmOperationsReadModelProvider(
            llm_service=container.llm_service,
            access_service=container.access_service,
            run_query=container.orchestration_run_query_service,
            events_service=container.events_service,
            event_definition_registry=container.event_definition_registry,
            operations_observation=container.operations_observation_store,
            runtime_metrics=get_runtime_metrics_registry(),
        ),
        memory=MemoryOperationsReadModelProvider(
            agent_service=container.agent_service,
            file_memory_service=container.file_memory_service,
            memory_context_resolver=container.memory_context_resolver,
            memory_watch_registry=container.memory_watch_registry,
            events_service=container.events_service,
            event_definition_registry=container.event_definition_registry,
            operations_observation=container.operations_observation_store,
        ),
        skills=SkillsOperationsReadModelProvider(
            skill_manager=container.skill_manager,
            tool_service=container.tool_service,
            access_service=container.access_service,
            agent_service=container.agent_service,
            events_service=container.events_service,
            event_definition_registry=container.event_definition_registry,
            operations_observation=container.operations_observation_store,
        ),
        access=AccessOperationsReadModelProvider(
            access_service=container.access_service,
            llm_service=container.llm_service,
            tool_service=container.tool_service,
            channel_profile_service=container.channel_profile_service,
            lark_channel_runtime_service=container.lark_channel_runtime_service,
            web_channel_runtime_service=container.web_channel_runtime_service,
            webhook_channel_runtime_service=container.webhook_channel_runtime_service,
            events_service=container.events_service,
            event_definition_registry=container.event_definition_registry,
            operations_observation=container.operations_observation_store,
        ),
        channels=ChannelsOperationsReadModelProvider(
            channel_profile_service=container.channel_profile_service,
            channel_runtime_manager=container.channel_runtime_manager,
            channel_interaction_service=container.channel_interaction_service,
            events_service=container.events_service,
            event_contract_registry=container.event_contract_registry,
            event_definition_registry=container.event_definition_registry,
        ),
        events=EventsOperationsReadModelProvider(
            events_service=container.events_service,
            event_contract_registry=container.event_contract_registry,
            event_definition_registry=container.event_definition_registry,
            operations_observation=container.operations_observation_store,
            operations_observer_runtime=container.operations_observer_runtime_event_service,
        ),
        daemon=DaemonOperationsReadModelProvider(
            daemon_service=container.daemon_service,
            daemon_manager=container.daemon_manager,
            events_service=container.events_service,
            event_definition_registry=container.event_definition_registry,
            operations_observation=container.operations_observation_store,
            process_service=container.process_service,
        ),
        modules=OperationsModuleReadModelProvider(
            module_query=OperationsModuleQuerySet(
                access_service=container.access_service,
                agent_service=container.agent_service,
                channel_profile_service=container.channel_profile_service,
                channel_runtime_manager=container.channel_runtime_manager,
                daemon_manager=container.daemon_manager,
                daemon_service=container.daemon_service,
                event_contract_registry=container.event_contract_registry,
                event_definition_registry=container.event_definition_registry,
                events_service=container.events_service,
                operations_observation_store=container.operations_observation_store,
                file_memory_service=container.file_memory_service,
                lark_channel_runtime_service=container.lark_channel_runtime_service,
                llm_service=container.llm_service,
                memory_context_resolver=container.memory_context_resolver,
                skill_manager=container.skill_manager,
                tool_service=container.tool_service,
                web_channel_runtime_service=container.web_channel_runtime_service,
                webhook_channel_runtime_service=container.webhook_channel_runtime_service,
            ),
        ),
    )
