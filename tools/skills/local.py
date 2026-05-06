from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from crxzipple.modules.skills.application import SkillReadResult
from crxzipple.modules.tool.domain import ToolExecutionContext, ToolRunResult


SKILL_READ_TOOL_ID = "skill_read"
_SURFACE_ATTR = "surface"
_AVAILABLE_SKILL_NAMES_ATTR = "available_skill_names"


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
        available_skill_names = _available_skill_names(execution_context)
        if (
            available_skill_names is not None
            and skill_name not in available_skill_names
        ):
            raise ValueError(
                f"Skill '{skill_name}' is not available in this orchestration run.",
            )
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
                "requirements": result.package.requirements.to_payload(),
                "resources": [
                    {
                        "path": resource.path,
                        "kind": resource.kind,
                        "size_bytes": resource.size_bytes,
                    }
                    for resource in result.package.resources
                ],
            },
        )

    return handler


def _available_skill_names(
    execution_context: ToolExecutionContext | None,
) -> set[str] | None:
    if execution_context is None:
        return None
    if _AVAILABLE_SKILL_NAMES_ATTR not in execution_context.attrs:
        return None
    raw_names = execution_context.attrs.get(_AVAILABLE_SKILL_NAMES_ATTR)
    if isinstance(raw_names, str):
        return {name.strip() for name in raw_names.split(",") if name.strip()}
    if isinstance(raw_names, (list, tuple, set)):
        return {
            str(name).strip()
            for name in raw_names
            if str(name).strip()
        }
    return set()


def render_skill_read_result(result: SkillReadResult) -> str:
    package = result.package
    requirements = package.requirements
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
    if package.manifest.when_to_use:
        lines.append(f"- Use when: {package.manifest.when_to_use}")
    if requirements.required_tools:
        lines.append(f"- Required tools: {', '.join(requirements.required_tools)}")
    if requirements.optional_tools:
        lines.append(f"- Optional tools: {', '.join(requirements.optional_tools)}")
    if requirements.suggested_tools:
        lines.append(f"- Suggested tools: {', '.join(requirements.suggested_tools)}")
    if requirements.required_effects:
        lines.append(f"- Required effects: {', '.join(requirements.required_effects)}")
    if requirements.surfaces:
        lines.append(f"- Surfaces: {', '.join(requirements.surfaces)}")
    if requirements.compatibility_auth:
        lines.append(
            f"- Compatibility auth: {', '.join(requirements.compatibility_auth)}",
        )
    if requirements.compatibility_secrets:
        lines.append(
            f"- Compatibility secrets: {', '.join(requirements.compatibility_secrets)}",
        )
    if requirements.compatibility_credential_files:
        lines.append(
            "- Compatibility credential files: "
            + ", ".join(requirements.compatibility_credential_files),
        )
    if package.resources:
        lines.append("- Resources:")
        lines.extend(
            f"  - {resource.path} ({resource.kind}, {resource.size_bytes} bytes)"
            for resource in package.resources
        )
    lines.extend(
        [
            "",
            result.content,
        ],
    )
    return "\n".join(lines).strip()
