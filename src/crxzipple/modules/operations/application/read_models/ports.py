from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol

from crxzipple.modules.operations.application.ports import (
    OperationsEventPublishPort as OperationsEventPublishPort,
    OperationsEventStreamPort as OperationsEventStreamPort,
)


class OperationsRuntimeBootstrapConfigPort(Protocol):
    orchestration_run_lease_seconds: float
    orchestration_run_heartbeat_seconds: float
    orchestration_executor_max_concurrent_assignments: int
    orchestration_auto_compaction_enabled: bool
    orchestration_auto_compaction_reserve_tokens: int
    orchestration_auto_compaction_soft_threshold_tokens: int
    tool_run_max_attempts: int
    tool_run_lease_seconds: int
    tool_run_heartbeat_seconds: float
    tool_worker_max_in_flight: int
    tool_worker_default_run_concurrency: int
    tool_worker_image_run_concurrency: int
    tool_worker_shared_state_run_concurrency: int
    tool_remote_default_max_concurrency: int


class OperationsObservationReadPort(Protocol):
    def get_module_observation(self, module: str) -> Any | None: ...

    def snapshot(self) -> Any: ...

    def list_event_buckets(
        self,
        *,
        module: str | None = None,
        event_name: str | None = None,
        since: Any | None = None,
        limit: int = 500,
    ) -> tuple[Mapping[str, Any], ...]: ...


class OperationsEventContractRegistryPort(Protocol):
    def to_payload(self) -> dict[str, Any]: ...

    def list_topic_contracts(self) -> tuple[Any, ...]: ...

    def list_route_contracts(self) -> tuple[Any, ...]: ...


class OperationsEventDefinitionRegistryPort(Protocol):
    def to_payload(self) -> dict[str, Any]: ...

    def list_definitions(self) -> tuple[Any, ...]: ...

    def list_surfaces(self) -> tuple[Any, ...]: ...

    def list_observers(self) -> tuple[Any, ...]: ...


class OperationsAccessReadinessPort(Protocol):
    def check_requirement(self, requirement: str) -> Any: ...

    def check_requirements(self, requirements: tuple[str, ...]) -> tuple[Any, ...]: ...

    def check_credential_binding(
        self,
        binding_id: str,
        *,
        allow_literal: bool = False,
    ) -> Any: ...


class OperationsSettingsQueryPort(Protocol):
    def get_resource(self, resource_id: str) -> Any: ...

    def list_resources(
        self,
        *,
        resource_kind: str | None = None,
        owner_module: str | None = None,
    ) -> tuple[Any, ...]: ...

    def list_versions(self, resource_id: str) -> tuple[Any, ...]: ...

    def get_effective(
        self,
        resource_id: str,
        *,
        environment: str | None = None,
        trace_context: Mapping[str, Any] | None = None,
    ) -> Any: ...

    def latest_snapshot(
        self,
        resource_id: str,
        *,
        environment: str | None = None,
    ) -> Any | None: ...

    def list_overrides(
        self,
        resource_id: str,
        *,
        environment: str | None = None,
    ) -> tuple[Any, ...]: ...

    def list_audits(self) -> tuple[Any, ...]: ...


class OperationsToolQueryPort(Protocol):
    @property
    def concurrency_policy(self) -> Any: ...

    def list_tools(self) -> tuple[Any, ...]: ...

    def list_enabled_tools(self) -> tuple[Any, ...]: ...

    def list_tool_runs(self) -> tuple[Any, ...]: ...

    def list_tool_workers(self) -> tuple[Any, ...]: ...

    def list_tool_run_assignments(self) -> tuple[Any, ...]: ...

    def check_readiness(self, tool_id: str) -> dict[str, Any] | None: ...

    def check_access_readiness(self, tool_id: str) -> Any | None: ...

    def list_sources(self) -> tuple[Any, ...]: ...

    def list_functions(self) -> tuple[Any, ...]: ...

    def list_provider_backends(self) -> tuple[Any, ...]: ...

    def check_provider_backend_readiness(self, backend: Any) -> Any | None: ...

    def list_source_discovery_runs(
        self,
        source_id: str,
        *,
        limit: int = 20,
    ) -> tuple[Any, ...]: ...


