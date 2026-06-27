from __future__ import annotations

import typer

from crxzipple.interfaces.cli.context import AppKey, ensure_container
from crxzipple.interfaces.cli.formatters import echo_data
from crxzipple.modules.skills.application.models import (
    SkillDraftCreateRequest,
    SkillDraftIntent,
    SkillDraftUpdateRequest,
)
from crxzipple.modules.skills.domain import SkillError, SkillInstallScope
from crxzipple.modules.skills.interfaces.cli_errors import exit_error
from crxzipple.modules.skills.interfaces.cli_options import (
    _load_json_object,
    _manifest_from_options,
    _read_text_option,
    _requirements_from_options,
    _requirements_option_was_provided,
    _support_files_from_options,
)
from crxzipple.modules.skills.interfaces.cli_payloads import _draft_payload


def register_draft_authoring_commands(app: typer.Typer) -> None:
    @app.command("create")
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
            exit_error(str(exc))
        echo_data(_draft_payload(draft))

    @app.command("update")
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
            exit_error(str(exc))
        echo_data(_draft_payload(draft))
