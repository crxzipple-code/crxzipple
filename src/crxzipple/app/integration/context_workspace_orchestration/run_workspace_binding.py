from __future__ import annotations

from crxzipple.modules.context_workspace.application import (
    ContextWorkspaceService,
    EnsureContextWorkspaceInput,
)
from crxzipple.modules.context_workspace.domain import (
    ContextWorkspace,
    ContextWorkspaceNotFoundError,
)


class RunWorkspaceBindingAdapter:
    def __init__(self, workspace_service: ContextWorkspaceService) -> None:
        self._workspace_service = workspace_service

    def workspace_for_request_snapshot(
        self,
        *,
        session_key: str,
        agent_id: str,
        metadata: dict[str, object],
        persist: bool,
    ) -> ContextWorkspace:
        if persist:
            return self._workspace_service.ensure_workspace(
                EnsureContextWorkspaceInput(
                    session_key=session_key,
                    agent_id=agent_id,
                    metadata=metadata,
                    refresh_expanded_children=False,
                ),
            )
        try:
            return self._workspace_service.get_by_session(session_key)
        except ContextWorkspaceNotFoundError:
            return self._workspace_service.ensure_workspace(
                EnsureContextWorkspaceInput(
                    session_key=session_key,
                    agent_id=agent_id,
                    metadata=metadata,
                    refresh_expanded_children=False,
                ),
            )