class OperationsArtifactReadPort(Protocol):
    def get_artifact(self, artifact_id: str) -> Any: ...


class OperationsLlmQueryPort(Protocol):
    def list_profiles(self) -> list[Any]: ...

    def list_invocations(self, *, limit: int = 100) -> list[Any]: ...

    def list_response_events(
        self,
        invocation_id: str,
        *,
        limit: int | None = None,
        after_sequence: int | None = None,
    ) -> list[Any]: ...

    def response_event_retention_policy(self) -> Any: ...


class OperationsAgentProfilePort(Protocol):
    def list_profiles(self) -> list[Any]: ...

    def get_profile(self, profile_id: str) -> Any: ...


class OperationsMemoryQueryPort(Protocol):
    def agent_scope_inventory(
        self,
        agent_id: str,
        *,
        file_limit: int = 240,
    ) -> Any: ...

    def search_agent(
        self,
        agent_id: str,
        *,
        query: str,
        limit: int = 20,
    ) -> tuple[Any, ...]: ...

    def get_agent_excerpt(
        self,
        agent_id: str,
        *,
        path: str,
        start_line: int | None = None,
        line_count: int | None = None,
    ) -> Any | None: ...

    def get_agent_long_term_excerpt(self, agent_id: str) -> Any | None: ...


class OperationsMemoryWatchRegistryPort(Protocol):
    def snapshot_metrics(self) -> Any: ...


class OperationsContextWorkspacePort(Protocol):
    def list_workspaces(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[Any, ...]: ...


class OperationsContextTreePort(Protocol):
    def list_tree(self, session_key: str) -> Any: ...


class OperationsContextObservationSnapshotPort(Protocol):
    def list_recent_snapshots(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[Any, ...]: ...


class OperationsContextSliceBuilderPort(Protocol):
    def build_slice(self, **kwargs: Any) -> Any: ...


class OperationsSkillCatalogPort(Protocol):
    def list_available(
        self,
        *,
        workspace_dir: str | None = None,
        surface: str | None = None,
    ) -> tuple[Any, ...]: ...


class OperationsBrowserProfilePort(Protocol):
    def list_profiles(self) -> tuple[Any, ...]: ...

    def list_pools(self) -> tuple[Any, ...]: ...

    def list_allocations(self) -> tuple[Any, ...]: ...


class OperationsChannelProfilePort(Protocol):
    def list_profiles(self) -> tuple[Any, ...]: ...


class OperationsChannelRuntimePort(Protocol):
    def list_runtimes(self, *, channel_type: str | None = None) -> tuple[Any, ...]: ...

    def list_account_bindings(
        self,
        *,
        runtime_id: str | None = None,
    ) -> tuple[Any, ...]: ...

    def list_connection_bindings(
        self,
        *,
        runtime_id: str | None = None,
    ) -> tuple[Any, ...]: ...


class OperationsChannelInteractionPort(Protocol):
    def list_interactions(self) -> tuple[Any, ...]: ...


class OperationsDaemonRegistryPort(Protocol):
    def list_service_specs(self) -> tuple[Any, ...]: ...

    def list_service_sets(self) -> tuple[Any, ...]: ...

    def list_leases(self, *, service_key: str | None = None) -> tuple[Any, ...]: ...


class OperationsDaemonManagerPort(Protocol):
    def list_instances(self, *, refresh: bool = False) -> tuple[Any, ...]: ...


class OperationsProcessQueryPort(Protocol):
    def list_sessions_metadata(self) -> tuple[Any, ...]: ...

    def list_sessions(self) -> tuple[Any, ...]: ...

    def get_session(self, session_id: str) -> Any | None: ...

    def read_output(self, session_id: str, *, tail: int | None = None) -> str: ...


class OperationsRuntimeMetricsPort(Protocol):
    def snapshot(self) -> Mapping[str, Any]: ...


class OperationsRemoteToolRuntimeRegistryPort(Protocol):
    def snapshot(self) -> Mapping[str, Any]: ...

    def registrations(self) -> tuple[Any, ...]: ...


class OperationsObserverRuntimePort(Protocol):
    @property
    def subscriptions(self) -> tuple[Any, ...]: ...

    def snapshot(self) -> Any: ...
