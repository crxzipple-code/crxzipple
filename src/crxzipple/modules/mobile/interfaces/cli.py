from __future__ import annotations

import json
from typing import Any

import typer

from crxzipple.interfaces.cli.context import ensure_container
from crxzipple.interfaces.cli.formatters import echo_data
from crxzipple.modules.mobile.domain import MobileExecutionError, MobileValidationError

from .requests import MobileActionRequest, MobileControlRequest


def _load_payload(raw: str | None) -> dict[str, Any]:
    if raw is None:
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise typer.BadParameter("payload must be valid JSON.") from exc
    if not isinstance(payload, dict):
        raise typer.BadParameter("payload JSON must decode to an object.")
    return dict(payload)


def _default_device(container) -> str | None:  # noqa: ANN001
    return container.mobile_system_config_store.load().default_device


def build_cli() -> typer.Typer:
    app = typer.Typer(help="Control Android devices through adb-backed mobile automation.", no_args_is_help=True)

    @app.command("control")
    def execute_control(
        ctx: typer.Context,
        kind: str = typer.Argument(..., help="Mobile control kind."),
        device: str | None = typer.Option(None, "--device", help="Configured mobile device name."),
        payload: str | None = typer.Option(None, "--payload", help="JSON payload."),
        timeout_ms: int | None = typer.Option(None, "--timeout-ms", min=1),
    ) -> None:
        container = ensure_container(ctx)
        try:
            result = container.mobile_facade.execute(
                MobileControlRequest(
                    device_name=device or _default_device(container),
                    kind=kind,
                    payload=_load_payload(payload),
                    timeout_ms=timeout_ms,
                ),
            )
        except (MobileValidationError, MobileExecutionError) as exc:
            raise typer.BadParameter(str(exc)) from exc
        echo_data(container.mobile_result_serializer.serialize(result))

    @app.command("act")
    def execute_action(
        ctx: typer.Context,
        kind: str = typer.Argument(..., help="Mobile action kind."),
        device: str | None = typer.Option(None, "--device", help="Configured mobile device name."),
        ref: str | None = typer.Option(None, "--ref", help="Stored mobile ref."),
        selector: str | None = typer.Option(None, "--selector", help="UI selector such as `xpath=...`, `id=...`, or `accessibility_id=...`."),
        payload: str | None = typer.Option(None, "--payload", help="JSON payload."),
        timeout_ms: int | None = typer.Option(None, "--timeout-ms", min=1),
    ) -> None:
        container = ensure_container(ctx)
        try:
            result = container.mobile_facade.execute(
                MobileActionRequest(
                    device_name=device or _default_device(container),
                    kind=kind,
                    ref=ref,
                    selector=selector,
                    payload=_load_payload(payload),
                    timeout_ms=timeout_ms,
                ),
            )
        except (MobileValidationError, MobileExecutionError) as exc:
            raise typer.BadParameter(str(exc)) from exc
        echo_data(container.mobile_result_serializer.serialize(result))

    return app
