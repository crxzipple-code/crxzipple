from __future__ import annotations

from time import perf_counter

from crxzipple.modules.context_workspace.application.context_control_slice_builder import (
    build_context_control_slice,
)
from crxzipple.modules.context_workspace.application.context_observation_slice_builder import (
    build_context_observation_slice,
)
from crxzipple.modules.context_workspace.application.context_slice_item_projection import (
    SessionItemResolver,
)
from crxzipple.modules.context_workspace.application.context_slice_selection import (
    normalize_slice_audience,
    visible_nodes_for_slice,
)
from crxzipple.modules.context_workspace.application.context_tree_maintenance import (
    ensure_default_root_nodes,
    refresh_owner_children,
)
from crxzipple.modules.context_workspace.application.models import (
    BuildContextControlSliceInput,
    BuildContextObservationSliceInput,
    ContextControlSlice,
    ContextSlice,
)
from crxzipple.modules.context_workspace.application.ports import ContextOwnerRegistry
from crxzipple.modules.context_workspace.domain import (
    ContextNodeRepository,
    ContextWorkspace,
    ContextWorkspaceNotFoundError,
    ContextWorkspaceRepository,
)


class ContextSliceBuilderService:
    def __init__(
        self,
        *,
        workspace_repository: ContextWorkspaceRepository,
        node_repository: ContextNodeRepository,
        owner_registry: ContextOwnerRegistry | None = None,
        session_item_resolver: SessionItemResolver | None = None,
    ) -> None:
        self._workspaces = workspace_repository
        self._nodes = node_repository
        self._owner_registry = owner_registry
        self._session_item_resolver = session_item_resolver

    def build_slice(
        self,
        *,
        session_key: str = "",
        run_id: str = "",
        audience: str = "llm_request",
        provider_profile: str | None = None,
        data: BuildContextObservationSliceInput | None = None,
    ) -> ContextSlice:
        if data is not None:
            session_key = data.session_key
            run_id = data.run_id
            audience = data.audience
            provider_profile = data.provider_profile
            request_metadata = dict(data.metadata)
        else:
            request_metadata = {}
        timings_started_at = perf_counter()
        phase_started_at = timings_started_at
        builder_timings: dict[str, float] = {}

        def record_timing(label: str) -> None:
            nonlocal phase_started_at
            now = perf_counter()
            builder_timings[f"{label}_ms"] = round(
                (now - phase_started_at) * 1000,
                3,
            )
            phase_started_at = now

        audience = normalize_slice_audience(audience)
        workspace = self._require_workspace(session_key)
        record_timing("require_workspace")
        read_only = request_metadata.get("read_only") is True
        if not read_only:
            ensure_default_root_nodes(
                workspace=workspace,
                node_repository=self._nodes,
            )
            refresh_owner_children(
                workspace=workspace,
                node_repository=self._nodes,
                owner_registry=self._owner_registry,
            )
        record_timing("refresh_owner_children")
        nodes = self._nodes.list_for_workspace(workspace.id)
        record_timing("list_nodes")
        return build_context_observation_slice(
            workspace=workspace,
            nodes=nodes,
            run_id=run_id,
            audience=audience,
            provider_profile=provider_profile,
            request_metadata=request_metadata,
            read_only=read_only,
            session_item_resolver=self._session_item_resolver,
            builder_timings=builder_timings,
            timings_started_at=timings_started_at,
        )

    def _require_workspace(self, session_key: str) -> ContextWorkspace:
        workspace = self._workspaces.get_by_session(session_key)
        if workspace is None:
            raise ContextWorkspaceNotFoundError(
                f"Context workspace for session '{session_key}' was not found.",
            )
        return workspace


class ContextControlSliceService:
    def __init__(
        self,
        *,
        workspace_repository: ContextWorkspaceRepository,
        node_repository: ContextNodeRepository,
    ) -> None:
        self._workspaces = workspace_repository
        self._nodes = node_repository

    def build_control_slice(
        self,
        *,
        session_key: str = "",
        run_id: str = "",
        audience: str = "llm_request",
        provider_profile: str | None = None,
        data: BuildContextControlSliceInput | None = None,
    ) -> ContextControlSlice:
        if data is not None:
            session_key = data.session_key
            run_id = data.run_id
            audience = data.audience
            provider_profile = data.provider_profile
            request_metadata = dict(data.metadata)
        else:
            request_metadata = {}
        audience = normalize_slice_audience(audience)
        workspace = self._require_workspace(session_key)
        read_only = request_metadata.get("read_only") is True
        if not read_only:
            ensure_default_root_nodes(
                workspace=workspace,
                node_repository=self._nodes,
            )
        nodes = self._nodes.list_for_workspace(workspace.id)
        visible_nodes = visible_nodes_for_slice(nodes, audience=audience)
        return build_context_control_slice(
            workspace=workspace,
            nodes=nodes,
            visible_nodes=visible_nodes,
            run_id=run_id,
            audience=audience,
            provider_profile=provider_profile,
            request_metadata=request_metadata,
            read_only=read_only,
        )

    def _require_workspace(self, session_key: str) -> ContextWorkspace:
        workspace = self._workspaces.get_by_session(session_key)
        if workspace is None:
            raise ContextWorkspaceNotFoundError(
                f"Context workspace for session '{session_key}' was not found.",
            )
        return workspace
