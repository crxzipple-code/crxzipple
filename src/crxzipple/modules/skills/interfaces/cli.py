from __future__ import annotations

import json
from pathlib import Path

import typer

from crxzipple.interfaces.cli.context import AppKey, ensure_container
from crxzipple.interfaces.cli.formatters import echo_data
from crxzipple.modules.skills.application.models import (
    InstalledSkill,
    SkillCreateRequest,
    SkillDraft,
    SkillDraftAuditRecord,
    SkillDraftCreateRequest,
    SkillDraftDiff,
    SkillDraftFileDiff,
    SkillDraftIntent,
    SkillDraftStatus,
    SkillDraftSupportFile,
    SkillDraftUpdateRequest,
    SkillDraftValidation,
    SkillMutationResult,
    SkillPackage,
    SkillReadResult,
    SkillReadiness,
    SkillSource,
    SkillSourceCreateRequest,
    SkillSourceKind,
    SkillSourceMutationResult,
    SkillSourceUpdateRequest,
    SkillSyncResult,
    SkillUpdateRequest,
)
from crxzipple.modules.skills.domain import (
    SkillError,
    SkillInstallScope,
    SkillRequirements,
)


def _exit_error(message: str) -> None:
    typer.secho(message, err=True, fg=typer.colors.RED)
    raise typer.Exit(code=1) from None


def _skill_payload(
    package: SkillPackage,
    *,
    instructions: str | None = None,
) -> dict[str, object]:
    requirements = package.requirements
    payload: dict[str, object] = {
        "name": package.name,
        "description": package.description,
        "version": package.version,
        "tags": list(package.tags),
        "source": package.source,
        "root_path": package.root_path,
        "manifest_path": package.manifest_path,
        "instructions_path": package.instructions_path,
        "resources": [
            {
                "path": resource.path,
                "kind": resource.kind,
                "size_bytes": resource.size_bytes,
            }
            for resource in package.resources
        ],
        "requirements": requirements.to_payload(),
        "manifest": {
            "api_version": package.manifest.api_version,
            "kind": package.manifest.kind,
            "name": package.manifest.name,
            "description": package.manifest.description,
            "version": package.manifest.version,
            "tags": list(package.manifest.tags),
            "when_to_use": package.manifest.when_to_use,
            "anti_patterns": list(package.manifest.anti_patterns),
            "instructions_path": package.manifest.instructions_path,
            "required_tools": list(package.manifest.required_tools),
            "optional_tools": list(package.manifest.optional_tools),
            "suggested_tools": list(package.manifest.suggested_tools),
            "required_effects": list(package.manifest.required_effects),
            "required_access": list(package.manifest.required_access),
            "surfaces": list(package.manifest.surfaces),
            "supported_platforms": list(package.manifest.supported_platforms),
            "setup_hints": list(package.manifest.setup_hints),
        },
    }
    if instructions is not None:
        payload["instructions"] = instructions
    return payload


def _read_payload(result: SkillReadResult) -> dict[str, object]:
    return {
        "skill": _skill_payload(result.package),
        "requested_path": result.requested_path,
        "resolved_path": result.resolved_path,
        "content": result.content,
    }


def _install_payload(result: InstalledSkill) -> dict[str, object]:
    payload = _skill_payload(result.package)
    payload.update(
        {
            "scope": result.scope.value,
            "target_root": result.target_root,
            "target_path": result.target_path,
        },
    )
    return payload


def _source_payload(source: SkillSource) -> dict[str, object]:
    return {
        "source_id": source.source_id,
        "source_kind": source.source_kind.value,
        "root_path": source.root_path,
        "enabled": source.enabled,
        "readonly": source.readonly,
        "package_count": source.package_count,
        "metadata": source.metadata,
        "status": source.status,
        "sync_status": source.sync_status,
        "priority": source.priority,
    }


def _readiness_payload(readiness: SkillReadiness) -> dict[str, object]:
    return {
        "status": readiness.status.value,
        "ready": readiness.ready,
        "missing_tools": list(readiness.missing_tools),
        "missing_access": list(readiness.missing_access),
        "missing_effects": list(readiness.missing_effects),
        "unsupported_surfaces": list(readiness.unsupported_surfaces),
        "unsupported_platforms": list(readiness.unsupported_platforms),
        "validation_errors": list(readiness.validation_errors),
        "setup_hints": list(readiness.setup_hints),
    }


def _sync_payload(result: SkillSyncResult) -> dict[str, object]:
    return {
        "source_id": result.source_id,
        "synced_count": result.synced_count,
        "skills": [_skill_payload(package) for package in result.packages],
    }


def _mutation_payload(result: SkillMutationResult) -> dict[str, object]:
    return {
        "action": result.action,
        "changed": result.changed,
        "message": result.message,
        "skill": _skill_payload(result.skill),
    }


