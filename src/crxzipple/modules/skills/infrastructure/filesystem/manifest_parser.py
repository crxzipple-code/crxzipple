from __future__ import annotations

from typing import Any

import yaml

from crxzipple.modules.skills.domain import SkillManifest, SkillValidationError


DEFAULT_SKILL_INSTRUCTIONS_FILENAME = "SKILL.md"
MAX_SKILL_DESCRIPTION_CHARS = 240


def parse_markdown_frontmatter(content: str) -> dict[str, Any] | None:
    lines = content.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    closing_index = next(
        (index for index, line in enumerate(lines[1:], start=1) if line.strip() == "---"),
        None,
    )
    if closing_index is None:
        return None
    payload = yaml.safe_load("\n".join(lines[1:closing_index])) or {}
    return payload if isinstance(payload, dict) else None


def strip_markdown_frontmatter(content: str) -> str:
    lines = content.splitlines()
    if not lines or lines[0].strip() != "---":
        return content
    closing_index = next(
        (index for index, line in enumerate(lines[1:], start=1) if line.strip() == "---"),
        None,
    )
    if closing_index is None:
        return content
    return "\n".join(lines[closing_index + 1 :])


def parse_normalized_manifest(
    *,
    frontmatter_payload: dict[str, Any] | None,
    legacy_payload: dict[str, Any] | None,
) -> SkillManifest:
    if frontmatter_payload is None:
        legacy = parse_legacy_manifest(legacy_payload) if legacy_payload is not None else None
        if legacy is None:
            raise SkillValidationError("Skill package must define SKILL.md frontmatter.")
        return legacy
    name = optional_string(frontmatter_payload.get("name"))
    if name is None:
        raise SkillValidationError("Skill frontmatter field 'name' is required.")
    description = optional_string(frontmatter_payload.get("description"))
    if description is None:
        raise SkillValidationError("Skill frontmatter field 'description' is required.")
    reject_legacy_access_fields(frontmatter_payload)
    setup = frontmatter_payload.get("setup")
    setup = setup if isinstance(setup, dict) else {}
    suggested_tools = (
        normalize_tool_function_ids(frontmatter_payload.get("suggested_tools"))
        or normalize_tool_function_ids(frontmatter_payload.get("preferred_tools"))
        or normalize_tool_function_ids(frontmatter_payload.get("allowed_tools"))
    )
    return SkillManifest(
        api_version=optional_string(frontmatter_payload.get("apiVersion"))
        or "skills.crxzipple/v1alpha1",
        kind=optional_string(frontmatter_payload.get("kind")) or "Skill",
        name=name,
        description=normalize_description(description),
        version=optional_string(frontmatter_payload.get("version")),
        tags=normalize_string_sequence(frontmatter_payload.get("tags")),
        when_to_use=optional_string(frontmatter_payload.get("when_to_use"))
        or optional_string(frontmatter_payload.get("whenToUse")),
        anti_patterns=normalize_string_sequence(frontmatter_payload.get("anti_patterns")),
        instructions_path=optional_string(frontmatter_payload.get("instructions_path"))
        or optional_string(frontmatter_payload.get("instructions"))
        or DEFAULT_SKILL_INSTRUCTIONS_FILENAME,
        required_tools=normalize_tool_function_ids(frontmatter_payload.get("required_tools")),
        optional_tools=normalize_tool_function_ids(frontmatter_payload.get("optional_tools")),
        suggested_tools=suggested_tools,
        allowed_tools=suggested_tools,
        required_effects=normalize_string_sequence(frontmatter_payload.get("required_effects")),
        required_access=normalize_access_requirement_sequence(
            frontmatter_payload.get("required_access"),
        ),
        surfaces=normalize_string_sequence(frontmatter_payload.get("surfaces")),
        supported_platforms=normalize_string_sequence(
            frontmatter_payload.get("supported_platforms"),
        )
        or normalize_string_sequence(frontmatter_payload.get("platforms")),
        setup_hints=normalize_string_sequence(frontmatter_payload.get("setup_hints"))
        or normalize_string_sequence(setup.get("help")),
    )


def parse_legacy_manifest(payload: dict[str, Any]) -> SkillManifest:
    api_version = required_string(payload.get("apiVersion"), "apiVersion")
    kind = required_string(payload.get("kind"), "kind")
    metadata = payload.get("metadata")
    spec = payload.get("spec")
    if not isinstance(metadata, dict):
        raise SkillValidationError("Skill manifest metadata must be a mapping.")
    if not isinstance(spec, dict):
        raise SkillValidationError("Skill manifest spec must be a mapping.")
    name = required_string(metadata.get("name"), "metadata.name")
    description = normalize_description(
        required_string(metadata.get("description"), "metadata.description"),
    )
    version = optional_string(metadata.get("version"))
    tags = normalize_string_sequence(metadata.get("tags"))
    instructions_path = required_string(spec.get("instructions"), "spec.instructions")
    dependencies = spec.get("dependencies")
    runtime = spec.get("runtime")
    dependencies = dependencies if isinstance(dependencies, dict) else {}
    runtime = runtime if isinstance(runtime, dict) else {}
    tools = dependencies.get("tools")
    tools = tools if isinstance(tools, dict) else {}
    allowed_tools = normalize_string_sequence(runtime.get("allowed_tools"))
    return SkillManifest(
        api_version=api_version,
        kind=kind,
        name=name,
        description=description,
        version=version,
        tags=tags,
        instructions_path=instructions_path,
        required_tools=normalize_tool_function_ids(tools.get("required")),
        optional_tools=normalize_tool_function_ids(tools.get("optional")),
        suggested_tools=normalize_tool_function_ids(allowed_tools),
        allowed_tools=normalize_tool_function_ids(allowed_tools),
        supported_platforms=normalize_string_sequence(
            runtime.get("supported_platforms"),
        )
        or normalize_string_sequence(runtime.get("platforms")),
    )


