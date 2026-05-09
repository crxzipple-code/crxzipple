from __future__ import annotations

import json
import os
import signal
import socket
from threading import Event
from uuid import uuid4

import typer

from crxzipple.bootstrap import build_container
from crxzipple.core.config import load_settings
from crxzipple.core.logger import configure_logging
from crxzipple.interfaces.cli.crxzipple import guard_runtime_database
from crxzipple.interfaces.cli.formatters import echo_data
from crxzipple.modules.channels.application.runtime import ChannelRuntimeBootstrapService
from crxzipple.modules.channels.domain import ChannelProfile, ChannelValidationError


def _resolve_runtime_id(channel: str, runtime_id: str | None) -> str:
    if runtime_id is not None and runtime_id.strip():
        return runtime_id.strip()
    normalized_channel = channel.strip().lower()
    return f"{normalized_channel}-{socket.gethostname()}-{os.getpid()}-{uuid4().hex[:8]}"


def _exit_error(exc: Exception) -> None:
    if isinstance(exc, ChannelValidationError) and exc.has_payload:
        echo_data(exc.to_payload())
        raise typer.Exit(code=1) from None
    typer.secho(str(exc), err=True, fg=typer.colors.RED)
    raise typer.Exit(code=1) from None


def _load_json_object(raw: str | None, option_name: str) -> dict[str, object]:
    if raw is None:
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise typer.BadParameter(
            f"{option_name} must be valid JSON: {exc.msg}",
        ) from exc
    if not isinstance(payload, dict):
        raise typer.BadParameter(f"{option_name} must be a JSON object.")
    return dict(payload)


def _load_account_payloads(raw_accounts: list[str] | None) -> list[dict[str, object]]:
    accounts: list[dict[str, object]] = []
    for raw_account in raw_accounts or ():
        accounts.append(_load_json_object(raw_account, "--account-json"))
    return accounts


def _profile_payload(profile: ChannelProfile) -> dict[str, object]:
    return profile.to_payload()


