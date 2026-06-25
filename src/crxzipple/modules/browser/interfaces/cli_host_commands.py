from __future__ import annotations

import signal
from threading import Event

import typer

from crxzipple.interfaces.cli.context import ensure_container
from crxzipple.modules.browser.domain import BrowserValidationError

from .cli_helpers import _close_container, _default_profile
from .cli_host_runtime import _run_host_loop


def register_host_commands(host_app: typer.Typer) -> None:
    @host_app.command("run")
    def run_host(
        ctx: typer.Context,
        profile: str | None = typer.Option(
            None, "--profile", help="Browser profile name."
        ),
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
            _close_container(container)
