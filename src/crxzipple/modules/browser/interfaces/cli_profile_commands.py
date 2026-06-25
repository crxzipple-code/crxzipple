from __future__ import annotations

import typer

from crxzipple.interfaces.cli.context import AppKey, ensure_container
from crxzipple.interfaces.cli.formatters import echo_data
from crxzipple.modules.browser.domain import BrowserValidationError

from .cli_helpers import (
    _execute_control_payload,
    _profiles_payload,
    _resolve_profile_update_kwargs,
)
from .profile_payloads import build_profile_diagnostics_payload


def register_profile_commands(app: typer.Typer, profile_app: typer.Typer) -> None:
    @app.command("profiles")
    def list_profiles(ctx: typer.Context) -> None:
        container = ensure_container(ctx)
        echo_data(_profiles_payload(container))

    @profile_app.command("create")
    def create_profile(
        ctx: typer.Context,
        name: str = typer.Argument(..., help="Browser profile name."),
        driver: str = typer.Option("managed", "--driver", help="Profile driver."),
        enabled: bool = typer.Option(
            True, "--enabled/--disabled", help="Enable this profile."
        ),
        cdp_url: str | None = typer.Option(None, "--cdp-url", help="Explicit CDP URL."),
        cdp_port: int | None = typer.Option(
            None, "--cdp-port", min=1, help="Explicit CDP port."
        ),
        user_data_dir: str | None = typer.Option(
            None, "--user-data-dir", help="User data directory."
        ),
        profile_directory: str | None = typer.Option(
            None,
            "--profile-directory",
            help="Browser profile directory, for example Default or Profile 1.",
        ),
        attach_only: bool = typer.Option(
            False, "--attach-only", help="Mark the profile as attach-only."
        ),
        autostart: bool = typer.Option(
            True, "--autostart/--no-autostart", help="Autostart this managed profile."
        ),
        proxy_mode: str = typer.Option(
            "none", "--proxy-mode", help="Proxy mode: none, static, access_binding."
        ),
        proxy_server: str | None = typer.Option(
            None, "--proxy-server", help="Proxy server URL for static proxy mode."
        ),
        proxy_bypass_list: list[str] = typer.Option(
            [],
            "--proxy-bypass",
            help="Proxy bypass entry. Can be provided multiple times.",
        ),
        proxy_binding_id: str | None = typer.Option(
            None, "--proxy-binding-id", help="Access binding for proxy credentials."
        ),
        proxy_credential_kind: str = typer.Option(
            "basic",
            "--proxy-credential-kind",
            help="Proxy credential kind: basic or bearer_token.",
        ),
        close_targets_on_release: bool = typer.Option(
            True,
            "--close-targets-on-release/--keep-targets-on-release",
            help="Close allocation-owned tabs when the lease is released.",
        ),
        close_targets_on_expire: bool = typer.Option(
            True,
            "--close-targets-on-expire/--keep-targets-on-expire",
            help="Close allocation-owned tabs when the lease expires.",
        ),
        set_default: bool = typer.Option(
            False, "--set-default", help="Set the new profile as default."
        ),
    ) -> None:
        container = ensure_container(ctx)
        try:
            system_config = container.require(
                AppKey.BROWSER_PROFILE_ADMIN_SERVICE
            ).create_profile(
                name=name,
                driver=driver,
                enabled=enabled,
                cdp_url=cdp_url,
                cdp_port=cdp_port,
                user_data_dir=user_data_dir,
                profile_directory=profile_directory,
                attach_only=attach_only,
                autostart=autostart,
                proxy_mode=proxy_mode,
                proxy_server=proxy_server,
                proxy_bypass_list=tuple(proxy_bypass_list),
                proxy_binding_id=proxy_binding_id,
                proxy_credential_kind=proxy_credential_kind,
                close_targets_on_release=close_targets_on_release,
                close_targets_on_expire=close_targets_on_expire,
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
        enabled: bool | None = typer.Option(
            None,
            "--enabled/--disabled",
            help="Enable or disable this profile.",
        ),
        cdp_url: str | None = typer.Option(
            None,
            "--cdp-url",
            help="Updated CDP URL. Pass an empty string to clear.",
        ),
        cdp_port: int | None = typer.Option(
            None, "--cdp-port", min=1, help="Updated CDP port."
        ),
        clear_cdp_port: bool = typer.Option(
            False, "--clear-cdp-port", help="Clear the configured CDP port."
        ),
        user_data_dir: str | None = typer.Option(
            None,
            "--user-data-dir",
            help="Updated user data dir. Pass an empty string to clear.",
        ),
        profile_directory: str | None = typer.Option(
            None,
            "--profile-directory",
            help="Updated browser profile directory. Pass an empty string to clear.",
        ),
        attach_only: bool | None = typer.Option(
            None,
            "--attach-only/--no-attach-only",
            help="Update attach-only mode.",
        ),
        autostart: bool | None = typer.Option(
            None,
            "--autostart/--no-autostart",
            help="Update autostart mode.",
        ),
        proxy_mode: str | None = typer.Option(
            None, "--proxy-mode", help="Proxy mode: none, static, access_binding."
        ),
        proxy_server: str | None = typer.Option(
            None,
            "--proxy-server",
            help="Updated proxy server. Pass an empty string to clear.",
        ),
        proxy_bypass_list: list[str] = typer.Option(
            [],
            "--proxy-bypass",
            help="Proxy bypass entry. Can be provided multiple times.",
        ),
        clear_proxy_bypass_list: bool = typer.Option(
            False,
            "--clear-proxy-bypass",
            help="Clear proxy bypass entries.",
        ),
        proxy_binding_id: str | None = typer.Option(
            None,
            "--proxy-binding-id",
            help="Updated Access binding id for proxy credentials. Pass an empty string to clear.",
        ),
        proxy_credential_kind: str | None = typer.Option(
            None,
            "--proxy-credential-kind",
            help="Updated proxy credential kind: basic or bearer_token.",
        ),
        close_targets_on_release: bool | None = typer.Option(
            None,
            "--close-targets-on-release/--keep-targets-on-release",
            help="Update release cleanup policy.",
        ),
        close_targets_on_expire: bool | None = typer.Option(
            None,
            "--close-targets-on-expire/--keep-targets-on-expire",
            help="Update expiry cleanup policy.",
        ),
        set_default: bool = typer.Option(
            False, "--set-default", help="Set this profile as default."
        ),
    ) -> None:
        container = ensure_container(ctx)
        try:
            system_config = container.require(
                AppKey.BROWSER_PROFILE_ADMIN_SERVICE
            ).update_profile(
                profile_name=name,
                **_resolve_profile_update_kwargs(
                    driver=driver,
                    enabled=enabled,
                    cdp_url=cdp_url,
                    cdp_port=cdp_port,
                    clear_cdp_port=clear_cdp_port,
                    user_data_dir=user_data_dir,
                    profile_directory=profile_directory,
                    attach_only=attach_only,
                    autostart=autostart,
                    proxy_mode=proxy_mode,
                    proxy_server=proxy_server,
                    proxy_bypass_list=tuple(proxy_bypass_list),
                    clear_proxy_bypass_list=clear_proxy_bypass_list,
                    proxy_binding_id=proxy_binding_id,
                    proxy_credential_kind=proxy_credential_kind,
                    close_targets_on_release=close_targets_on_release,
                    close_targets_on_expire=close_targets_on_expire,
                    set_default=set_default,
                ),
            )
        except BrowserValidationError as exc:
            raise typer.BadParameter(str(exc)) from exc
        echo_data(_profiles_payload(container, system_config))

    @profile_app.command("enable")
    def enable_profile(
        ctx: typer.Context,
        name: str = typer.Argument(..., help="Browser profile name."),
    ) -> None:
        container = ensure_container(ctx)
        try:
            system_config = container.require(
                AppKey.BROWSER_PROFILE_ADMIN_SERVICE
            ).enable_profile(
                profile_name=name,
            )
        except BrowserValidationError as exc:
            raise typer.BadParameter(str(exc)) from exc
        echo_data(_profiles_payload(container, system_config))

    @profile_app.command("disable")
    def disable_profile(
        ctx: typer.Context,
        name: str = typer.Argument(..., help="Browser profile name."),
    ) -> None:
        container = ensure_container(ctx)
        try:
            system_config = container.require(
                AppKey.BROWSER_PROFILE_ADMIN_SERVICE
            ).disable_profile(
                profile_name=name,
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
            system_config = container.require(
                AppKey.BROWSER_PROFILE_ADMIN_SERVICE
            ).delete_profile(
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
            system_config = container.require(
                AppKey.BROWSER_PROFILE_ADMIN_SERVICE
            ).set_default_profile(
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

    @profile_app.command("start")
    def start_profile(
        ctx: typer.Context,
        name: str = typer.Argument(..., help="Browser profile name."),
    ) -> None:
        container = ensure_container(ctx)
        try:
            echo_data(
                _execute_control_payload(container, profile_name=name, kind="start")
            )
        except BrowserValidationError as exc:
            raise typer.BadParameter(str(exc)) from exc

    @profile_app.command("stop")
    def stop_profile(
        ctx: typer.Context,
        name: str = typer.Argument(..., help="Browser profile name."),
    ) -> None:
        container = ensure_container(ctx)
        try:
            echo_data(
                _execute_control_payload(container, profile_name=name, kind="stop")
            )
        except BrowserValidationError as exc:
            raise typer.BadParameter(str(exc)) from exc

    @profile_app.command("restart")
    def restart_profile(
        ctx: typer.Context,
        name: str = typer.Argument(..., help="Browser profile name."),
    ) -> None:
        container = ensure_container(ctx)
        try:
            stopped = _execute_control_payload(
                container, profile_name=name, kind="stop"
            )
            started = _execute_control_payload(
                container, profile_name=name, kind="start"
            )
        except BrowserValidationError as exc:
            raise typer.BadParameter(str(exc)) from exc
        echo_data(
            {"profile": name.strip().lower(), "stopped": stopped, "started": started}
        )
