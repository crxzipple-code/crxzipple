from __future__ import annotations

from collections.abc import Callable

import typer

from crxzipple.interfaces.cli.context import AppKey, ensure_container
from crxzipple.interfaces.cli.formatters import echo_data
from crxzipple.modules.skills.application.models import SkillDraft
from crxzipple.modules.skills.domain import SkillError
from crxzipple.modules.skills.interfaces.cli_errors import exit_error
from crxzipple.modules.skills.interfaces.cli_payloads import _draft_payload


def register_draft_lifecycle_commands(app: typer.Typer) -> None:
    @app.command("validate")
    def validate_draft(
        ctx: typer.Context,
        draft_id: str = typer.Argument(..., help="Draft id."),
    ) -> None:
        _run_draft_action(
            ctx,
            lambda manager: manager.validate_draft(draft_id),
        )

    @app.command("diff")
    def diff_draft(
        ctx: typer.Context,
        draft_id: str = typer.Argument(..., help="Draft id."),
    ) -> None:
        _run_draft_action(
            ctx,
            lambda manager: manager.build_draft_diff(draft_id),
        )

    @app.command("apply")
    def apply_draft(
        ctx: typer.Context,
        draft_id: str = typer.Argument(..., help="Draft id."),
        reason: str | None = typer.Option(None, help="Apply reason."),
    ) -> None:
        _run_draft_action(
            ctx,
            lambda manager: manager.apply_draft(
                draft_id=draft_id,
                reason=reason,
            ),
        )

    @app.command("reject")
    def reject_draft(
        ctx: typer.Context,
        draft_id: str = typer.Argument(..., help="Draft id."),
        reason: str | None = typer.Option(None, help="Reject reason."),
    ) -> None:
        _run_draft_action(
            ctx,
            lambda manager: manager.reject_draft(
                draft_id=draft_id,
                reason=reason,
            ),
        )

    @app.command("delete")
    def delete_draft(
        ctx: typer.Context,
        draft_id: str = typer.Argument(..., help="Draft id."),
    ) -> None:
        _run_draft_action(
            ctx,
            lambda manager: manager.delete_draft(draft_id),
        )


def _run_draft_action(
    ctx: typer.Context,
    action: Callable[[object], SkillDraft],
) -> None:
    container = ensure_container(ctx)
    try:
        draft = action(container.require(AppKey.SKILL_MANAGER))
    except SkillError as exc:
        exit_error(str(exc))
    echo_data(_draft_payload(draft))
