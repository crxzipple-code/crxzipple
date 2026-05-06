from __future__ import annotations

import json
import signal
from threading import Event
from typing import Any

import typer

from crxzipple.interfaces.cli.context import ensure_container
from crxzipple.interfaces.cli.formatters import echo_data
from crxzipple.modules.browser.domain import BrowserValidationError

from .profile_payloads import build_profile_diagnostics_payload
from .profile_payloads import build_profiles_payload
from .requests import BrowserControlRequest, BrowserPageActionRequest


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


def _default_profile(container) -> str:  # noqa: ANN001
    return container.browser_system_config_store.load().default_profile


def _system_config(container):  # noqa: ANN001
    return container.browser_system_config_store.load()


def _profiles_payload(container, system_config=None) -> dict[str, object]:  # noqa: ANN001
    return build_profiles_payload(container, system_config=system_config)


def _run_host_loop(
    container,  # noqa: ANN001
    *,
    profile_name: str,
    poll_interval_seconds: float,
    max_cycles: int | None = None,
    stop_event: Event | None = None,
) -> int:
    completed_cycles = 0
    stopper = stop_event or Event()
    while not stopper.is_set():
        container.browser_facade.execute(
            BrowserControlRequest(
                profile_name=profile_name,
                kind="list-tabs",
            )
        )
        completed_cycles += 1
        if max_cycles is not None and completed_cycles >= max_cycles:
            break
        stopper.wait(poll_interval_seconds)
    return completed_cycles


def _run_mcp_loop(
    container,  # noqa: ANN001
    *,
    profile_name: str,
    poll_interval_seconds: float,
    max_cycles: int | None = None,
    stop_event: Event | None = None,
) -> int:
    completed_cycles = 0
    stopper = stop_event or Event()
    while not stopper.is_set():
        container.browser_facade.execute(
            BrowserControlRequest(
                profile_name=profile_name,
                kind="list-tabs",
            )
        )
        completed_cycles += 1
        if max_cycles is not None and completed_cycles >= max_cycles:
            break
        stopper.wait(poll_interval_seconds)
    return completed_cycles


def _resolve_profile_update_kwargs(
    *,
    driver: str | None,
    cdp_url: str | None,
    cdp_port: int | None,
    clear_cdp_port: bool,
    user_data_dir: str | None,
    attach_only: bool | None,
    set_default: bool,
) -> dict[str, object]:
    updates: dict[str, object] = {}
    if driver is not None:
        updates["driver"] = driver
    if cdp_url is not None:
        updates["cdp_url"] = cdp_url
    if cdp_port is not None:
        updates["cdp_port"] = cdp_port
    if clear_cdp_port:
        updates["cdp_port"] = None
    if user_data_dir is not None:
        updates["user_data_dir"] = user_data_dir
    if attach_only is not None:
        updates["attach_only"] = attach_only
    if set_default:
        updates["set_as_default"] = True
    return updates


