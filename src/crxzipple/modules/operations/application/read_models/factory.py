from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from crxzipple.modules.operations.application.read_models.access import (
    AccessOperationsReadModelProvider,
)
from crxzipple.modules.operations.application.read_models.channels import (
    ChannelsOperationsReadModelProvider,
)
from crxzipple.modules.operations.application.read_models.browser import (
    BrowserOperationsReadModelProvider,
)
from crxzipple.modules.operations.application.read_models.context_workspace import (
    ContextWorkspaceOperationsReadModelProvider,
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
from crxzipple.modules.operations.application.read_models.ports import (
    OperationsAccessReadinessPort,
    OperationsAgentProfilePort,
    OperationsArtifactReadPort,
    OperationsBrowserProfilePort,
    OperationsChannelInteractionPort,
    OperationsChannelProfilePort,
    OperationsChannelRuntimePort,
    OperationsContextSliceBuilderPort,
    OperationsContextObservationSnapshotPort,
    OperationsContextTreePort,
    OperationsContextWorkspacePort,
    OperationsDaemonManagerPort,
    OperationsDaemonRegistryPort,
    OperationsEventContractRegistryPort,
    OperationsEventDefinitionRegistryPort,
    OperationsEventStreamPort,
    OperationsLlmQueryPort,
    OperationsMemoryQueryPort,
    OperationsMemoryWatchRegistryPort,
    OperationsObservationReadPort,
    OperationsObserverRuntimePort,
    OperationsProcessQueryPort,
    OperationsRemoteToolRuntimeRegistryPort,
    OperationsRuntimeBootstrapConfigPort,
    OperationsSettingsQueryPort,
    OperationsSkillCatalogPort,
    OperationsToolQueryPort,
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

if TYPE_CHECKING:
    from crxzipple.modules.orchestration.application import (
        OrchestrationExecutorLeaseQueryPort,
        OrchestrationRunQueryPort,
    )


@dataclass(slots=True)
class OperationsSourceReadModelContext:
    runtime_bootstrap_config: OperationsRuntimeBootstrapConfigPort
    events_service: OperationsEventStreamPort | None
    event_contract_registry: OperationsEventContractRegistryPort
    event_definition_registry: OperationsEventDefinitionRegistryPort
    operations_observation_store: OperationsObservationReadPort
    access_governance_repository: Any | None
    settings_query_service: OperationsSettingsQueryPort | None
    settings_environment: str | None
    orchestration_run_query_service: OrchestrationRunQueryPort
    orchestration_executor_lease_query: OrchestrationExecutorLeaseQueryPort
    tool_service: OperationsToolQueryPort
    access_service: OperationsAccessReadinessPort
    artifact_service: OperationsArtifactReadPort
    remote_tool_registry: OperationsRemoteToolRuntimeRegistryPort
    llm_service: OperationsLlmQueryPort
    agent_service: OperationsAgentProfilePort
    memory_query_service: OperationsMemoryQueryPort
    memory_watch_registry: OperationsMemoryWatchRegistryPort | None
    context_workspace_service: OperationsContextWorkspacePort
    context_tree_service: OperationsContextTreePort
    context_observation_snapshot_service: OperationsContextObservationSnapshotPort
    context_slice_builder: OperationsContextSliceBuilderPort
    skill_manager: OperationsSkillCatalogPort
    browser_profile_service: OperationsBrowserProfilePort
    channel_profile_service: OperationsChannelProfilePort
    channel_runtime_manager: OperationsChannelRuntimePort
    channel_interaction_service: OperationsChannelInteractionPort
    daemon_service: OperationsDaemonRegistryPort
    daemon_manager: OperationsDaemonManagerPort
    process_service: OperationsProcessQueryPort
    operations_observer_runtime_event_service: (
        OperationsObserverRuntimePort | None
    ) = None

    def attach_operations_observer_runtime(
        self,
        runtime: OperationsObserverRuntimePort | None,
    ) -> None:
        self.operations_observer_runtime_event_service = runtime

    def current_operations_observer_runtime(
        self,
    ) -> OperationsObserverRuntimePort | None:
        return self.operations_observer_runtime_event_service


def build_operations_source_read_model_provider(
    context: OperationsSourceReadModelContext,
) -> OperationsReadModelProvider:
    """Builds the source projector used by the operations observer sidecar."""

    return OperationsReadModelProvider(
        orchestration=OrchestrationOperationsReadModelProvider(
            run_query=context.orchestration_run_query_service,
            executor_lease_query=context.orchestration_executor_lease_query,
            ingress_query=context.orchestration_run_query_service,
            continuation_query=context.orchestration_run_query_service,
            dispatch_query=context.orchestration_run_query_service,
            operations_observation=context.operations_observation_store,
            runtime_bootstrap_config=context.runtime_bootstrap_config,
            worker_lease_seconds=(
                context.runtime_bootstrap_config.orchestration_run_lease_seconds
            ),
            worker_heartbeat_seconds=(
                context.runtime_bootstrap_config.orchestration_run_heartbeat_seconds
            ),
        ),
        tool=ToolOperationsReadModelProvider(
            tool_service=context.tool_service,
            access_service=context.access_service,
            artifact_service=context.artifact_service,
            run_query=context.orchestration_run_query_service,
            events_service=context.events_service,
            event_definition_registry=context.event_definition_registry,
            operations_observation=context.operations_observation_store,
            runtime_metrics=get_runtime_metrics_registry(),
            runtime_registry=context.remote_tool_registry,
            runtime_bootstrap_config=context.runtime_bootstrap_config,
        ),
        browser=BrowserOperationsReadModelProvider(
            browser_profile_service=context.browser_profile_service,
            access_service=context.access_service,
            daemon_service=context.daemon_service,
            daemon_manager=context.daemon_manager,
            operations_observation=context.operations_observation_store,
        ),
        llm=LlmOperationsReadModelProvider(
            llm_service=context.llm_service,
            access_service=context.access_service,
            run_query=context.orchestration_run_query_service,
            events_service=context.events_service,
            event_definition_registry=context.event_definition_registry,
            operations_observation=context.operations_observation_store,
            runtime_metrics=get_runtime_metrics_registry(),
        ),
        memory=MemoryOperationsReadModelProvider(
            agent_service=context.agent_service,
            memory_query_service=context.memory_query_service,
            memory_watch_registry=context.memory_watch_registry,
            events_service=context.events_service,
            event_definition_registry=context.event_definition_registry,
            operations_observation=context.operations_observation_store,
        ),
        context_workspace=ContextWorkspaceOperationsReadModelProvider(
            workspace_service=context.context_workspace_service,
            tree_service=context.context_tree_service,
            observation_snapshot_service=context.context_observation_snapshot_service,
            slice_builder=context.context_slice_builder,
        ),
        skills=SkillsOperationsReadModelProvider(
            skill_manager=context.skill_manager,
            tool_service=context.tool_service,
            access_service=context.access_service,
            agent_service=context.agent_service,
            events_service=context.events_service,
            event_definition_registry=context.event_definition_registry,
            operations_observation=context.operations_observation_store,
        ),
        access=AccessOperationsReadModelProvider(
            access_service=context.access_service,
            access_governance_repository=context.access_governance_repository,
            llm_service=context.llm_service,
            tool_service=context.tool_service,
            channel_profile_service=context.channel_profile_service,
            lark_channel_runtime_service=None,
            web_channel_runtime_service=None,
            webhook_channel_runtime_service=None,
            settings_query_service=context.settings_query_service,
            settings_environment=context.settings_environment,
            events_service=context.events_service,
            event_definition_registry=context.event_definition_registry,
            operations_observation=context.operations_observation_store,
        ),
        channels=ChannelsOperationsReadModelProvider(
            channel_profile_service=context.channel_profile_service,
            channel_runtime_manager=context.channel_runtime_manager,
            channel_interaction_service=context.channel_interaction_service,
            events_service=context.events_service,
            event_contract_registry=context.event_contract_registry,
            event_definition_registry=context.event_definition_registry,
            operations_observation=context.operations_observation_store,
        ),
        events=EventsOperationsReadModelProvider(
            events_service=context.events_service,
            event_contract_registry=context.event_contract_registry,
            event_definition_registry=context.event_definition_registry,
            operations_observation=context.operations_observation_store,
            operations_observer_runtime_provider=(
                context.current_operations_observer_runtime
            ),
        ),
        daemon=DaemonOperationsReadModelProvider(
            daemon_service=context.daemon_service,
            daemon_manager=context.daemon_manager,
            events_service=context.events_service,
            event_definition_registry=context.event_definition_registry,
            operations_observation=context.operations_observation_store,
            process_service=context.process_service,
            runtime_bootstrap_config=context.runtime_bootstrap_config,
        ),
        modules=OperationsModuleReadModelProvider(
            module_query=OperationsModuleQuerySet(
                access_service=context.access_service,
                access_governance_repository=context.access_governance_repository,
                settings_query_service=context.settings_query_service,
                settings_environment=context.settings_environment,
                agent_service=context.agent_service,
                channel_profile_service=context.channel_profile_service,
                channel_runtime_manager=context.channel_runtime_manager,
                daemon_manager=context.daemon_manager,
                daemon_service=context.daemon_service,
                event_contract_registry=context.event_contract_registry,
                event_definition_registry=context.event_definition_registry,
                events_service=context.events_service,
                operations_observation_store=context.operations_observation_store,
                llm_service=context.llm_service,
                memory_query_service=context.memory_query_service,
                skill_manager=context.skill_manager,
                browser_profile_service=context.browser_profile_service,
                tool_service=context.tool_service,
            ),
        ),
    )
