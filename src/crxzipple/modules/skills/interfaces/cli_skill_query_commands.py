from __future__ import annotations

import typer

from crxzipple.interfaces.cli.context import AppKey, ensure_container
from crxzipple.interfaces.cli.formatters import echo_data
from crxzipple.modules.skills.domain import SkillError
from crxzipple.modules.skills.interfaces.cli_errors import exit_error
from crxzipple.modules.skills.interfaces.cli_payloads import (
    _read_payload,
    _readiness_payload,
    _skill_payload,
)


def register_skill_query_commands(app: typer.Typer) -> None:
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
        _show_skill(
            ctx,
            skill_name=skill_name,
            workspace_dir=workspace_dir,
            surface=surface,
            include_instructions=include_instructions,
        )

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
        _show_skill(
            ctx,
            skill_name=skill_name,
            workspace_dir=workspace_dir,
            surface=surface,
            include_instructions=include_instructions,
        )

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


def _show_skill(
    ctx: typer.Context,
    *,
    skill_name: str,
    workspace_dir: str | None,
    surface: str,
    include_instructions: bool,
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
