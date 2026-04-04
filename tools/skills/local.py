from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from crxzipple.modules.skills.application import SkillReadResult
from crxzipple.modules.tool.domain import ToolExecutionContext, ToolRunResult


SKILL_READ_TOOL_ID = "skill_read"
_SURFACE_ATTR = "surface"


class SkillToolWorkspaceResolver(Protocol):
    def resolve(self, execution_context: ToolExecutionContext | None) -> str | None:
        ...


@dataclass(frozen=True, slots=True)
class ExecutionContextWorkspaceResolver:
    attr_name: str = "workspace_dir"

    def resolve(self, execution_context: ToolExecutionContext | None) -> str | None:
        if execution_context is None:
            return None
        return execution_context.get_str(self.attr_name)


def skill_read(container: Any):
    local_tool_catalog = getattr(container, "local_tool_catalog", None)
    skill_manager = getattr(container, "skill_manager", None)
    if local_tool_catalog is None or skill_manager is None:
        return None
    workspace_resolver = ExecutionContextWorkspaceResolver()

    async def handler(
        arguments: dict[str, Any],
        execution_context: ToolExecutionContext | None = None,
    ) -> ToolRunResult:
        skill_name = str(arguments.get("skill", "")).strip()
        if not skill_name:
            raise ValueError("skill_read requires a skill name.")
        raw_path = arguments.get("path")
        path = raw_path.strip() if isinstance(raw_path, str) else None
        workspace_dir = workspace_resolver.resolve(execution_context)
        surface = (
            execution_context.get_str(_SURFACE_ATTR)
            if execution_context is not None
            else None
        ) or "interactive"
        result = skill_manager.read(
            workspace_dir=workspace_dir,
            skill_name=skill_name,
            path=path,
            surface=surface,
        )
        return ToolRunResult.text(
            render_skill_read_result(result),
            metadata={
                "tool": SKILL_READ_TOOL_ID,
                "skill_name": result.package.name,
                "workspace_dir": workspace_dir,
                "requested_path": result.requested_path,
                "resolved_path": result.resolved_path,
            },
        )

    return handler


def render_skill_read_result(result: SkillReadResult) -> str:
    package = result.package
    lines = [
        f"# Skill: {package.name}",
        "",
        f"- Source: {package.source}",
        f"- Package: {package.root_path}",
        f"- Manifest: {package.manifest_path}",
        f"- Requested path: {result.requested_path}",
        f"- Resolved path: {result.resolved_path}",
    ]
    if package.version is not None:
        lines.append(f"- Version: {package.version}")
    if package.tags:
        lines.append(f"- Tags: {', '.join(package.tags)}")
    if package.allowed_tools:
        lines.append(f"- Suggested tools: {', '.join(package.allowed_tools)}")
    lines.extend(
        [
            "",
            result.content,
        ],
    )
    return "\n".join(lines).strip()