def _source_mutation_payload(
    result: SkillSourceMutationResult,
) -> dict[str, object]:
    return {
        "action": result.action,
        "changed": result.changed,
        "message": result.message,
        "source": _source_payload(result.source),
    }


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


def _validation_payload(validation: SkillDraftValidation | None) -> dict[str, object] | None:
    if validation is None:
        return None
    return {
        "valid": validation.valid,
        "errors": list(validation.errors),
        "warnings": list(validation.warnings),
        "missing_tools": list(validation.missing_tools),
        "missing_access": list(validation.missing_access),
        "missing_effects": list(validation.missing_effects),
        "unsupported_surfaces": list(validation.unsupported_surfaces),
        "unsupported_platforms": list(validation.unsupported_platforms),
        "readiness_status": validation.readiness_status,
    }


def _file_diff_payload(diff: SkillDraftFileDiff) -> dict[str, object]:
    return {
        "path": diff.path,
        "status": diff.status,
        "unified_diff": diff.unified_diff,
    }


def _diff_payload(diff: SkillDraftDiff | None) -> dict[str, object] | None:
    if diff is None:
        return None
    return {
        "manifest_diff": dict(diff.manifest_diff),
        "instructions_diff": diff.instructions_diff,
        "file_diffs": [_file_diff_payload(item) for item in diff.file_diffs],
        "summary": list(diff.summary),
    }


def _draft_payload(draft: SkillDraft) -> dict[str, object]:
    return {
        "draft_id": draft.draft_id,
        "status": draft.status.value,
        "intent": draft.intent.value,
        "skill_name": draft.skill_name,
        "target_source_id": draft.target_source_id,
        "target_scope": draft.target_scope.value,
        "workspace_dir": draft.workspace_dir,
        "base_fingerprint": draft.base_fingerprint,
        "manifest": dict(draft.manifest or {}),
        "instructions_body": draft.instructions_body,
        "support_files": [
            {"path": item.path, "content": item.content}
            for item in draft.support_files
        ],
        "requirements": draft.requirements.to_payload(),
        "validation": _validation_payload(draft.validation),
        "diff": _diff_payload(draft.diff),
        "created_by_run_id": draft.created_by_run_id,
        "created_by_turn_id": draft.created_by_turn_id,
        "actor": draft.actor,
        "reason": draft.reason,
        "created_at": draft.created_at,
        "updated_at": draft.updated_at,
        "expires_at": draft.expires_at,
    }


def _draft_audit_payload(record: SkillDraftAuditRecord) -> dict[str, object]:
    return {
        "audit_id": record.audit_id,
        "draft_id": record.draft_id,
        "action": record.action,
        "status": record.status,
        "actor": record.actor,
        "reason": record.reason,
        "before_payload": dict(record.before_payload or {}),
        "after_payload": dict(record.after_payload or {}),
        "metadata": dict(record.metadata or {}),
        "created_at": record.created_at,
    }


