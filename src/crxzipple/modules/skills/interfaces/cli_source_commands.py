from __future__ import annotations

import typer

from crxzipple.interfaces.cli.context import AppKey, ensure_container
from crxzipple.interfaces.cli.formatters import echo_data
from crxzipple.modules.skills.application.models import (
    SkillSourceCreateRequest,
    SkillSourceKind,
    SkillSourceUpdateRequest,
)
from crxzipple.modules.skills.domain import SkillError
from crxzipple.modules.skills.interfaces.cli_errors import exit_error
from crxzipple.modules.skills.interfaces.cli_payloads import (
    _source_mutation_payload,
    _source_payload,
)


def build_source_cli() -> typer.Typer:
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
            exit_error(str(exc))
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
            exit_error(str(exc))
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
            exit_error(str(exc))
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
            exit_error(str(exc))
        echo_data(_source_mutation_payload(result))

    return source_app
