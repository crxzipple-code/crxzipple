from __future__ import annotations

import typer

from crxzipple.interfaces.cli.context import AppKey, ensure_container
from crxzipple.interfaces.cli.formatters import echo_data
from crxzipple.modules.skills.application.models import SkillDraftStatus
from crxzipple.modules.skills.domain import SkillError
from crxzipple.modules.skills.interfaces.cli_errors import exit_error
from crxzipple.modules.skills.interfaces.cli_payloads import (
    _draft_audit_payload,
    _draft_payload,
)


def register_draft_query_commands(app: typer.Typer) -> None:
    @app.command("list")
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
            exit_error(str(exc))
        echo_data([_draft_payload(draft) for draft in drafts])

    @app.command("show")
    def show_draft(
        ctx: typer.Context,
        draft_id: str = typer.Argument(..., help="Draft id."),
    ) -> None:
        container = ensure_container(ctx)
        try:
            draft = container.require(AppKey.SKILL_MANAGER).get_draft(draft_id)
        except SkillError as exc:
            exit_error(str(exc))
        echo_data(_draft_payload(draft))

    @app.command("audit")
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
            exit_error(str(exc))
        echo_data([_draft_audit_payload(record) for record in records])