def render_skill_markdown(*, manifest: SkillManifest, body: str) -> str:
    payload = manifest_frontmatter_payload(manifest)
    frontmatter = yaml.safe_dump(
        payload,
        sort_keys=False,
        allow_unicode=True,
    ).strip()
    normalized_body = body.strip()
    return f"---\n{frontmatter}\n---\n\n{normalized_body}\n"


def manifest_frontmatter_payload(manifest: SkillManifest) -> dict[str, object]:
    payload: dict[str, object] = {
        "apiVersion": manifest.api_version,
        "kind": manifest.kind,
        "name": manifest.name,
        "description": manifest.description,
        "instructions_path": manifest.instructions_path,
    }
    optional_values: tuple[tuple[str, object | None], ...] = (
        ("version", manifest.version),
        ("tags", list(manifest.tags) or None),
        ("when_to_use", manifest.when_to_use),
        ("anti_patterns", list(manifest.anti_patterns) or None),
        ("required_tools", list(manifest.required_tools) or None),
        ("optional_tools", list(manifest.optional_tools) or None),
        ("suggested_tools", list(manifest.suggested_tools) or None),
        ("required_effects", list(manifest.required_effects) or None),
        ("required_access", list(manifest.required_access) or None),
        ("surfaces", list(manifest.surfaces) or None),
        ("supported_platforms", list(manifest.supported_platforms) or None),
        ("setup_hints", list(manifest.setup_hints) or None),
    )
    for key, value in optional_values:
        if value is not None:
            payload[key] = value
    return payload


def required_string(value: Any, field_name: str) -> str:
    if not isinstance(value, str):
        raise SkillValidationError(f"Skill manifest field '{field_name}' must be a string.")
    normalized = value.strip()
    if not normalized:
        raise SkillValidationError(f"Skill manifest field '{field_name}' is required.")
    return normalized


def optional_string(value: Any) -> str | None:
    if value is None or isinstance(value, bool):
        return None
    normalized = str(value).strip()
    return normalized or None


def normalize_string_sequence(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        normalized = value.strip()
        return (normalized,) if normalized else ()
    if not isinstance(value, list | tuple):
        return ()
    items: list[str] = []
    for raw_item in value:
        if not isinstance(raw_item, str):
            continue
        normalized = raw_item.strip()
        if not normalized or normalized in items:
            continue
        items.append(normalized)
    return tuple(items)


def normalize_tool_function_ids(value: Any) -> tuple[str, ...]:
    items = normalize_string_sequence(value)
    for item in items:
        if item.startswith(("env:", "file:")) or item in {
            "codex_auth_json",
            "auth_ref",
        }:
            raise SkillValidationError(
                "Skill required_tools must reference ToolFunction ids, not credential sources.",
            )
        if "/" in item or "\\" in item or any(character.isspace() for character in item):
            raise SkillValidationError(
                f"Skill tool requirement '{item}' is not a valid ToolFunction id.",
            )
    return items


def normalize_access_requirement_sequence(value: Any) -> tuple[str, ...]:
    items = normalize_requirement_sequence(value)
    for item in items:
        if item.startswith(("env:", "file:", "codex_auth_json", "auth_ref")):
            raise SkillValidationError(
                "Skill required_access must reference Access bindings or requirements, not direct credential sources.",
            )
        if item.startswith(("~", "/")) or "\\" in item:
            raise SkillValidationError(
                f"Skill access requirement '{item}' must not reference a local path.",
            )
    return items


def reject_legacy_access_fields(payload: dict[str, Any]) -> None:
    legacy_fields = (
        "required_auth",
        "required_secrets",
        "required_environment_variables",
        "required_credential_files",
    )
    present = [field for field in legacy_fields if field in payload]
    if present:
        joined = ", ".join(present)
        raise SkillValidationError(
            f"Skill frontmatter uses retired access fields: {joined}. Use required_access instead.",
        )


def normalize_requirement_sequence(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        normalized = value.strip()
        return (normalized,) if normalized else ()
    if isinstance(value, dict):
        item = normalize_requirement_mapping(value)
        return (item,) if item else ()
    if not isinstance(value, list):
        return ()
    items: list[str] = []
    for raw_item in value:
        normalized = ""
        if isinstance(raw_item, str):
            normalized = raw_item.strip()
        elif isinstance(raw_item, dict):
            normalized = normalize_requirement_mapping(raw_item)
        if not normalized or normalized in items:
            continue
        items.append(normalized)
    return tuple(items)


def normalize_requirement_mapping(value: dict[str, Any]) -> str:
    provider = str(value.get("provider") or "").strip()
    kind = str(value.get("kind") or "").strip()
    name = str(value.get("name") or "").strip()
    if provider:
        label = f"{provider}:{kind}" if kind else provider
    else:
        label = name or kind
    scopes = normalize_string_sequence(value.get("scopes"))
    if label and scopes:
        return f"{label}({','.join(scopes)})"
    return label


def normalize_description(content: str) -> str:
    normalized = " ".join(content.strip().split())
    if len(normalized) <= MAX_SKILL_DESCRIPTION_CHARS:
        return normalized
    return f"{normalized[: MAX_SKILL_DESCRIPTION_CHARS - 1].rstrip()}..."
