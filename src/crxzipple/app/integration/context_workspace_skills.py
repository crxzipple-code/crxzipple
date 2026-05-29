"""Skills context tree adapter."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol
from urllib.parse import quote

from crxzipple.modules.context_workspace.application import ContextChildrenRequest
from crxzipple.modules.context_workspace.domain import (
    ContextAction,
    ContextEstimate,
    ContextNodeSeed,
    ContextNodeState,
)
from crxzipple.modules.skills.application import (
    SkillPackage,
    SkillReadResult,
)
from crxzipple.modules.skills.domain import SkillError


class SkillContextService(Protocol):
    def list_available(
        self,
        *,
        workspace_dir: str | None,
        surface: str,
        include_disabled: bool = False,
    ) -> tuple[SkillPackage, ...]:
        ...

    def get(
        self,
        *,
        workspace_dir: str | None,
        skill_name: str,
        surface: str,
        include_disabled: bool = False,
    ) -> SkillPackage:
        ...

    def read(
        self,
        *,
        workspace_dir: str | None,
        skill_name: str,
        path: str | None,
        surface: str,
    ) -> SkillReadResult:
        ...


class SkillContextNodeProvider:
    owner = "skills"

    def __init__(self, skill_service: SkillContextService) -> None:
        self._skill_service = skill_service

    def children(
        self,
        request: ContextChildrenRequest,
    ) -> tuple[ContextNodeSeed, ...]:
        if request.node.id == "skills.available":
            return self._available_skill_children(request)
        if request.node.kind == "skill":
            return self._skill_detail_children(request)
        return ()

    def _available_skill_children(
        self,
        request: ContextChildrenRequest,
    ) -> tuple[ContextNodeSeed, ...]:
        workspace_dir = _workspace_dir(request)
        surface = _surface(request)
        packages = self._packages_for_workspace(
            workspace_dir=workspace_dir,
            surface=surface,
            skill_names=_available_skill_names(request.workspace.metadata),
        )
        return tuple(
            _skill_node_seed(
                package,
                parent_id=request.node.id,
                workspace_dir=workspace_dir,
                surface=surface,
                display_order=index * 10,
            )
            for index, package in enumerate(packages, start=1)
        )

    def _skill_detail_children(
        self,
        request: ContextChildrenRequest,
    ) -> tuple[ContextNodeSeed, ...]:
        skill_name = _optional_text(request.node.owner_ref.get("skill_name"))
        if skill_name is None:
            return ()
        workspace_dir = _workspace_dir(request)
        surface = _surface(request)
        try:
            result = self._skill_service.read(
                workspace_dir=workspace_dir,
                skill_name=skill_name,
                path=None,
                surface=surface,
            )
        except SkillError:
            return ()
        return (
            _skill_instructions_node_seed(
                result,
                parent_id=request.node.id,
            ),
        )

    def _packages_for_workspace(
        self,
        *,
        workspace_dir: str | None,
        surface: str,
        skill_names: tuple[str, ...],
    ) -> tuple[SkillPackage, ...]:
        if not skill_names:
            return self._skill_service.list_available(
                workspace_dir=workspace_dir,
                surface=surface,
                include_disabled=False,
            )
        packages: list[SkillPackage] = []
        for name in skill_names:
            try:
                packages.append(
                    self._skill_service.get(
                        workspace_dir=workspace_dir,
                        skill_name=name,
                        surface=surface,
                        include_disabled=False,
                    ),
                )
            except SkillError:
                continue
        return tuple(packages)


_SKILL_ACTIONS = (
    ContextAction.EXPAND,
    ContextAction.COLLAPSE,
    ContextAction.PIN,
    ContextAction.UNPIN,
    ContextAction.READ_SKILL,
    ContextAction.ESTIMATE,
)


def _skill_node_seed(
    package: SkillPackage,
    *,
    parent_id: str,
    workspace_dir: str | None,
    surface: str,
    display_order: int,
) -> ContextNodeSeed:
    summary_parts = [package.description]
    if package.manifest.when_to_use:
        summary_parts.append(f"Use when: {package.manifest.when_to_use}")
    if package.required_tools:
        summary_parts.append(f"Requires tools: {', '.join(package.required_tools)}")
    if package.suggested_tools:
        summary_parts.append(f"Suggested tools: {', '.join(package.suggested_tools)}")
    summary = " ".join(part.strip() for part in summary_parts if part.strip())
    return ContextNodeSeed(
        node_id=f"skills.skill.{_node_token(package.name)}",
        parent_id=parent_id,
        owner="skills",
        kind="skill",
        title=package.name,
        summary=_truncate(summary, 480),
        actions=_SKILL_ACTIONS,
        owner_ref={
            "skill_name": package.name,
            "workspace_dir": workspace_dir,
            "surface": surface,
            "root_path": package.root_path,
            "instructions_path": package.instructions_path,
        },
        estimate=_text_estimate(summary),
        display_order=display_order,
        metadata={
            "version": package.version,
            "tags": list(package.tags),
            "source": package.source,
            "resource_count": len(package.resources),
            "requirements": package.requirements.to_payload(),
        },
    )


def _skill_instructions_node_seed(
    result: SkillReadResult,
    *,
    parent_id: str,
) -> ContextNodeSeed:
    content = result.content.strip()
    summary = _truncate(content, 1600)
    return ContextNodeSeed(
        node_id=f"{parent_id}.instructions",
        parent_id=parent_id,
        owner="skills",
        kind="skill_instructions",
        title=result.requested_path or "SKILL.md",
        summary=summary,
        state=ContextNodeState(collapsed=False, loaded=True),
        actions=(ContextAction.PIN, ContextAction.UNPIN, ContextAction.ESTIMATE),
        owner_ref={
            "skill_name": result.package.name,
            "requested_path": result.requested_path,
            "resolved_path": result.resolved_path,
        },
        estimate=_text_estimate(summary),
        display_order=10,
        metadata={
            "content_chars": len(content),
            "truncated": len(content) > len(summary),
        },
    )


def _workspace_dir(request: ContextChildrenRequest) -> str | None:
    return _optional_text(request.workspace.metadata.get("workspace_dir"))


def _surface(request: ContextChildrenRequest) -> str:
    return _optional_text(request.workspace.metadata.get("prompt_surface")) or "interactive"


def _available_skill_names(metadata: dict[str, object]) -> tuple[str, ...]:
    raw_names = metadata.get("available_skill_names")
    if not isinstance(raw_names, Iterable) or isinstance(raw_names, (str, bytes)):
        return ()
    names: list[str] = []
    for item in raw_names:
        normalized = _optional_text(item)
        if normalized is not None and normalized not in names:
            names.append(normalized)
    return tuple(names)


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _node_token(value: str) -> str:
    return quote(value.strip(), safe="")


def _text_estimate(text: str) -> ContextEstimate:
    normalized = text or ""
    return ContextEstimate(
        text_chars=len(normalized),
        text_tokens=max((len(normalized) + 3) // 4, 1) if normalized else 0,
    )


def _truncate(value: str, limit: int) -> str:
    text = value.strip()
    if len(text) <= limit:
        return text
    return text[: max(limit - 1, 0)].rstrip() + "..."


__all__ = ["SkillContextNodeProvider"]