def build_cli() -> typer.Typer:
    app = typer.Typer(help="Run channel runtime processes.", no_args_is_help=True)

    @app.command("list-profiles")
    def list_profiles() -> None:
        settings = load_settings()
        configure_logging(settings)
        container = build_container(settings=settings)
        try:
            echo_data(
                [
                    _profile_payload(profile)
                    for profile in container.channel_profile_service.list_profiles()
                ],
            )
        finally:
            container.close()

    @app.command("get-profile")
    def get_profile(
        channel: str = typer.Argument(..., help="Channel type."),
    ) -> None:
        settings = load_settings()
        configure_logging(settings)
        container = build_container(settings=settings)
        try:
            profile = container.channel_profile_service.get_profile(channel)
            if profile is None:
                _exit_error(
                    ChannelValidationError(
                        f"channel profile '{channel}' was not found.",
                        code="channel_profile_not_found",
                        details={"channel_type": channel},
                    ),
                )
            echo_data(_profile_payload(profile))
        finally:
            container.close()

    @app.command("upsert-profile")
    def upsert_profile(
        channel: str = typer.Argument(..., help="Channel type."),
        enabled: bool = typer.Option(True, "--enabled/--disabled"),
        capabilities_json: str | None = typer.Option(
            None,
            "--capabilities-json",
            help="Channel capabilities as a JSON object.",
        ),
        account_json: list[str] = typer.Option(
            None,
            "--account-json",
            help="Repeatable account profile JSON object.",
        ),
        metadata_json: str | None = typer.Option(
            None,
            "--metadata-json",
            help="Profile metadata as a JSON object.",
        ),
    ) -> None:
        settings = load_settings()
        configure_logging(settings)
        container = build_container(settings=settings)
        try:
            profile = ChannelProfile.from_payload(
                {
                    "channel_type": channel,
                    "enabled": enabled,
                    "capabilities": _load_json_object(
                        capabilities_json,
                        "--capabilities-json",
                    ),
                    "accounts": _load_account_payloads(account_json),
                    "metadata": _load_json_object(metadata_json, "--metadata-json"),
                },
            )
            saved = container.channel_profile_service.upsert_profile(profile)
            echo_data(_profile_payload(saved))
        except ChannelValidationError as exc:
            _exit_error(exc)
        finally:
            container.close()

    @app.command("enable-profile")
    def enable_profile(
        channel: str = typer.Argument(..., help="Channel type."),
    ) -> None:
        settings = load_settings()
        configure_logging(settings)
        container = build_container(settings=settings)
        try:
            echo_data(
                _profile_payload(container.channel_profile_service.enable_profile(channel)),
            )
        except ChannelValidationError as exc:
            _exit_error(exc)
        finally:
            container.close()

    @app.command("disable-profile")
    def disable_profile(
        channel: str = typer.Argument(..., help="Channel type."),
    ) -> None:
        settings = load_settings()
        configure_logging(settings)
        container = build_container(settings=settings)
        try:
            echo_data(
                _profile_payload(container.channel_profile_service.disable_profile(channel)),
            )
        except ChannelValidationError as exc:
            _exit_error(exc)
        finally:
            container.close()

    @app.command("run")
    def run_runtime(
        channel: str = typer.Option(..., "--channel", help="Channel type to run."),
        service_key: str | None = typer.Option(
            None,
            "--service-key",
            help="Explicit daemon service key for this runtime.",
        ),
        runtime_id: str | None = typer.Option(
            None,
            "--runtime-id",
            help="Explicit runtime identifier.",
        ),
        poll_interval_seconds: float = typer.Option(
            5.0,
            "--poll-interval-seconds",
            min=0.05,
            help="Idle wait time between runtime heartbeats.",
        ),
        max_cycles: int | None = typer.Option(
            None,
            "--max-cycles",
            min=1,
            help="Optional maximum heartbeat cycles before exiting.",
        ),
    ) -> None:
        settings = load_settings()
        guard_runtime_database(settings, runtime_name="channel runtime")
        configure_logging(settings)
        container = build_container(settings=settings)
        stop_event = Event()
        resolved_channel = channel.strip().lower()
        if resolved_channel == "inbox":
            _exit_error(
                ChannelValidationError(
                    "channel 'inbox' has been retired; route inbound traffic directly into orchestration instead.",
                )
            )
        resolved_runtime_id = _resolve_runtime_id(resolved_channel, runtime_id)
        runtime: ChannelRuntimeBootstrapService
        if resolved_channel == "lark":
            runtime = container.lark_channel_runtime_service
        elif resolved_channel == "web":
            runtime = container.web_channel_runtime_service
        elif resolved_channel == "webhook":
            runtime = container.webhook_channel_runtime_service
        else:
            runtime = ChannelRuntimeBootstrapService(
                profile_service=container.channel_profile_service,
                runtime_manager=container.channel_runtime_manager,
            )
        previous_sigint = signal.getsignal(signal.SIGINT)
        previous_sigterm = signal.getsignal(signal.SIGTERM)
        registration = None

        def _request_stop(signum, frame) -> None:  # noqa: ANN001
            stop_event.set()

        signal.signal(signal.SIGINT, _request_stop)
        signal.signal(signal.SIGTERM, _request_stop)

        try:
            resolved_service_key = (
                service_key.strip()
                if isinstance(service_key, str) and service_key.strip()
                else f"channel:{resolved_channel}"
            )
            if resolved_channel in {"web", "webhook", "lark"}:
                registration = runtime.ensure_registered(
                    runtime_id=resolved_runtime_id,
                    service_key=resolved_service_key,
                    metadata={"runtime_mode": "channel-runtime-cli"},
                )
            else:
                registration = runtime.ensure_registered(
                    resolved_channel,
                    runtime_id=resolved_runtime_id,
                    service_key=resolved_service_key,
                    metadata={"runtime_mode": "channel-runtime-cli"},
                )
            echo_data(
                {
                    "status": "running",
                    "channel": resolved_channel,
                    "runtime_id": registration.runtime_id,
                    "service_key": registration.service_key,
                },
            )
            runtime.run_runtime_loop(
                resolved_channel,
                runtime_id=registration.runtime_id,
                service_key=registration.service_key,
                poll_interval_seconds=poll_interval_seconds,
                max_cycles=max_cycles,
                stop_event=stop_event,
                metadata={"runtime_mode": "channel-runtime-cli"},
            )
        except ChannelValidationError as exc:
            _exit_error(exc)
        finally:
            if registration is not None:
                runtime.unregister_runtime(registration.runtime_id)
            signal.signal(signal.SIGINT, previous_sigint)
            signal.signal(signal.SIGTERM, previous_sigterm)
            container.close()

    return app