def build_cli() -> typer.Typer:
    app = typer.Typer(help="Manage filesystem-backed skills.", no_args_is_help=True)

    @app.command("list")
    def list_skills(
        ctx: typer.Context,
        workspace_dir: str | None = typer.Option(
            None,
            help="Optional session workspace used for workspace skill discovery.",
        ),
        surface: str = typer.Option(
            "interactive",
            help="Optional run surface for future filtering.",
        ),
        source: str | None = typer.Option(None, help="Optional source id filter."),
    ) -> None:
        container = ensure_container(ctx)
        skills = container.require(AppKey.SKILL_MANAGER).list_available(
            workspace_dir=workspace_dir,
            surface=surface,
        )
        if source:
            normalized_source = source.strip()
            skills = tuple(skill for skill in skills if skill.source == normalized_source)
        echo_data([_skill_payload(skill) for skill in skills])

    source_app = typer.Typer(help="Manage skill sources.", no_args_is_help=True)

    @source_app.command("list")
    def list_sources(
        ctx: typer.Context,
        workspace_dir: str | None = typer.Option(
            None,
            help="Optional session workspace used for workspace skill discovery.",
        ),
        surface: str = typer.Option(
            "interactive",
            help="Optional run surface for filtering.",
        ),
    ) -> None:
        container = ensure_container(ctx)
        try:
            sources = container.require(AppKey.SKILL_MANAGER).list_sources(
                workspace_dir=workspace_dir,
                surface=surface,
            )
        except SkillError as exc:
            _exit_error(str(exc))
        echo_data([_source_payload(source) for source in sources])

    @source_app.command("create")
    def create_source(
        ctx: typer.Context,
        source_id: str = typer.Argument(..., help="Source id."),
        root_path: str = typer.Argument(..., help="Directory containing skill packages."),
        source_kind: SkillSourceKind = typer.Option(
            SkillSourceKind.EXTERNAL,
            "--source-kind",
            case_sensitive=False,
            help="Custom source kind.",
        ),
        enabled: bool = typer.Option(True, help="Enable this source immediately."),
        readonly: bool = typer.Option(False, help="Mark source packages read-only."),
        priority: int = typer.Option(100, help="Source priority."),
    ) -> None:
        container = ensure_container(ctx)
        try:
            result = container.require(AppKey.SKILL_MANAGER).create_source(
                SkillSourceCreateRequest(
                    source_id=source_id,
                    root_path=root_path,
                    source_kind=source_kind,
                    enabled=enabled,
                    readonly=readonly,
                    priority=priority,
                ),
            )
        except SkillError as exc:
            _exit_error(str(exc))
        echo_data(_source_mutation_payload(result))

    @source_app.command("update")
    def update_source(
        ctx: typer.Context,
        source_id: str = typer.Argument(..., help="Source id."),
        root_path: str | None = typer.Option(None, help="Updated source root."),
        enabled: bool | None = typer.Option(None, help="Updated enabled state."),
        readonly: bool | None = typer.Option(None, help="Updated read-only state."),
        priority: int | None = typer.Option(None, help="Updated source priority."),
    ) -> None:
        container = ensure_container(ctx)
        try:
            result = container.require(AppKey.SKILL_MANAGER).update_source(
                SkillSourceUpdateRequest(
                    source_id=source_id,
                    root_path=root_path,
                    enabled=enabled,
                    readonly=readonly,
                    priority=priority,
                ),
            )
        except SkillError as exc:
            _exit_error(str(exc))
        echo_data(_source_mutation_payload(result))

    @source_app.command("delete")
    def delete_source(
        ctx: typer.Context,
        source_id: str = typer.Argument(..., help="Source id."),
    ) -> None:
        container = ensure_container(ctx)
        try:
            result = container.require(AppKey.SKILL_MANAGER).delete_source(
                source_id=source_id,
            )
        except SkillError as exc:
            _exit_error(str(exc))
        echo_data(_source_mutation_payload(result))

    app.add_typer(source_app, name="source")

    draft_app = typer.Typer(help="Manage governed skill authoring drafts.", no_args_is_help=True)

    @draft_app.command("list")
    def list_drafts(
        ctx: typer.Context,
        status_value: SkillDraftStatus | None = typer.Option(
            None,
            "--status",
            case_sensitive=False,
            help="Optional draft status filter.",
        ),
        skill_name: str | None = typer.Option(None, help="Optional skill name filter."),
        run_id: str | None = typer.Option(None, help="Optional creator run id filter."),
        workspace_dir: str | None = typer.Option(
            None,
            help="Optional workspace filter.",
        ),
        limit: int = typer.Option(100, min=1, max=500, help="Maximum drafts to list."),
    ) -> None:
        container = ensure_container(ctx)
        try:
            drafts = container.require(AppKey.SKILL_MANAGER).list_drafts(
                status=status_value.value if status_value is not None else None,
                skill_name=skill_name,
                run_id=run_id,
                workspace_dir=workspace_dir,
                limit=limit,
            )
        except SkillError as exc:
            _exit_error(str(exc))
        echo_data([_draft_payload(draft) for draft in drafts])

    @draft_app.command("show")
    def show_draft(
        ctx: typer.Context,
        draft_id: str = typer.Argument(..., help="Draft id."),
    ) -> None:
        container = ensure_container(ctx)
        try:
            draft = container.require(AppKey.SKILL_MANAGER).get_draft(draft_id)
        except SkillError as exc:
            _exit_error(str(exc))
        echo_data(_draft_payload(draft))

    @draft_app.command("audit")
    def audit_draft(
        ctx: typer.Context,
        draft_id: str = typer.Argument(..., help="Draft id."),
        limit: int = typer.Option(100, min=1, max=500, help="Maximum records to list."),
    ) -> None:
        container = ensure_container(ctx)
        try:
            records = container.require(AppKey.SKILL_MANAGER).list_draft_audit(
                draft_id=draft_id,
                limit=limit,
            )
        except SkillError as exc:
            _exit_error(str(exc))
        echo_data([_draft_audit_payload(record) for record in records])

    @draft_app.command("create")
    def create_draft(
        ctx: typer.Context,
        skill_name: str = typer.Argument(..., help="Target skill name."),
        intent: SkillDraftIntent = typer.Option(
            SkillDraftIntent.CREATE,
            "--intent",
            case_sensitive=False,
            help="Draft intent.",
        ),
        instructions: str | None = typer.Option(None, help="Draft SKILL.md body."),
        instructions_file: str | None = typer.Option(
            None,
            help="File containing draft SKILL.md body.",
        ),
        manifest_json: str | None = typer.Option(
            None,
            help="Draft manifest JSON object.",
        ),
        description: str | None = typer.Option(
            None,
            help="Manifest description when --manifest-json omits it.",
        ),
        version: str | None = typer.Option(None, help="Manifest version."),
        tags: str | None = typer.Option(None, help="Comma-separated manifest tags."),
        target_scope: SkillInstallScope = typer.Option(
            SkillInstallScope.WORKSPACE,
            "--target-scope",
            case_sensitive=False,
            help="Target install scope.",
        ),
        target_source_id: str | None = typer.Option(
            None,
            help="Optional target source id.",
        ),
        workspace_dir: str | None = typer.Option(None, help="Target workspace root."),
        base_fingerprint: str | None = typer.Option(
            None,
            help="Observed target package fingerprint for update drafts.",
        ),
        support_files_json: str | None = typer.Option(
            None,
            help="JSON array of support file objects with path/content.",
        ),
        support_file: list[str] | None = typer.Option(
            None,
            "--support-file",
            help="Support file in path=content form. May be repeated.",
        ),
        requirements_json: str | None = typer.Option(
            None,
            help="Requirements JSON object.",
        ),
        required_tools: str | None = typer.Option(
            None,
            help="Comma-separated required tool ids.",
        ),
        optional_tools: str | None = typer.Option(
            None,
            help="Comma-separated optional tool ids.",
        ),
        suggested_tools: str | None = typer.Option(
            None,
            help="Comma-separated suggested tool ids.",
        ),
        required_effects: str | None = typer.Option(
            None,
            help="Comma-separated Authorization effect ids.",
        ),
        required_access: str | None = typer.Option(
            None,
            help="Comma-separated Access requirement ids.",
        ),
        surfaces: str | None = typer.Option(
            None,
            help="Comma-separated runtime surfaces.",
        ),
        supported_platforms: str | None = typer.Option(
            None,
            help="Comma-separated supported platform tags.",
        ),
        setup_hints: str | None = typer.Option(
            None,
            help="Comma-separated setup hints.",
        ),
        created_by_run_id: str | None = typer.Option(None, help="Creator run id."),
        created_by_turn_id: str | None = typer.Option(None, help="Creator turn id."),
        actor: str | None = typer.Option(None, help="Actor creating the draft."),
        reason: str | None = typer.Option(None, help="Authoring reason."),
    ) -> None:
        container = ensure_container(ctx)
        try:
            body = _read_text_option(
                inline=instructions,
                path=instructions_file,
                option_name="--instructions",
            )
            draft = container.require(AppKey.SKILL_MANAGER).create_draft(
                SkillDraftCreateRequest(
                    intent=intent,
                    skill_name=skill_name,
                    manifest=_manifest_from_options(
                        skill_name=skill_name,
                        manifest_json=manifest_json,
                        description=description,
                        version=version,
                        tags=tags,
                    ),
                    instructions_body=body or "",
                    target_scope=target_scope,
                    target_source_id=target_source_id,
                    workspace_dir=workspace_dir,
                    base_fingerprint=base_fingerprint,
                    support_files=_support_files_from_options(
                        support_files_json=support_files_json,
                        support_file=support_file,
                    ),
                    requirements=_requirements_from_options(
                        requirements_json=requirements_json,
                        required_tools=required_tools,
                        optional_tools=optional_tools,
                        suggested_tools=suggested_tools,
                        required_effects=required_effects,
                        required_access=required_access,
                        surfaces=surfaces,
                        supported_platforms=supported_platforms,
                        setup_hints=setup_hints,
                    ),
                    created_by_run_id=created_by_run_id,
                    created_by_turn_id=created_by_turn_id,
                    actor=actor,
                    reason=reason,
                ),
            )
        except SkillError as exc:
            _exit_error(str(exc))
        echo_data(_draft_payload(draft))

    @draft_app.command("update")
    def update_draft(
        ctx: typer.Context,
        draft_id: str = typer.Argument(..., help="Draft id."),
        instructions: str | None = typer.Option(None, help="Updated SKILL.md body."),
        instructions_file: str | None = typer.Option(
            None,
            help="File containing updated SKILL.md body.",
        ),
        manifest_json: str | None = typer.Option(
            None,
            help="Updated manifest JSON object.",
        ),
        support_files_json: str | None = typer.Option(
            None,
            help="Replacement support files JSON array with path/content.",
        ),
        support_file: list[str] | None = typer.Option(
            None,
            "--support-file",
            help="Replacement support file in path=content form. May be repeated.",
        ),
        requirements_json: str | None = typer.Option(
            None,
            help="Replacement requirements JSON object.",
        ),
        required_tools: str | None = typer.Option(
            None,
            help="Comma-separated required tool ids.",
        ),
        optional_tools: str | None = typer.Option(
            None,
            help="Comma-separated optional tool ids.",
        ),
        suggested_tools: str | None = typer.Option(
            None,
            help="Comma-separated suggested tool ids.",
        ),
        required_effects: str | None = typer.Option(
            None,
            help="Comma-separated Authorization effect ids.",
        ),
        required_access: str | None = typer.Option(
            None,
            help="Comma-separated Access requirement ids.",
        ),
        surfaces: str | None = typer.Option(
            None,
            help="Comma-separated runtime surfaces.",
        ),
        supported_platforms: str | None = typer.Option(
            None,
            help="Comma-separated supported platform tags.",
        ),
        setup_hints: str | None = typer.Option(
            None,
            help="Comma-separated setup hints.",
        ),
        target_scope: SkillInstallScope | None = typer.Option(
            None,
            "--target-scope",
            case_sensitive=False,
            help="Updated target install scope.",
        ),
        target_source_id: str | None = typer.Option(
            None,
            help="Updated target source id.",
        ),
        workspace_dir: str | None = typer.Option(None, help="Updated workspace root."),
        actor: str | None = typer.Option(None, help="Actor updating the draft."),
        reason: str | None = typer.Option(None, help="Update reason."),
    ) -> None:
        container = ensure_container(ctx)
        try:
            body = _read_text_option(
                inline=instructions,
                path=instructions_file,
                option_name="--instructions",
            )
            has_support_files = support_files_json is not None or bool(support_file)
            has_requirements = _requirements_option_was_provided(
                requirements_json=requirements_json,
                required_tools=required_tools,
                optional_tools=optional_tools,
                suggested_tools=suggested_tools,
                required_effects=required_effects,
                required_access=required_access,
                surfaces=surfaces,
                supported_platforms=supported_platforms,
                setup_hints=setup_hints,
            )
            draft = container.require(AppKey.SKILL_MANAGER).update_draft(
                draft_id=draft_id,
                request=SkillDraftUpdateRequest(
                    manifest=(
                        _load_json_object(manifest_json, "--manifest-json")
                        if manifest_json is not None
                        else None
                    ),
                    instructions_body=body,
                    support_files=(
                        _support_files_from_options(
                            support_files_json=support_files_json,
                            support_file=support_file,
                        )
                        if has_support_files
                        else None
                    ),
                    requirements=(
                        _requirements_from_options(
                            requirements_json=requirements_json,
                            required_tools=required_tools,
                            optional_tools=optional_tools,
                            suggested_tools=suggested_tools,
                            required_effects=required_effects,
                            required_access=required_access,
                            surfaces=surfaces,
                            supported_platforms=supported_platforms,
                            setup_hints=setup_hints,
                        )
                        if has_requirements
                        else None
                    ),
                    target_scope=target_scope,
                    target_source_id=target_source_id,
                    workspace_dir=workspace_dir,
                    actor=actor,
                    reason=reason,
                ),
            )
        except SkillError as exc:
            _exit_error(str(exc))
        echo_data(_draft_payload(draft))

    @draft_app.command("validate")
    def validate_draft(
        ctx: typer.Context,
        draft_id: str = typer.Argument(..., help="Draft id."),
    ) -> None:
        container = ensure_container(ctx)
        try:
            draft = container.require(AppKey.SKILL_MANAGER).validate_draft(draft_id)
        except SkillError as exc:
            _exit_error(str(exc))
        echo_data(_draft_payload(draft))

    @draft_app.command("diff")
    def diff_draft(
        ctx: typer.Context,
        draft_id: str = typer.Argument(..., help="Draft id."),
    ) -> None:
        container = ensure_container(ctx)
        try:
            draft = container.require(AppKey.SKILL_MANAGER).build_draft_diff(draft_id)
        except SkillError as exc:
            _exit_error(str(exc))
        echo_data(_draft_payload(draft))

    @draft_app.command("apply")
    def apply_draft(
        ctx: typer.Context,
        draft_id: str = typer.Argument(..., help="Draft id."),
        reason: str | None = typer.Option(None, help="Apply reason."),
    ) -> None:
        container = ensure_container(ctx)
        try:
            draft = container.require(AppKey.SKILL_MANAGER).apply_draft(
                draft_id=draft_id,
                reason=reason,
            )
        except SkillError as exc:
            _exit_error(str(exc))
        echo_data(_draft_payload(draft))

    @draft_app.command("reject")
    def reject_draft(
        ctx: typer.Context,
        draft_id: str = typer.Argument(..., help="Draft id."),
        reason: str | None = typer.Option(None, help="Reject reason."),
    ) -> None:
        container = ensure_container(ctx)
        try:
            draft = container.require(AppKey.SKILL_MANAGER).reject_draft(
                draft_id=draft_id,
                reason=reason,
            )
        except SkillError as exc:
            _exit_error(str(exc))
        echo_data(_draft_payload(draft))

    @draft_app.command("delete")
    def delete_draft(
        ctx: typer.Context,
        draft_id: str = typer.Argument(..., help="Draft id."),
    ) -> None:
        container = ensure_container(ctx)
        try:
            draft = container.require(AppKey.SKILL_MANAGER).delete_draft(draft_id)
        except SkillError as exc:
            _exit_error(str(exc))
        echo_data(_draft_payload(draft))

    app.add_typer(draft_app, name="draft")

    @app.command("sync")
    def sync_skills(
        ctx: typer.Context,
        workspace_dir: str | None = typer.Option(
            None,
            help="Optional session workspace used for workspace skill discovery.",
        ),
        source_id: str | None = typer.Option(
            None,
            help="Optional source id to sync.",
        ),
        surface: str = typer.Option(
            "interactive",
            help="Optional run surface for filtering.",
        ),
    ) -> None:
        container = ensure_container(ctx)
        try:
            result = container.require(AppKey.SKILL_MANAGER).sync(
                workspace_dir=workspace_dir,
                source_id=source_id,
                surface=surface,
            )
        except SkillError as exc:
            _exit_error(str(exc))
        echo_data(_sync_payload(result))

    @app.command("readiness")
    def readiness(
        ctx: typer.Context,
        skill_name: str | None = typer.Argument(None, help="Optional skill name."),
        workspace_dir: str | None = typer.Option(
            None,
            help="Optional session workspace used for workspace skill discovery.",
        ),
        surface: str = typer.Option(
            "interactive",
            help="Optional run surface for filtering.",
        ),
    ) -> None:
        container = ensure_container(ctx)
        try:
            result = container.require(AppKey.SKILL_MANAGER).readiness(
                workspace_dir=workspace_dir,
                skill_name=skill_name,
                surface=surface,
            )
        except SkillError as exc:
            _exit_error(str(exc))
        echo_data({name: _readiness_payload(item) for name, item in result.items()})

    @app.command("show")
    def show_skill(
        ctx: typer.Context,
        skill_name: str = typer.Argument(..., help="Skill name."),
        workspace_dir: str | None = typer.Option(
            None,
            help="Optional session workspace used for workspace skill discovery.",
        ),
        surface: str = typer.Option(
            "interactive",
            help="Optional run surface for future filtering.",
        ),
        include_instructions: bool = typer.Option(
            False,
            "--include-instructions",
            help="Include the resolved SKILL.md content.",
        ),
    ) -> None:
        container = ensure_container(ctx)
        try:
            package = container.require(AppKey.SKILL_MANAGER).get(
                workspace_dir=workspace_dir,
                skill_name=skill_name,
                surface=surface,
            )
            instructions = None
            if include_instructions:
                instructions = container.require(AppKey.SKILL_MANAGER).read(
                    workspace_dir=workspace_dir,
                    skill_name=skill_name,
                    path=None,
                    surface=surface,
                ).content
        except SkillError as exc:
            _exit_error(str(exc))
        echo_data(_skill_payload(package, instructions=instructions))

    @app.command("get")
    def get_skill(
        ctx: typer.Context,
        skill_name: str = typer.Argument(..., help="Skill name."),
        workspace_dir: str | None = typer.Option(
            None,
            help="Optional session workspace used for workspace skill discovery.",
        ),
        surface: str = typer.Option(
            "interactive",
            help="Optional run surface for future filtering.",
        ),
        include_instructions: bool = typer.Option(
            False,
            "--include-instructions",
            help="Include the resolved SKILL.md content.",
        ),
    ) -> None:
        container = ensure_container(ctx)
        try:
            package = container.require(AppKey.SKILL_MANAGER).get(
                workspace_dir=workspace_dir,
                skill_name=skill_name,
                surface=surface,
            )
            instructions = None
            if include_instructions:
                instructions = container.require(AppKey.SKILL_MANAGER).read(
                    workspace_dir=workspace_dir,
                    skill_name=skill_name,
                    path=None,
                    surface=surface,
                ).content
        except SkillError as exc:
            _exit_error(str(exc))
        echo_data(_skill_payload(package, instructions=instructions))

    @app.command("read")
    def read_skill(
        ctx: typer.Context,
        skill_name: str = typer.Argument(..., help="Skill name."),
        path: str | None = typer.Argument(None, help="Optional package-relative path."),
        workspace_dir: str | None = typer.Option(
            None,
            help="Optional session workspace used for workspace skill discovery.",
        ),
        surface: str = typer.Option(
            "interactive",
            help="Optional run surface for filtering.",
        ),
    ) -> None:
        container = ensure_container(ctx)
        try:
            result = container.require(AppKey.SKILL_MANAGER).read(
                workspace_dir=workspace_dir,
                skill_name=skill_name,
                path=path,
                surface=surface,
            )
        except SkillError as exc:
            _exit_error(str(exc))
        echo_data(_read_payload(result))

    @app.command("validate")
    def validate_skill(
        ctx: typer.Context,
        path: str = typer.Argument(..., help="Path to a skill package directory."),
    ) -> None:
        container = ensure_container(ctx)
        try:
            package = container.require(AppKey.SKILL_MANAGER).validate(path=path)
        except SkillError as exc:
            _exit_error(str(exc))
        echo_data(_skill_payload(package))

    @app.command("install")
    def install_skill(
        ctx: typer.Context,
        source_dir: str = typer.Argument(..., help="Path to a skill package directory."),
        scope: SkillInstallScope = typer.Option(
            SkillInstallScope.WORKSPACE,
            "--scope",
            case_sensitive=False,
            help="Install destination scope.",
        ),
        workspace_dir: str | None = typer.Option(
            None,
            help="Workspace root required for workspace installs.",
        ),
    ) -> None:
        container = ensure_container(ctx)
        try:
            result = container.require(AppKey.SKILL_MANAGER).install(
                source_dir=source_dir,
                scope=scope,
                workspace_dir=workspace_dir,
            )
        except SkillError as exc:
            _exit_error(str(exc))
        echo_data(_install_payload(result))

    @app.command("create")
    def create_skill(
        ctx: typer.Context,
        skill_name: str = typer.Argument(..., help="Skill name."),
        description: str = typer.Option(..., help="Skill description."),
        instructions: str = typer.Option(..., help="Initial SKILL.md body."),
        scope: SkillInstallScope = typer.Option(
            SkillInstallScope.WORKSPACE,
            "--scope",
            case_sensitive=False,
            help="Create destination scope.",
        ),
        workspace_dir: str | None = typer.Option(
            None,
            help="Workspace root required for workspace skill creation.",
        ),
        tags: str | None = typer.Option(None, help="Comma-separated tags."),
        required_tools: str | None = typer.Option(
            None,
            help="Comma-separated required tool ids.",
        ),
        suggested_tools: str | None = typer.Option(
            None,
            help="Comma-separated suggested tool ids.",
        ),
        required_access: str | None = typer.Option(
            None,
            help="Comma-separated Access binding or requirement ids.",
        ),
        supported_platforms: str | None = typer.Option(
            None,
            help="Comma-separated supported platform tags such as linux, macos, windows.",
        ),
    ) -> None:
        container = ensure_container(ctx)
        try:
            result = container.require(AppKey.SKILL_MANAGER).create(
                SkillCreateRequest(
                    name=skill_name,
                    description=description,
                    instructions=instructions,
                    scope=scope,
                    workspace_dir=workspace_dir,
                    tags=_csv_tuple(tags),
                    required_tools=_csv_tuple(required_tools),
                    suggested_tools=_csv_tuple(suggested_tools),
                    required_access=_csv_tuple(required_access),
                    supported_platforms=_csv_tuple(supported_platforms),
                ),
            )
        except SkillError as exc:
            _exit_error(str(exc))
        echo_data(_mutation_payload(result))

    @app.command("update")
    def update_skill(
        ctx: typer.Context,
        skill_name: str = typer.Argument(..., help="Skill name."),
        workspace_dir: str | None = typer.Option(
            None,
            help="Optional session workspace used for workspace skill discovery.",
        ),
        description: str | None = typer.Option(None, help="Updated description."),
        version: str | None = typer.Option(None, help="Updated version."),
        tags: str | None = typer.Option(None, help="Comma-separated tags."),
        required_tools: str | None = typer.Option(
            None,
            help="Comma-separated required tool ids.",
        ),
        suggested_tools: str | None = typer.Option(
            None,
            help="Comma-separated suggested tool ids.",
        ),
        required_access: str | None = typer.Option(
            None,
            help="Comma-separated Access binding or requirement ids.",
        ),
        supported_platforms: str | None = typer.Option(
            None,
            help="Comma-separated supported platform tags such as linux, macos, windows.",
        ),
    ) -> None:
        container = ensure_container(ctx)
        try:
            result = container.require(AppKey.SKILL_MANAGER).update(
                SkillUpdateRequest(
                    skill_name=skill_name,
                    workspace_dir=workspace_dir,
                    description=description,
                    version=version,
                    tags=_optional_csv_tuple(tags),
                    required_tools=_optional_csv_tuple(required_tools),
                    suggested_tools=_optional_csv_tuple(suggested_tools),
                    required_access=_optional_csv_tuple(required_access),
                    supported_platforms=_optional_csv_tuple(supported_platforms),
                ),
            )
        except SkillError as exc:
            _exit_error(str(exc))
        echo_data(_mutation_payload(result))

    @app.command("write-instructions")
    def write_instructions(
        ctx: typer.Context,
        skill_name: str = typer.Argument(..., help="Skill name."),
        content: str = typer.Argument(..., help="New SKILL.md body content."),
        workspace_dir: str | None = typer.Option(
            None,
            help="Optional session workspace used for workspace skill discovery.",
        ),
    ) -> None:
        container = ensure_container(ctx)
        try:
            result = container.require(AppKey.SKILL_MANAGER).write_instructions(
                workspace_dir=workspace_dir,
                skill_name=skill_name,
                content=content,
            )
        except SkillError as exc:
            _exit_error(str(exc))
        echo_data(_mutation_payload(result))

    @app.command("write-file")
    def write_file(
        ctx: typer.Context,
        skill_name: str = typer.Argument(..., help="Skill name."),
        path: str = typer.Argument(..., help="Package-relative support file path."),
        content: str = typer.Argument(..., help="File text content."),
        workspace_dir: str | None = typer.Option(
            None,
            help="Optional session workspace used for workspace skill discovery.",
        ),
    ) -> None:
        container = ensure_container(ctx)
        try:
            result = container.require(AppKey.SKILL_MANAGER).write_file(
                workspace_dir=workspace_dir,
                skill_name=skill_name,
                path=path,
                content=content,
            )
        except SkillError as exc:
            _exit_error(str(exc))
        echo_data(_mutation_payload(result))

    @app.command("delete-file")
    def delete_file(
        ctx: typer.Context,
        skill_name: str = typer.Argument(..., help="Skill name."),
        path: str = typer.Argument(..., help="Package-relative support file path."),
        workspace_dir: str | None = typer.Option(
            None,
            help="Optional session workspace used for workspace skill discovery.",
        ),
    ) -> None:
        container = ensure_container(ctx)
        try:
            result = container.require(AppKey.SKILL_MANAGER).delete_file(
                workspace_dir=workspace_dir,
                skill_name=skill_name,
                path=path,
            )
        except SkillError as exc:
            _exit_error(str(exc))
        echo_data(_mutation_payload(result))

    @app.command("enable")
    def enable_skill(
        ctx: typer.Context,
        skill_name: str = typer.Argument(..., help="Skill name."),
        workspace_dir: str | None = typer.Option(
            None,
            help="Optional session workspace used for workspace skill discovery.",
        ),
        surface: str = typer.Option(
            "interactive",
            help="Optional run surface for filtering.",
        ),
        reason: str | None = typer.Option(None, help="Optional governance reason."),
    ) -> None:
        container = ensure_container(ctx)
        try:
            result = container.require(AppKey.SKILL_MANAGER).enable(
                workspace_dir=workspace_dir,
                skill_name=skill_name,
                reason=reason,
                surface=surface,
            )
        except SkillError as exc:
            _exit_error(str(exc))
        echo_data(_mutation_payload(result))

    @app.command("disable")
    def disable_skill(
        ctx: typer.Context,
        skill_name: str = typer.Argument(..., help="Skill name."),
        workspace_dir: str | None = typer.Option(
            None,
            help="Optional session workspace used for workspace skill discovery.",
        ),
        surface: str = typer.Option(
            "interactive",
            help="Optional run surface for filtering.",
        ),
        reason: str | None = typer.Option(None, help="Optional governance reason."),
    ) -> None:
        container = ensure_container(ctx)
        try:
            result = container.require(AppKey.SKILL_MANAGER).disable(
                workspace_dir=workspace_dir,
                skill_name=skill_name,
                reason=reason,
                surface=surface,
            )
        except SkillError as exc:
            _exit_error(str(exc))
        echo_data(_mutation_payload(result))

    @app.command("delete")
    def delete_skill(
        ctx: typer.Context,
        skill_name: str = typer.Argument(..., help="Skill name."),
        workspace_dir: str | None = typer.Option(
            None,
            help="Optional session workspace used for workspace skill discovery.",
        ),
        surface: str = typer.Option(
            "interactive",
            help="Optional run surface for filtering.",
        ),
    ) -> None:
        container = ensure_container(ctx)
        try:
            result = container.require(AppKey.SKILL_MANAGER).uninstall(
                workspace_dir=workspace_dir,
                skill_name=skill_name,
                surface=surface,
            )
        except SkillError as exc:
            _exit_error(str(exc))
        echo_data(_mutation_payload(result))

    @app.command("uninstall")
    def uninstall_skill(
        ctx: typer.Context,
        skill_name: str = typer.Argument(..., help="Skill name."),
        workspace_dir: str | None = typer.Option(
            None,
            help="Optional session workspace used for workspace skill discovery.",
        ),
        surface: str = typer.Option(
            "interactive",
            help="Optional run surface for filtering.",
        ),
    ) -> None:
        container = ensure_container(ctx)
        try:
            result = container.require(AppKey.SKILL_MANAGER).uninstall(
                workspace_dir=workspace_dir,
                skill_name=skill_name,
                surface=surface,
            )
        except SkillError as exc:
            _exit_error(str(exc))
        echo_data(_mutation_payload(result))

    return app