def build_cli() -> typer.Typer:
    app = typer.Typer(help="Control browser profiles and page actions.", no_args_is_help=True)
    profile_app = typer.Typer(help="Manage browser profiles.", no_args_is_help=True)
    host_app = typer.Typer(help="Run managed browser host processes.", no_args_is_help=True)
    mcp_app = typer.Typer(help="Run Chrome MCP capability processes.", no_args_is_help=True)

    @app.command("profiles")
    def list_profiles(ctx: typer.Context) -> None:
        container = ensure_container(ctx)
        echo_data(_profiles_payload(container))

    @profile_app.command("create")
    def create_profile(
        ctx: typer.Context,
        name: str = typer.Argument(..., help="Browser profile name."),
        driver: str = typer.Option("managed", "--driver", help="Profile driver."),
        cdp_url: str | None = typer.Option(None, "--cdp-url", help="Explicit CDP URL."),
        cdp_port: int | None = typer.Option(None, "--cdp-port", min=1, help="Explicit CDP port."),
        user_data_dir: str | None = typer.Option(None, "--user-data-dir", help="User data directory."),
        attach_only: bool = typer.Option(False, "--attach-only", help="Mark the profile as attach-only."),
        set_default: bool = typer.Option(False, "--set-default", help="Set the new profile as default."),
    ) -> None:
        container = ensure_container(ctx)
        try:
            system_config = container.browser_profile_admin_service.create_profile(
                name=name,
                driver=driver,
                cdp_url=cdp_url,
                cdp_port=cdp_port,
                user_data_dir=user_data_dir,
                attach_only=attach_only,
                set_as_default=set_default,
            )
        except BrowserValidationError as exc:
            raise typer.BadParameter(str(exc)) from exc
        echo_data(_profiles_payload(container, system_config))

    @profile_app.command("update")
    def update_profile(
        ctx: typer.Context,
        name: str = typer.Argument(..., help="Existing browser profile name."),
        driver: str | None = typer.Option(None, "--driver", help="Profile driver."),
        cdp_url: str | None = typer.Option(
            None,
            "--cdp-url",
            help="Updated CDP URL. Pass an empty string to clear.",
        ),
        cdp_port: int | None = typer.Option(None, "--cdp-port", min=1, help="Updated CDP port."),
        clear_cdp_port: bool = typer.Option(False, "--clear-cdp-port", help="Clear the configured CDP port."),
        user_data_dir: str | None = typer.Option(
            None,
            "--user-data-dir",
            help="Updated user data dir. Pass an empty string to clear.",
        ),
        attach_only: bool | None = typer.Option(
            None,
            "--attach-only/--no-attach-only",
            help="Update attach-only mode.",
        ),
        set_default: bool = typer.Option(False, "--set-default", help="Set this profile as default."),
    ) -> None:
        container = ensure_container(ctx)
        try:
            system_config = container.browser_profile_admin_service.update_profile(
                profile_name=name,
                **_resolve_profile_update_kwargs(
                    driver=driver,
                    cdp_url=cdp_url,
                    cdp_port=cdp_port,
                    clear_cdp_port=clear_cdp_port,
                    user_data_dir=user_data_dir,
                    attach_only=attach_only,
                    set_default=set_default,
                ),
            )
        except BrowserValidationError as exc:
            raise typer.BadParameter(str(exc)) from exc
        echo_data(_profiles_payload(container, system_config))

    @profile_app.command("delete")
    def delete_profile(
        ctx: typer.Context,
        name: str = typer.Argument(..., help="Browser profile name to delete."),
    ) -> None:
        container = ensure_container(ctx)
        try:
            system_config = container.browser_profile_admin_service.delete_profile(
                profile_name=name,
            )
        except BrowserValidationError as exc:
            raise typer.BadParameter(str(exc)) from exc
        echo_data(_profiles_payload(container, system_config))

    @profile_app.command("set-default")
    def set_default_profile(
        ctx: typer.Context,
        name: str = typer.Argument(..., help="Browser profile name to use as default."),
    ) -> None:
        container = ensure_container(ctx)
        try:
            system_config = container.browser_profile_admin_service.set_default_profile(
                profile_name=name,
            )
        except BrowserValidationError as exc:
            raise typer.BadParameter(str(exc)) from exc
        echo_data(_profiles_payload(container, system_config))

    @profile_app.command("diagnose")
    def diagnose_profile(
        ctx: typer.Context,
        name: str = typer.Argument(..., help="Browser profile name to inspect."),
    ) -> None:
        container = ensure_container(ctx)
        try:
            echo_data(build_profile_diagnostics_payload(container, profile_name=name))
        except BrowserValidationError as exc:
            raise typer.BadParameter(str(exc)) from exc

    @host_app.command("run")
    def run_host(
        ctx: typer.Context,
        profile: str | None = typer.Option(None, "--profile", help="Browser profile name."),
        poll_interval_seconds: float = typer.Option(
            5.0,
            "--poll-interval-seconds",
            min=0.1,
            help="Idle wait time between managed browser health cycles.",
        ),
        max_cycles: int | None = typer.Option(
            None,
            "--max-cycles",
            min=1,
            help="Optional maximum health cycles before exiting.",
        ),
    ) -> None:
        container = ensure_container(ctx)
        container.browser_cdp_control.terminate_owned_processes_on_close = True
        resolved_profile = profile or _default_profile(container)
        stop_event = Event()
        previous_sigint = signal.getsignal(signal.SIGINT)
        previous_sigterm = signal.getsignal(signal.SIGTERM)

        def _request_stop(signum, frame) -> None:  # noqa: ANN001
            del signum, frame
            stop_event.set()

        try:
            signal.signal(signal.SIGINT, _request_stop)
            signal.signal(signal.SIGTERM, _request_stop)
            _run_host_loop(
                container,
                profile_name=resolved_profile,
                poll_interval_seconds=poll_interval_seconds,
                max_cycles=max_cycles,
                stop_event=stop_event,
            )
        except BrowserValidationError as exc:
            raise typer.BadParameter(str(exc)) from exc
        finally:
            signal.signal(signal.SIGINT, previous_sigint)
            signal.signal(signal.SIGTERM, previous_sigterm)

    @mcp_app.command("run")
    def run_mcp(
        ctx: typer.Context,
        profile: str | None = typer.Option(None, "--profile", help="Browser profile name."),
        poll_interval_seconds: float = typer.Option(
            5.0,
            "--poll-interval-seconds",
            min=0.1,
            help="Idle wait time between Chrome MCP health cycles.",
        ),
        max_cycles: int | None = typer.Option(
            None,
            "--max-cycles",
            min=1,
            help="Optional maximum health cycles before exiting.",
        ),
    ) -> None:
        container = ensure_container(ctx)
        resolved_profile = profile or _default_profile(container)
        stop_event = Event()
        previous_sigint = signal.getsignal(signal.SIGINT)
        previous_sigterm = signal.getsignal(signal.SIGTERM)

        def _request_stop(signum, frame) -> None:  # noqa: ANN001
            del signum, frame
            stop_event.set()

        try:
            signal.signal(signal.SIGINT, _request_stop)
            signal.signal(signal.SIGTERM, _request_stop)
            _run_mcp_loop(
                container,
                profile_name=resolved_profile,
                poll_interval_seconds=poll_interval_seconds,
                max_cycles=max_cycles,
                stop_event=stop_event,
            )
        except BrowserValidationError as exc:
            raise typer.BadParameter(str(exc)) from exc
        finally:
            signal.signal(signal.SIGINT, previous_sigint)
            signal.signal(signal.SIGTERM, previous_sigterm)

    @app.command("control")
    def execute_control(
        ctx: typer.Context,
        kind: str = typer.Argument(..., help="Control kind."),
        profile: str | None = typer.Option(None, "--profile", help="Browser profile name."),
        target_id: str | None = typer.Option(None, "--target-id", help="Browser tab id."),
        payload: str | None = typer.Option(None, "--payload", help="JSON object payload."),
        timeout_ms: int | None = typer.Option(None, "--timeout-ms", min=1),
    ) -> None:
        container = ensure_container(ctx)
        try:
            result = container.browser_facade.execute(
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
        echo_data(container.browser_result_serializer.serialize(result))

    @app.command("act")
    def execute_page_action(
        ctx: typer.Context,
        kind: str = typer.Argument(..., help="Page action kind."),
        profile: str | None = typer.Option(None, "--profile", help="Browser profile name."),
        target_id: str | None = typer.Option(None, "--target-id", help="Browser tab id."),
        ref: str | None = typer.Option(None, "--ref", help="Element ref."),
        selector: str | None = typer.Option(None, "--selector", help="CSS selector."),
        payload: str | None = typer.Option(None, "--payload", help="JSON object payload."),
        timeout_ms: int | None = typer.Option(None, "--timeout-ms", min=1),
    ) -> None:
        container = ensure_container(ctx)
        try:
            result = container.browser_facade.execute(
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
        echo_data(container.browser_result_serializer.serialize(result))

    app.add_typer(profile_app, name="profile")
    app.add_typer(host_app, name="host")
    app.add_typer(mcp_app, name="mcp")

    return app
