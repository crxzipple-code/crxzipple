"""Agent home context tree adapter."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from crxzipple.modules.agent.domain.exceptions import AgentError
from crxzipple.modules.context_workspace.application import ContextChildrenRequest
from crxzipple.modules.context_workspace.domain import (
    ContextAction,
    ContextEstimate,
    ContextNodeSeed,
    ContextNodeState,
)


class AgentHomeContextService(Protocol):
    def inspect_profile_home(self, profile_id: str) -> object:
        ...


class AgentHomeContextNodeProvider:
    owner = "agent"

    def __init__(self, agent_service: AgentHomeContextService) -> None:
        self._agent_service = agent_service

    def children(
        self,
        request: ContextChildrenRequest,
    ) -> tuple[ContextNodeSeed, ...]:
        if request.node.id != "agent.home":
            return ()
        try:
            snapshot = self._agent_service.inspect_profile_home(
                request.workspace.agent_id,
            )
        except (AgentError, OSError):
            return ()
        files = _agent_home_files(snapshot)
        return tuple(
            _agent_home_file_node_seed(
                file,
                parent_id=request.node.id,
                display_order=index * 10,
                home_dir=_optional_text(getattr(snapshot, "home_dir", None)),
            )
            for index, file in enumerate(files, start=1)
        )


@dataclass(frozen=True, slots=True)
class _AgentHomeFile:
    name: str
    path: str | None
    role: str
    content: str
    truncated: bool


_FILE_ROLES = {
    "AGENT.md": "agent_instructions",
    "SOUL.md": "style",
    "USER.md": "user_preferences",
    "IDENTITY.md": "identity",
}
_FILE_ORDER = tuple(_FILE_ROLES)
_MAX_FILE_CHARS = 20_000
_SUMMARY_CHARS = 1_600
_AGENT_HOME_FILE_ACTIONS = (
    ContextAction.EXPAND,
    ContextAction.COLLAPSE,
    ContextAction.PIN,
    ContextAction.UNPIN,
    ContextAction.ESTIMATE,
)


def _agent_home_files(snapshot) -> tuple[_AgentHomeFile, ...]:
    files_by_name = {
        str(getattr(item, "name", "")).strip(): item
        for item in getattr(snapshot, "files", ()) or ()
    }
    files: list[_AgentHomeFile] = []
    for name in _FILE_ORDER:
        item = files_by_name.get(name)
        if item is None or not bool(getattr(item, "exists", False)):
            continue
        content = str(getattr(item, "content", "") or "")
        if not content.strip():
            continue
        truncated = len(content) > _MAX_FILE_CHARS
        files.append(
            _AgentHomeFile(
                name=name,
                path=_optional_text(getattr(item, "path", None)),
                role=_FILE_ROLES[name],
                content=content[:_MAX_FILE_CHARS],
                truncated=truncated,
            ),
        )
    return tuple(files)


def _agent_home_file_node_seed(
    file: _AgentHomeFile,
    *,
    parent_id: str,
    display_order: int,
    home_dir: str | None,
) -> ContextNodeSeed:
    content = file.content.strip()
    summary = _truncate(content, _SUMMARY_CHARS)
    collapsed = file.name != "AGENT.md"
    metadata = {
        "name": file.name,
        "role": file.role,
        "source": "agent.home",
        "content_chars": len(content),
        "truncated": file.truncated,
    }
    owner_ref = {"name": file.name, "role": file.role}
    if home_dir is not None:
        metadata["home_dir"] = home_dir
        owner_ref["home_dir"] = home_dir
    if file.path is not None:
        metadata["path"] = file.path
        owner_ref["path"] = file.path
    return ContextNodeSeed(
        node_id=f"agent.home.{file.name}",
        parent_id=parent_id,
        owner="agent",
        kind="agent_home_file",
        title=file.name,
        summary=summary,
        state=ContextNodeState(collapsed=collapsed, loaded=True),
        actions=_AGENT_HOME_FILE_ACTIONS,
        owner_ref=owner_ref,
        estimate=_text_estimate(summary),
        display_order=display_order,
        metadata=metadata,
    )


def _text_estimate(text: str) -> ContextEstimate:
    normalized = text or ""
    return ContextEstimate(
        text_chars=len(normalized),
        text_tokens=max((len(normalized) + 3) // 4, 1) if normalized else 0,
    )


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _truncate(value: str, limit: int) -> str:
    text = value.strip()
    if len(text) <= limit:
        return text
    return text[: max(limit - 1, 0)].rstrip() + "..."


__all__ = ["AgentHomeContextNodeProvider"]
