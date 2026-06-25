from __future__ import annotations

import typer

from crxzipple.interfaces.cli.context import AppKey, ensure_container
from crxzipple.interfaces.cli.formatters import echo_data
from crxzipple.modules.browser.domain import BrowserValidationError

from .cli_helpers import _default_profile, _load_payload
from .requests import BrowserControlRequest, BrowserPageActionRequest


def register_action_commands(app: typer.Typer) -> None:
    @app.command("control")
    def execute_control(
        ctx: typer.Context,
        kind: str = typer.Argument(..., help="Control kind."),
        profile: str | None = typer.Option(
            None, "--profile", help="Browser profile name."
        ),
        target_id: str | None = typer.Option(
            None, "--target-id", help="Browser tab id."
        ),
        payload: str | None = typer.Option(
            None, "--payload", help="JSON object payload."
        ),
        timeout_ms: int | None = typer.Option(None, "--timeout-ms", min=1),
    ) -> None:
        container = ensure_container(ctx)
        try:
            result = container.require(AppKey.BROWSER_FACADE).execute(
                BrowserControlRequest(
                    profile_name=profile or _default_profile(container),
                    kind=kind,
                    target_id=target_id,
                    payload=_load_payload(payload),
                    timeout_ms=timeout_ms,
                ),
            )
        except BrowserValidationError as exc:
            raise typer.BadParameter(str(exc)) from exc
        echo_data(container.require(AppKey.BROWSER_RESULT_SERIALIZER).serialize(result))

    @app.command("act")
    def execute_page_action(
        ctx: typer.Context,
        kind: str = typer.Argument(..., help="Page action kind."),
        profile: str | None = typer.Option(
            None, "--profile", help="Browser profile name."
        ),
        target_id: str | None = typer.Option(
            None, "--target-id", help="Browser tab id."
        ),
        ref: str | None = typer.Option(None, "--ref", help="Element ref."),
        selector: str | None = typer.Option(None, "--selector", help="CSS selector."),
        payload: str | None = typer.Option(
            None, "--payload", help="JSON object payload."
        ),
        timeout_ms: int | None = typer.Option(None, "--timeout-ms", min=1),
    ) -> None:
        container = ensure_container(ctx)
        try:
            result = container.require(AppKey.BROWSER_FACADE).execute(
                BrowserPageActionRequest(
                    profile_name=profile or _default_profile(container),
                    kind=kind,
                    target_id=target_id,
                    ref=ref,
                    selector=selector,
                    payload=_load_payload(payload),
                    timeout_ms=timeout_ms,
                ),
            )
        except BrowserValidationError as exc:
            raise typer.BadParameter(str(exc)) from exc
        echo_data(container.require(AppKey.BROWSER_RESULT_SERIALIZER).serialize(result))
