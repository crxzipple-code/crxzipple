from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from crxzipple.modules.operations.application.read_models.ports_access_settings import (
    OperationsAccessReadinessPort,
    OperationsSettingsQueryPort,
)
from crxzipple.modules.operations.application.read_models.ports_context import (
    OperationsContextObservationSnapshotPort,
    OperationsContextSliceBuilderPort,
    OperationsContextTreePort,
    OperationsContextWorkspacePort,
    OperationsMemoryQueryPort,
    OperationsMemoryWatchRegistryPort,
    OperationsSkillCatalogPort,
)
from crxzipple.modules.operations.application.read_models.ports_llm_agent import (
    OperationsAgentProfilePort,
    OperationsLlmQueryPort,
)
from crxzipple.modules.operations.application.read_models.ports_runtime import (
    OperationsEventContractRegistryPort,
    OperationsEventDefinitionRegistryPort,
    OperationsEventStreamPort,
    OperationsObservationReadPort,
    OperationsObserverRuntimePort,
    OperationsRuntimeBootstrapConfigPort,
)
from crxzipple.modules.operations.application.read_models.ports_runtime_sources import (
    OperationsBrowserProfilePort,
    OperationsChannelInteractionPort,
    OperationsChannelProfilePort,
    OperationsChannelRuntimePort,
    OperationsDaemonManagerPort,
    OperationsDaemonRegistryPort,
    OperationsProcessQueryPort,
)
from crxzipple.modules.operations.application.read_models.ports_tooling import (
    OperationsArtifactReadPort,
    OperationsRemoteToolRuntimeRegistryPort,
    OperationsToolQueryPort,
)

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
