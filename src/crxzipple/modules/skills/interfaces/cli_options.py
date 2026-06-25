from __future__ import annotations

import json
from pathlib import Path

import typer

from crxzipple.modules.skills.application.models import SkillDraftSupportFile
from crxzipple.modules.skills.domain import SkillRequirements


def _csv_tuple(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()
    return tuple(item.strip() for item in value.split(",") if item.strip())


def _optional_csv_tuple(value: str | None) -> tuple[str, ...] | None:
    if value is None:
        return None
    return _csv_tuple(value)


def _load_json(value: str | None, option_name: str) -> object:
    if value is None:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError as exc:
        raise typer.BadParameter(
            f"{option_name} must be valid JSON: {exc.msg}",
        ) from exc


def _load_json_object(value: str | None, option_name: str) -> dict[str, object]:
    payload = _load_json(value, option_name)
    if payload is None:
        return {}
    if not isinstance(payload, dict):
        raise typer.BadParameter(f"{option_name} must be a JSON object.")
    return dict(payload)


def _load_json_array(value: str | None, option_name: str) -> list[object]:
    payload = _load_json(value, option_name)
    if payload is None:
        return []
    if not isinstance(payload, list):
        raise typer.BadParameter(f"{option_name} must be a JSON array.")
    return list(payload)


def _read_text_option(
    *,
    inline: str | None,
    path: str | None,
    option_name: str,
) -> str | None:
    if inline is not None and path is not None:
        raise typer.BadParameter(
            f"Use either {option_name} or {option_name}-file, not both.",
        )
    if path is None:
        return inline
    return Path(path).read_text(encoding="utf-8")


def _manifest_from_options(
    *,
    skill_name: str,
    manifest_json: str | None,
    description: str | None,
    version: str | None,
    tags: str | None,
) -> dict[str, object]:
    manifest = _load_json_object(manifest_json, "--manifest-json")
    manifest.setdefault("name", skill_name)
    if description is not None:
        manifest["description"] = description
    manifest.setdefault("description", "")
    if version is not None:
        manifest["version"] = version
    if tags is not None:
        manifest["tags"] = list(_csv_tuple(tags))
    return manifest


def _requirements_from_options(
    *,
    requirements_json: str | None,
    required_tools: str | None,
    optional_tools: str | None,
    suggested_tools: str | None,
    required_effects: str | None,
    required_access: str | None,
    surfaces: str | None,
    supported_platforms: str | None,
    setup_hints: str | None,
) -> SkillRequirements:
    payload = _load_json_object(requirements_json, "--requirements-json")

    def items(key: str) -> tuple[str, ...]:
        if key not in payload:
            return ()
        raw = payload[key]
        if raw is None:
            return ()
        if not isinstance(raw, list):
            raise typer.BadParameter(
                f"--requirements-json field '{key}' must be a JSON array.",
            )
        return tuple(str(item).strip() for item in raw if str(item).strip())

    values = {
        "required_tools": items("required_tools"),
        "optional_tools": items("optional_tools"),
        "suggested_tools": items("suggested_tools"),
        "required_effects": items("required_effects"),
        "required_access": items("required_access"),
        "surfaces": items("surfaces"),
        "supported_platforms": items("supported_platforms"),
        "setup_hints": items("setup_hints"),
    }
    overrides = {
        "required_tools": required_tools,
        "optional_tools": optional_tools,
        "suggested_tools": suggested_tools,
        "required_effects": required_effects,
        "required_access": required_access,
        "surfaces": surfaces,
        "supported_platforms": supported_platforms,
        "setup_hints": setup_hints,
    }
    for key, raw in overrides.items():
        if raw is not None:
            values[key] = _csv_tuple(raw)
    return SkillRequirements(**values)


def _requirements_option_was_provided(
    *,
    requirements_json: str | None,
    required_tools: str | None,
    optional_tools: str | None,
    suggested_tools: str | None,
    required_effects: str | None,
    required_access: str | None,
    surfaces: str | None,
    supported_platforms: str | None,
    setup_hints: str | None,
) -> bool:
    return any(
        value is not None
        for value in (
            requirements_json,
            required_tools,
            optional_tools,
            suggested_tools,
            required_effects,
            required_access,
            surfaces,
            supported_platforms,
            setup_hints,
        )
    )


def _support_files_from_options(
    *,
    support_files_json: str | None,
    support_file: list[str] | None,
) -> tuple[SkillDraftSupportFile, ...]:
    files: list[SkillDraftSupportFile] = []
    for item in _load_json_array(support_files_json, "--support-files-json"):
        if not isinstance(item, dict):
            raise typer.BadParameter(
                "--support-files-json items must be JSON objects.",
            )
        path = str(item.get("path") or "").strip()
        if not path:
            raise typer.BadParameter(
                "--support-files-json items require a non-empty path.",
            )
        files.append(
            SkillDraftSupportFile(
                path=path,
                content=str(item.get("content") or ""),
            ),
        )
    for raw in support_file or ():
        if "=" not in raw:
            raise typer.BadParameter("--support-file must use path=content.")
        path, content = raw.split("=", 1)
        normalized_path = path.strip()
        if not normalized_path:
            raise typer.BadParameter("--support-file requires a non-empty path.")
        files.append(SkillDraftSupportFile(path=normalized_path, content=content))
    return tuple(files)
