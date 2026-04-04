from __future__ import annotations

import typer

from crxzipple.interfaces.cli.context import ensure_container
from crxzipple.interfaces.cli.formatters import echo_data
from crxzipple.modules.skills.application.models import InstalledSkill, SkillPackage
from crxzipple.modules.skills.domain import SkillError, SkillInstallScope


def _exit_error(message: str) -> None:
    typer.secho(message, err=True, fg=typer.colors.RED)
    raise typer.Exit(code=1) from None


def _skill_payload(
    package: SkillPackage,
    *,
    instructions: str | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "name": package.name,
        "description": package.description,
        "version": package.version,
        "tags": list(package.tags),
        "source": package.source,
        "root_path": package.root_path,
        "manifest_path": package.manifest_path,
        "instructions_path": package.instructions_path,
        "manifest": {
            "api_version": package.manifest.api_version,
            "kind": package.manifest.kind,
            "name": package.manifest.name,
            "description": package.manifest.description,
            "version": package.manifest.version,
            "tags": list(package.manifest.tags),
            "instructions_path": package.manifest.instructions_path,
            "required_tools": list(package.manifest.required_tools),
            "optional_tools": list(package.manifest.optional_tools),
            "allowed_tools": list(package.manifest.allowed_tools),
        },
    }
    if instructions is not None:
        payload["instructions"] = instructions
    return payload


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
    ) -> None:
        container = ensure_container(ctx)
        skills = container.skill_manager.list_available(
            workspace_dir=workspace_dir,
            surface=surface,
        )
        echo_data([_skill_payload(skill) for skill in skills])

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
            package = container.skill_manager.get(
                workspace_dir=workspace_dir,
                skill_name=skill_name,
                surface=surface,
            )
            instructions = None
            if include_instructions:
                instructions = container.skill_manager.read(
                    workspace_dir=workspace_dir,
                    skill_name=skill_name,
                    path=None,
                    surface=surface,
                ).content
        except SkillError as exc:
            _exit_error(str(exc))
        echo_data(_skill_payload(package, instructions=instructions))

    @app.command("validate")
    def validate_skill(
        ctx: typer.Context,
        path: str = typer.Argument(..., help="Path to a skill package directory."),
    ) -> None:
        container = ensure_container(ctx)
        try:
            package = container.skill_manager.validate(path=path)
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
            result = container.skill_manager.install(
                source_dir=source_dir,
                scope=scope,
                workspace_dir=workspace_dir,
            )
        except SkillError as exc:
            _exit_error(str(exc))
        echo_data(_install_payload(result))

    return app
