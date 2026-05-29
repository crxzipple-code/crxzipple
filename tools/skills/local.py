from __future__ import annotations

from collections.abc import Awaitable, Mapping
from dataclasses import asdict, dataclass, is_dataclass
from enum import Enum
import inspect
import json
from typing import Any, Protocol

from crxzipple.modules.skills.application import (
    SkillDraftCreateRequest,
    SkillDraftIntent,
    SkillDraftSupportFile,
    SkillDraftUpdateRequest,
    SkillReadPort,
    SkillReadResult,
)
from crxzipple.modules.skills.domain import SkillInstallScope, SkillRequirements
from crxzipple.modules.tool.domain import ToolExecutionContext, ToolRunResult


SKILL_READ_TOOL_ID = "skill_read"
SKILL_DRAFT_CREATE_TOOL_ID = "skill_draft_create"
SKILL_DRAFT_UPDATE_TOOL_ID = "skill_draft_update"
SKILL_DRAFT_VALIDATE_TOOL_ID = "skill_draft_validate"
SKILL_DRAFT_DIFF_TOOL_ID = "skill_draft_diff"
SKILL_DRAFT_APPLY_TOOL_ID = "skill_draft_apply"
SKILL_DRAFT_REJECT_TOOL_ID = "skill_draft_reject"
_SURFACE_ATTR = "surface"
_AVAILABLE_SKILL_NAMES_ATTR = "available_skill_names"


class SkillToolWorkspaceResolver(Protocol):
    def resolve(self, execution_context: ToolExecutionContext | None) -> str | None:
        ...


class SkillAuthoringPort(Protocol):
    def create_draft(
        self,
        request: SkillDraftCreateRequest,
    ) -> Any | Awaitable[Any]:
        ...

    def update_draft(
        self,
        *,
        draft_id: str,
        request: SkillDraftUpdateRequest,
    ) -> Any | Awaitable[Any]:
        ...

    def validate_draft(self, draft_id: str) -> Any | Awaitable[Any]:
        ...

    def build_draft_diff(self, draft_id: str) -> Any | Awaitable[Any]:
        ...

    def apply_draft(
        self,
        *,
        draft_id: str,
        reason: str | None = None,
    ) -> Any | Awaitable[Any]:
        ...

    def reject_draft(
        self,
        *,
        draft_id: str,
        reason: str | None = None,
    ) -> Any | Awaitable[Any]:
        ...


@dataclass(frozen=True, slots=True)
class SkillsToolDeps:
    skill_manager: SkillReadPort
    skill_authoring_service: SkillAuthoringPort | None = None


@dataclass(frozen=True, slots=True)
class ExecutionContextWorkspaceResolver:
    attr_name: str = "workspace_dir"

    def resolve(self, execution_context: ToolExecutionContext | None) -> str | None:
        if execution_context is None:
            return None
        return execution_context.get_str(self.attr_name)


def _coerce_skills_deps(
    value: SkillsToolDeps | Any,
) -> SkillsToolDeps:
    if isinstance(value, SkillsToolDeps):
        return value
    raise TypeError("skill_read requires SkillsToolDeps.")


