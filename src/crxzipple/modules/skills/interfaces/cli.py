from __future__ import annotations

import typer

from crxzipple.interfaces.cli.context import AppKey, ensure_container
from crxzipple.interfaces.cli.formatters import echo_data
from crxzipple.modules.skills.application.models import (
    SkillCreateRequest,
    SkillUpdateRequest,
)
from crxzipple.modules.skills.domain import (
    SkillError,
    SkillInstallScope,
)
from crxzipple.modules.skills.interfaces.cli_draft_commands import build_draft_cli
from crxzipple.modules.skills.interfaces.cli_errors import exit_error
from crxzipple.modules.skills.interfaces.cli_options import (
    _csv_tuple,
    _optional_csv_tuple,
)
from crxzipple.modules.skills.interfaces.cli_payloads import (
    _install_payload,
    _mutation_payload,
    _read_payload,
    _readiness_payload,
    _skill_payload,
    _sync_payload,
)
from crxzipple.modules.skills.interfaces.cli_source_commands import build_source_cli


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

    app.add_typer(build_source_cli(), name="source")
    app.add_typer(build_draft_cli(), name="draft")

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
            exit_error(str(exc))
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
            exit_error(str(exc))
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
            exit_error(str(exc))
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
            exit_error(str(exc))
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
            exit_error(str(exc))
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
            exit_error(str(exc))
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
            exit_error(str(exc))
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
            exit_error(str(exc))
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
            exit_error(str(exc))
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
            exit_error(str(exc))
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
            exit_error(str(exc))
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
            exit_error(str(exc))
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
            exit_error(str(exc))
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
            exit_error(str(exc))
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
            exit_error(str(exc))
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
            exit_error(str(exc))
        echo_data(_mutation_payload(result))

    return app
