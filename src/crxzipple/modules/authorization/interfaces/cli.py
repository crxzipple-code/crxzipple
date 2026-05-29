from __future__ import annotations

import json

import typer

from crxzipple.interfaces.cli.context import AppKey, ensure_container
from crxzipple.interfaces.cli.formatters import echo_data
from crxzipple.modules.authorization.domain import (
    AuthorizationContext,
    AuthorizationRequest,
    AuthorizationResource,
    AuthorizationSubject,
)


def _parse_json_object(payload: str | None, option_name: str) -> dict[str, object]:
    if payload is None:
        return {}
    try:
        value = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise typer.BadParameter(
            f"{option_name} must be valid JSON: {exc.msg}",
        ) from exc
    if not isinstance(value, dict):
        raise typer.BadParameter(f"{option_name} must decode to a JSON object.")
    return value


def build_cli() -> typer.Typer:
    app = typer.Typer(
        help="Manage authorization policies and decisions.",
        no_args_is_help=True,
    )

    @app.command("policies")
    def list_policies(ctx: typer.Context) -> None:
        container = ensure_container(ctx)
        echo_data(container.require(AppKey.AUTHORIZATION_SERVICE).list_policies())

    @app.command("check")
    def check_authorization(
        ctx: typer.Context,
        action: str = typer.Argument(..., help="Action identifier."),
        resource_kind: str = typer.Argument(..., help="Resource kind."),
        resource_id: str | None = typer.Option(None, help="Optional resource id."),
        subject_type: str = typer.Option("anonymous", help="Subject type."),
        subject_id: str | None = typer.Option(None, help="Optional subject id."),
        subject_attrs: str | None = typer.Option(
            None,
            help="JSON object of subject attributes.",
        ),
        resource_attrs: str | None = typer.Option(
            None,
            help="JSON object of resource attributes.",
        ),
        context: str | None = typer.Option(
            None,
            help="JSON object of contextual attributes.",
        ),
    ) -> None:
        container = ensure_container(ctx)
        decision = container.require(AppKey.AUTHORIZATION_SERVICE).check(
            AuthorizationRequest(
                subject=AuthorizationSubject(
                    type=subject_type,
                    id=subject_id,
                    attrs=_parse_json_object(subject_attrs, "--subject-attrs"),
                ),
                action=action,
                resource=AuthorizationResource(
                    kind=resource_kind,
                    id=resource_id,
                    attrs=_parse_json_object(resource_attrs, "--resource-attrs"),
                ),
                context=AuthorizationContext(
                    attrs=_parse_json_object(context, "--context"),
                ),
            ),
        )
        echo_data(decision)

    return app