def skill_read(deps: SkillsToolDeps | Any):
    resolved = _coerce_skills_deps(deps)
    if resolved.skill_manager is None:
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
        result = resolved.skill_manager.read(
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


def skill_draft_create(deps: SkillsToolDeps | Any):
    resolved = _coerce_skills_deps(deps)
    authoring = _require_authoring_service(resolved)
    workspace_resolver = ExecutionContextWorkspaceResolver()

    async def handler(
        arguments: dict[str, Any],
        execution_context: ToolExecutionContext | None = None,
    ) -> ToolRunResult:
        skill_name = _required_str(arguments, "skill_name", SKILL_DRAFT_CREATE_TOOL_ID)
        manifest = _mapping_arg(arguments, "manifest", required=True)
        instructions_body = _required_str(
            arguments,
            "instructions_body",
            SKILL_DRAFT_CREATE_TOOL_ID,
        )
        workspace_dir = _argument_workspace_dir(
            arguments,
            workspace_resolver=workspace_resolver,
            execution_context=execution_context,
        )
        actor_context = _actor_context(execution_context, workspace_dir=workspace_dir)
        result = await _call_authoring(
            authoring,
            "create_draft",
            SkillDraftCreateRequest(
                intent=_draft_intent(_optional_str(arguments, "intent")),
                skill_name=skill_name,
                target_source_id=_optional_str(arguments, "target_source_id"),
                target_scope=_draft_scope(_optional_str(arguments, "target_scope")),
                workspace_dir=workspace_dir,
                manifest=dict(manifest),
                instructions_body=instructions_body,
                support_files=_support_files_arg(arguments, "support_files"),
                requirements=_requirements_arg(arguments, "requirements"),
                created_by_run_id=_context_text(actor_context, "run_id"),
                created_by_turn_id=_context_text(actor_context, "turn_id"),
                actor=_context_text(actor_context, "agent_id"),
                reason=_optional_str(arguments, "reason")
                or _optional_str(arguments, "summary"),
            ),
        )
        return _authoring_result(
            tool_id=SKILL_DRAFT_CREATE_TOOL_ID,
            action="created",
            result=result,
            workspace_dir=workspace_dir,
        )

    return handler


def skill_draft_update(deps: SkillsToolDeps | Any):
    resolved = _coerce_skills_deps(deps)
    authoring = _require_authoring_service(resolved)
    workspace_resolver = ExecutionContextWorkspaceResolver()

    async def handler(
        arguments: dict[str, Any],
        execution_context: ToolExecutionContext | None = None,
    ) -> ToolRunResult:
        draft_id = _required_str(arguments, "draft_id", SKILL_DRAFT_UPDATE_TOOL_ID)
        patch = _mapping_arg(arguments, "patch", required=True)
        workspace_dir = workspace_resolver.resolve(execution_context)
        actor_context = _actor_context(execution_context, workspace_dir=workspace_dir)
        result = await _call_authoring(
            authoring,
            "update_draft",
            draft_id=draft_id,
            request=_draft_update_request(
                dict(patch),
                reason=_optional_str(arguments, "reason"),
                actor=_context_text(actor_context, "agent_id"),
            ),
        )
        return _authoring_result(
            tool_id=SKILL_DRAFT_UPDATE_TOOL_ID,
            action="updated",
            result=result,
            draft_id=draft_id,
            workspace_dir=workspace_dir,
        )

    return handler


def skill_draft_validate(deps: SkillsToolDeps | Any):
    resolved = _coerce_skills_deps(deps)
    authoring = _require_authoring_service(resolved)
    workspace_resolver = ExecutionContextWorkspaceResolver()

    async def handler(
        arguments: dict[str, Any],
        execution_context: ToolExecutionContext | None = None,
    ) -> ToolRunResult:
        draft_id = _required_str(arguments, "draft_id", SKILL_DRAFT_VALIDATE_TOOL_ID)
        workspace_dir = workspace_resolver.resolve(execution_context)
        result = await _call_authoring(
            authoring,
            "validate_draft",
            draft_id,
        )
        return _authoring_result(
            tool_id=SKILL_DRAFT_VALIDATE_TOOL_ID,
            action="validated",
            result=result,
            draft_id=draft_id,
            workspace_dir=workspace_dir,
        )

    return handler


def skill_draft_diff(deps: SkillsToolDeps | Any):
    resolved = _coerce_skills_deps(deps)
    authoring = _require_authoring_service(resolved)
    workspace_resolver = ExecutionContextWorkspaceResolver()

    async def handler(
        arguments: dict[str, Any],
        execution_context: ToolExecutionContext | None = None,
    ) -> ToolRunResult:
        draft_id = _required_str(arguments, "draft_id", SKILL_DRAFT_DIFF_TOOL_ID)
        workspace_dir = workspace_resolver.resolve(execution_context)
        result = await _call_authoring(
            authoring,
            "build_draft_diff",
            draft_id,
        )
        return _authoring_result(
            tool_id=SKILL_DRAFT_DIFF_TOOL_ID,
            action="diffed",
            result=result,
            draft_id=draft_id,
            workspace_dir=workspace_dir,
        )

    return handler


def skill_draft_apply(deps: SkillsToolDeps | Any):
    resolved = _coerce_skills_deps(deps)
    authoring = _require_authoring_service(resolved)
    workspace_resolver = ExecutionContextWorkspaceResolver()

    async def handler(
        arguments: dict[str, Any],
        execution_context: ToolExecutionContext | None = None,
    ) -> ToolRunResult:
        draft_id = _required_str(arguments, "draft_id", SKILL_DRAFT_APPLY_TOOL_ID)
        reason = _required_str(arguments, "reason", SKILL_DRAFT_APPLY_TOOL_ID)
        workspace_dir = workspace_resolver.resolve(execution_context)
        result = await _call_authoring(
            authoring,
            "apply_draft",
            draft_id=draft_id,
            reason=reason,
        )
        return _authoring_result(
            tool_id=SKILL_DRAFT_APPLY_TOOL_ID,
            action="applied",
            result=result,
            draft_id=draft_id,
            workspace_dir=workspace_dir,
            approval_required=True,
            required_effect_id="skill_authoring.apply",
        )

    return handler


def skill_draft_reject(deps: SkillsToolDeps | Any):
    resolved = _coerce_skills_deps(deps)
    authoring = _require_authoring_service(resolved)
    workspace_resolver = ExecutionContextWorkspaceResolver()

    async def handler(
        arguments: dict[str, Any],
        execution_context: ToolExecutionContext | None = None,
    ) -> ToolRunResult:
        draft_id = _required_str(arguments, "draft_id", SKILL_DRAFT_REJECT_TOOL_ID)
        workspace_dir = workspace_resolver.resolve(execution_context)
        result = await _call_authoring(
            authoring,
            "reject_draft",
            draft_id=draft_id,
            reason=_optional_str(arguments, "reason"),
        )
        return _authoring_result(
            tool_id=SKILL_DRAFT_REJECT_TOOL_ID,
            action="rejected",
            result=result,
            draft_id=draft_id,
            workspace_dir=workspace_dir,
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


def _require_authoring_service(resolved: SkillsToolDeps) -> SkillAuthoringPort:
    if resolved.skill_authoring_service is None:
        raise RuntimeError(
            "Skill authoring tools require service dependency "
            "'skill_authoring_service' implementing SkillAuthoringPort.",
        )
    return resolved.skill_authoring_service


async def _call_authoring(
    authoring: SkillAuthoringPort,
    method_name: str,
    *args: Any,
    **kwargs: Any,
) -> Any:
    method = getattr(authoring, method_name, None)
    if not callable(method):
        raise RuntimeError(
            "Skill authoring service does not implement "
            f"SkillAuthoringPort.{method_name}.",
        )
    result = method(*args, **kwargs)
    if inspect.isawaitable(result):
        return await result
    return result


def _authoring_result(
    *,
    tool_id: str,
    action: str,
    result: Any,
    draft_id: str | None = None,
    workspace_dir: str | None = None,
    approval_required: bool = False,
    required_effect_id: str | None = None,
) -> ToolRunResult:
    payload = _jsonable(result)
    resolved_draft_id = draft_id or _payload_field(payload, "draft_id")
    metadata: dict[str, Any] = {
        "tool": tool_id,
        "draft_id": resolved_draft_id,
        "workspace_dir": workspace_dir,
    }
    if approval_required:
        metadata["approval_required"] = True
        metadata["required_effect_id"] = required_effect_id
    return ToolRunResult.text(
        _render_authoring_result(
            action=action,
            draft_id=resolved_draft_id,
            payload=payload,
            approval_required=approval_required,
            required_effect_id=required_effect_id,
        ),
        details=payload,
        metadata={key: value for key, value in metadata.items() if value is not None},
    )


def _render_authoring_result(
    *,
    action: str,
    draft_id: str | None,
    payload: Any,
    approval_required: bool,
    required_effect_id: str | None,
) -> str:
    lines = [f"Skill draft {action}."]
    if draft_id:
        lines.append(f"- Draft: {draft_id}")
    status = _payload_field(payload, "status")
    if status:
        lines.append(f"- Status: {status}")
    summary = _payload_field(payload, "summary") or _payload_field(payload, "message")
    if summary:
        lines.append(f"- Summary: {summary}")
    readiness = _payload_field(payload, "readiness_status")
    if readiness:
        lines.append(f"- Readiness: {readiness}")
    if approval_required:
        effect = required_effect_id or "skill_authoring.apply"
        lines.append(f"- Approval: required before apply ({effect})")
    next_step = _payload_field(payload, "next_step") or _payload_field(payload, "next_steps")
    if next_step:
        lines.append(f"- Next: {next_step}")
    if len(lines) == 1:
        lines.append(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return "\n".join(lines)


def _jsonable(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return _jsonable(asdict(value))
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    to_payload = getattr(value, "to_payload", None)
    if callable(to_payload):
        return _jsonable(to_payload())
    return str(value)


def _payload_field(payload: Any, key: str) -> str | None:
    if not isinstance(payload, Mapping):
        return None
    value = payload.get(key)
    if value is None:
        return None
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(_jsonable(value), ensure_ascii=False, sort_keys=True)
    normalized = str(value).strip()
    return normalized or None


def _required_str(arguments: Mapping[str, Any], key: str, tool_id: str) -> str:
    value = arguments.get(key)
    if value is None:
        raise ValueError(f"{tool_id} requires '{key}'.")
    normalized = str(value).strip()
    if not normalized:
        raise ValueError(f"{tool_id} requires non-empty '{key}'.")
    return normalized


def _optional_str(arguments: Mapping[str, Any], key: str) -> str | None:
    value = arguments.get(key)
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _mapping_arg(
    arguments: Mapping[str, Any],
    key: str,
    *,
    required: bool = False,
) -> Mapping[str, Any] | None:
    value = arguments.get(key)
    if value is None:
        if required:
            raise ValueError(f"Skill authoring tool requires mapping '{key}'.")
        return None
    if not isinstance(value, Mapping):
        raise ValueError(f"Skill authoring argument '{key}' must be an object.")
    return value


def _sequence_arg(arguments: Mapping[str, Any], key: str) -> tuple[Any, ...]:
    value = arguments.get(key)
    if value is None:
        return ()
    if isinstance(value, str) or not isinstance(value, (list, tuple)):
        raise ValueError(f"Skill authoring argument '{key}' must be an array.")
    return tuple(_jsonable(item) for item in value)


def _support_files_arg(
    arguments: Mapping[str, Any],
    key: str,
) -> tuple[SkillDraftSupportFile, ...]:
    files: list[SkillDraftSupportFile] = []
    for index, item in enumerate(_sequence_arg(arguments, key)):
        if not isinstance(item, Mapping):
            raise ValueError(
                f"Skill authoring support file #{index + 1} must be an object.",
            )
        files.append(
            SkillDraftSupportFile(
                path=str(item.get("path") or "").strip(),
                content=str(item.get("content") or ""),
            ),
        )
    return tuple(files)


def _requirements_arg(
    arguments: Mapping[str, Any],
    key: str,
) -> SkillRequirements:
    return _requirements_from_mapping(dict(_mapping_arg(arguments, key) or {}))


def _requirements_from_mapping(payload: Mapping[str, Any]) -> SkillRequirements:
    return SkillRequirements(
        required_tools=_string_tuple(payload.get("required_tools")),
        optional_tools=_string_tuple(payload.get("optional_tools")),
        suggested_tools=_string_tuple(payload.get("suggested_tools")),
        required_effects=_string_tuple(payload.get("required_effects")),
        surfaces=_string_tuple(payload.get("surfaces")),
        supported_platforms=_string_tuple(payload.get("supported_platforms")),
        required_access=_string_tuple(payload.get("required_access")),
        setup_hints=_string_tuple(payload.get("setup_hints")),
    )


def _draft_update_request(
    patch: Mapping[str, Any],
    *,
    reason: str | None,
    actor: str | None,
) -> SkillDraftUpdateRequest:
    return SkillDraftUpdateRequest(
        manifest=dict(patch["manifest"]) if isinstance(patch.get("manifest"), Mapping) else None,
        instructions_body=(
            str(patch["instructions_body"])
            if patch.get("instructions_body") is not None
            else None
        ),
        support_files=(
            _support_files_from_sequence(patch.get("support_files"))
            if patch.get("support_files") is not None
            else None
        ),
        requirements=(
            _requirements_from_mapping(dict(patch["requirements"]))
            if isinstance(patch.get("requirements"), Mapping)
            else None
        ),
        target_source_id=_text_or_none(patch.get("target_source_id")),
        target_scope=(
            _draft_scope(_text_or_none(patch.get("target_scope")))
            if patch.get("target_scope") is not None
            else None
        ),
        workspace_dir=_text_or_none(patch.get("workspace_dir")),
        actor=actor,
        reason=reason,
    )


def _support_files_from_sequence(value: Any) -> tuple[SkillDraftSupportFile, ...]:
    if isinstance(value, str) or not isinstance(value, (list, tuple)):
        raise ValueError("Skill authoring patch 'support_files' must be an array.")
    files: list[SkillDraftSupportFile] = []
    for index, item in enumerate(value):
        if not isinstance(item, Mapping):
            raise ValueError(
                f"Skill authoring support file #{index + 1} must be an object.",
            )
        files.append(
            SkillDraftSupportFile(
                path=str(item.get("path") or "").strip(),
                content=str(item.get("content") or ""),
            ),
        )
    return tuple(files)


def _draft_intent(value: str | None) -> SkillDraftIntent:
    try:
        return SkillDraftIntent(value or SkillDraftIntent.CREATE.value)
    except ValueError as exc:
        raise ValueError(f"Unsupported skill draft intent '{value}'.") from exc


def _draft_scope(value: str | None) -> SkillInstallScope:
    try:
        return SkillInstallScope(value or SkillInstallScope.WORKSPACE.value)
    except ValueError as exc:
        raise ValueError(f"Unsupported skill draft target_scope '{value}'.") from exc


def _string_tuple(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        normalized = value.strip()
        return (normalized,) if normalized else ()
    if not isinstance(value, (list, tuple, set)):
        return ()
    return tuple(str(item).strip() for item in value if str(item).strip())


def _text_or_none(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _context_text(context: Mapping[str, Any], key: str) -> str | None:
    return _text_or_none(context.get(key))


def _argument_workspace_dir(
    arguments: Mapping[str, Any],
    *,
    workspace_resolver: SkillToolWorkspaceResolver,
    execution_context: ToolExecutionContext | None,
) -> str | None:
    return _optional_str(arguments, "workspace_dir") or workspace_resolver.resolve(
        execution_context,
    )


def _surface(execution_context: ToolExecutionContext | None) -> str:
    return (
        execution_context.get_str(_SURFACE_ATTR)
        if execution_context is not None
        else None
    ) or "interactive"


def _actor_context(
    execution_context: ToolExecutionContext | None,
    *,
    workspace_dir: str | None,
) -> dict[str, Any]:
    attrs = dict(execution_context.attrs) if execution_context is not None else {}
    return {
        "workspace_dir": workspace_dir,
        "surface": _surface(execution_context),
        "run_id": attrs.get("run_id"),
        "turn_id": attrs.get("turn_id"),
        "agent_id": attrs.get("agent_id"),
        "session_key": attrs.get("session_key"),
    }


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
    if requirements.required_access:
        lines.append(f"- Required access: {', '.join(requirements.required_access)}")
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
