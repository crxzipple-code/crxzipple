from __future__ import annotations

import json
import signal
from threading import Event
from typing import Any

import typer

from crxzipple.interfaces.cli.context import AppKey, ensure_container
from crxzipple.interfaces.cli.formatters import echo_data
from crxzipple.modules.browser.domain import BrowserValidationError
from crxzipple.modules.browser.infrastructure import BrowserHostProcessRunner

from .profile_payloads import build_allocation_entry
from .profile_payloads import build_allocations_payload
from .profile_payloads import build_pool_entry
from .profile_payloads import build_pools_payload
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
    return container.require(AppKey.BROWSER_SYSTEM_CONFIG_STORE).load().default_profile


def _system_config(container):  # noqa: ANN001
    return container.require(AppKey.BROWSER_SYSTEM_CONFIG_STORE).load()


def _profiles_payload(container, system_config=None) -> dict[str, object]:  # noqa: ANN001
    return build_profiles_payload(container, system_config=system_config)


def _pools_payload(container) -> dict[str, object]:  # noqa: ANN001
    return build_pools_payload(container)


def _allocations_payload(container) -> dict[str, object]:  # noqa: ANN001
    return build_allocations_payload(container)


def _execute_control_payload(container, *, profile_name: str, kind: str) -> dict[str, Any]:  # noqa: ANN001
    result = container.require(AppKey.BROWSER_FACADE).execute(
        BrowserControlRequest(
            profile_name=profile_name,
            kind=kind,
        ),
    )
    return container.require(AppKey.BROWSER_RESULT_SERIALIZER).serialize(result)


def _run_host_loop(
    container,  # noqa: ANN001
    *,
    profile_name: str,
    poll_interval_seconds: float,
    max_cycles: int | None = None,
    stop_event: Event | None = None,
) -> int:
    system_config = _system_config(container)
    browser = container.require(AppKey.BROWSER_INFRASTRUCTURE)
    resolved = browser.profile_resolver.resolve(
        system=system_config,
        profile_name=profile_name,
    )
    capabilities = browser.capabilities_resolver.resolve(profile=resolved)
    runner = BrowserHostProcessRunner(
        daemon_service=container.require(AppKey.DAEMON_SERVICE),
        system=system_config,
        profile=resolved,
        capabilities=capabilities,
        profiles_root=browser.state_root.profiles_dir,
        credential_provider=container.require(AppKey.ACCESS_SERVICE),
        proxy_egress_check_url=getattr(
            container.require(AppKey.CORE_SETTINGS),
            "browser_proxy_egress_check_url",
            None,
        ),
    )
    completed_cycles = 0
    stopper = stop_event or Event()
    try:
        runner.start()
        while not stopper.is_set():
            runner.healthcheck()
            completed_cycles += 1
            if max_cycles is not None and completed_cycles >= max_cycles:
                break
            stopper.wait(poll_interval_seconds)
        return completed_cycles
    finally:
        runner.close()


def _close_container(container) -> None:  # noqa: ANN001
    close = getattr(container, "close", None)
    if callable(close):
        close()


def _resolve_profile_update_kwargs(
    *,
    driver: str | None,
    enabled: bool | None,
    cdp_url: str | None,
    cdp_port: int | None,
    clear_cdp_port: bool,
    user_data_dir: str | None,
    profile_directory: str | None,
    attach_only: bool | None,
    autostart: bool | None,
    proxy_mode: str | None,
    proxy_server: str | None,
    proxy_bypass_list: tuple[str, ...],
    clear_proxy_bypass_list: bool,
    proxy_binding_id: str | None,
    proxy_credential_kind: str | None,
    close_targets_on_release: bool | None,
    close_targets_on_expire: bool | None,
    set_default: bool,
) -> dict[str, object]:
    updates: dict[str, object] = {}
    if driver is not None:
        updates["driver"] = driver
    if enabled is not None:
        updates["enabled"] = enabled
    if cdp_url is not None:
        updates["cdp_url"] = cdp_url
    if cdp_port is not None:
        updates["cdp_port"] = cdp_port
    if clear_cdp_port:
        updates["cdp_port"] = None
    if user_data_dir is not None:
        updates["user_data_dir"] = user_data_dir
    if profile_directory is not None:
        updates["profile_directory"] = profile_directory
    if attach_only is not None:
        updates["attach_only"] = attach_only
    if autostart is not None:
        updates["autostart"] = autostart
    if proxy_mode is not None:
        updates["proxy_mode"] = proxy_mode
    if proxy_server is not None:
        updates["proxy_server"] = proxy_server
    if proxy_bypass_list:
        updates["proxy_bypass_list"] = proxy_bypass_list
    if clear_proxy_bypass_list:
        updates["proxy_bypass_list"] = ()
    if proxy_binding_id is not None:
        updates["proxy_binding_id"] = proxy_binding_id
    if proxy_credential_kind is not None:
        updates["proxy_credential_kind"] = proxy_credential_kind
    if close_targets_on_release is not None:
        updates["close_targets_on_release"] = close_targets_on_release
    if close_targets_on_expire is not None:
        updates["close_targets_on_expire"] = close_targets_on_expire
    if set_default:
        updates["set_as_default"] = True
    return updates


def build_cli() -> typer.Typer:
    app = typer.Typer(help="Control browser profiles and page actions.", no_args_is_help=True)
    profile_app = typer.Typer(help="Manage browser profiles.", no_args_is_help=True)
    pool_app = typer.Typer(help="Manage browser profile pools.", no_args_is_help=True)
    allocation_app = typer.Typer(help="Manage browser profile allocations.", no_args_is_help=True)
    host_app = typer.Typer(help="Run managed browser host processes.", no_args_is_help=True)

    @app.command("profiles")
    def list_profiles(ctx: typer.Context) -> None:
        container = ensure_container(ctx)
        echo_data(_profiles_payload(container))

    @profile_app.command("create")
    def create_profile(
        ctx: typer.Context,
        name: str = typer.Argument(..., help="Browser profile name."),
        driver: str = typer.Option("managed", "--driver", help="Profile driver."),
        enabled: bool = typer.Option(True, "--enabled/--disabled", help="Enable this profile."),
        cdp_url: str | None = typer.Option(None, "--cdp-url", help="Explicit CDP URL."),
        cdp_port: int | None = typer.Option(None, "--cdp-port", min=1, help="Explicit CDP port."),
        user_data_dir: str | None = typer.Option(None, "--user-data-dir", help="User data directory."),
        profile_directory: str | None = typer.Option(
            None,
            "--profile-directory",
            help="Browser profile directory, for example Default or Profile 1.",
        ),
        attach_only: bool = typer.Option(False, "--attach-only", help="Mark the profile as attach-only."),
        autostart: bool = typer.Option(True, "--autostart/--no-autostart", help="Autostart this managed profile."),
        proxy_mode: str = typer.Option("none", "--proxy-mode", help="Proxy mode: none, static, access_binding."),
        proxy_server: str | None = typer.Option(None, "--proxy-server", help="Proxy server URL for static proxy mode."),
        proxy_bypass_list: list[str] = typer.Option(
            [],
            "--proxy-bypass",
            help="Proxy bypass entry. Can be provided multiple times.",
        ),
        proxy_binding_id: str | None = typer.Option(None, "--proxy-binding-id", help="Access binding for proxy credentials."),
        proxy_credential_kind: str = typer.Option("basic", "--proxy-credential-kind", help="Proxy credential kind: basic or bearer_token."),
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
        set_default: bool = typer.Option(False, "--set-default", help="Set the new profile as default."),
    ) -> None:
        container = ensure_container(ctx)
        try:
            system_config = container.require(AppKey.BROWSER_PROFILE_ADMIN_SERVICE).create_profile(
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
        cdp_port: int | None = typer.Option(None, "--cdp-port", min=1, help="Updated CDP port."),
        clear_cdp_port: bool = typer.Option(False, "--clear-cdp-port", help="Clear the configured CDP port."),
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
        proxy_mode: str | None = typer.Option(None, "--proxy-mode", help="Proxy mode: none, static, access_binding."),
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
        set_default: bool = typer.Option(False, "--set-default", help="Set this profile as default."),
    ) -> None:
        container = ensure_container(ctx)
        try:
            system_config = container.require(AppKey.BROWSER_PROFILE_ADMIN_SERVICE).update_profile(
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
            system_config = container.require(AppKey.BROWSER_PROFILE_ADMIN_SERVICE).enable_profile(
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
            system_config = container.require(AppKey.BROWSER_PROFILE_ADMIN_SERVICE).disable_profile(
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
            system_config = container.require(AppKey.BROWSER_PROFILE_ADMIN_SERVICE).delete_profile(
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
            system_config = container.require(AppKey.BROWSER_PROFILE_ADMIN_SERVICE).set_default_profile(
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
            echo_data(_execute_control_payload(container, profile_name=name, kind="start"))
        except BrowserValidationError as exc:
            raise typer.BadParameter(str(exc)) from exc

    @profile_app.command("stop")
    def stop_profile(
        ctx: typer.Context,
        name: str = typer.Argument(..., help="Browser profile name."),
    ) -> None:
        container = ensure_container(ctx)
        try:
            echo_data(_execute_control_payload(container, profile_name=name, kind="stop"))
        except BrowserValidationError as exc:
            raise typer.BadParameter(str(exc)) from exc

    @profile_app.command("restart")
    def restart_profile(
        ctx: typer.Context,
        name: str = typer.Argument(..., help="Browser profile name."),
    ) -> None:
        container = ensure_container(ctx)
        try:
            stopped = _execute_control_payload(container, profile_name=name, kind="stop")
            started = _execute_control_payload(container, profile_name=name, kind="start")
        except BrowserValidationError as exc:
            raise typer.BadParameter(str(exc)) from exc
        echo_data({"profile": name.strip().lower(), "stopped": stopped, "started": started})

    @pool_app.command("list")
    def list_pools(ctx: typer.Context) -> None:
        container = ensure_container(ctx)
        echo_data(_pools_payload(container))

    @pool_app.command("show")
    def show_pool(
        ctx: typer.Context,
        pool_id: str = typer.Argument(..., help="Browser profile pool id."),
    ) -> None:
        container = ensure_container(ctx)
        try:
            pool = container.require(AppKey.BROWSER_PROFILE_POOL_SERVICE).get_pool(
                pool_id=pool_id,
            )
        except BrowserValidationError as exc:
            raise typer.BadParameter(str(exc)) from exc
        echo_data(
            {
                "pool": build_pool_entry(
                    container,
                    pool=pool,
                    system_config=_system_config(container),
                ),
            }
        )

    @pool_app.command("create")
    def create_pool(
        ctx: typer.Context,
        pool_id: str = typer.Argument(..., help="Browser profile pool id."),
        profile: list[str] = typer.Option(
            [],
            "--profile",
            help="Profile name to include. Can be provided multiple times.",
        ),
        target_host: list[str] = typer.Option(
            [],
            "--target-host",
            help="Target host this pool is intended for. Can be provided multiple times.",
        ),
        display_name: str | None = typer.Option(None, "--display-name", help="Display name."),
        enabled: bool = typer.Option(True, "--enabled/--disabled", help="Enable this pool."),
        selection_strategy: str = typer.Option(
            "least_busy",
            "--strategy",
            help="Selection strategy: least_busy, round_robin, sticky_session, manual_only.",
        ),
        max_concurrency_per_profile: int = typer.Option(
            1,
            "--max-per-profile",
            min=1,
            help="Maximum concurrent allocations per profile.",
        ),
        max_concurrency_total: int | None = typer.Option(
            None,
            "--max-total",
            min=1,
            help="Optional maximum concurrent allocations for the pool.",
        ),
        allocation_ttl_seconds: int = typer.Option(
            900,
            "--allocation-ttl-seconds",
            min=1,
            help="Allocation lease TTL.",
        ),
        cooldown_seconds: int = typer.Option(
            0,
            "--cooldown-seconds",
            min=0,
            help="Cooldown after allocation release.",
        ),
        failure_cooldown_seconds: int = typer.Option(
            300,
            "--failure-cooldown-seconds",
            min=0,
            help="Cooldown after profile allocation failure.",
        ),
        allow_attach_only: bool = typer.Option(
            False,
            "--allow-attach-only",
            help="Allow attach-only/existing-session profiles in this pool.",
        ),
        close_targets_on_release: bool = typer.Option(
            True,
            "--close-targets-on-release/--keep-targets-on-release",
            help="Close allocation-owned tabs when a lease from this pool is released.",
        ),
        close_targets_on_expire: bool = typer.Option(
            True,
            "--close-targets-on-expire/--keep-targets-on-expire",
            help="Close allocation-owned tabs when a lease from this pool expires.",
        ),
    ) -> None:
        container = ensure_container(ctx)
        try:
            container.require(AppKey.BROWSER_PROFILE_POOL_SERVICE).create_pool(
                pool_id=pool_id,
                display_name=display_name,
                enabled=enabled,
                profile_names=tuple(profile),
                target_hosts=tuple(target_host),
                selection_strategy=selection_strategy,
                max_concurrency_per_profile=max_concurrency_per_profile,
                max_concurrency_total=max_concurrency_total,
                allocation_ttl_seconds=allocation_ttl_seconds,
                cooldown_seconds=cooldown_seconds,
                failure_cooldown_seconds=failure_cooldown_seconds,
                allow_attach_only=allow_attach_only,
                close_targets_on_release=close_targets_on_release,
                close_targets_on_expire=close_targets_on_expire,
            )
        except BrowserValidationError as exc:
            raise typer.BadParameter(str(exc)) from exc
        echo_data(_pools_payload(container))

    @pool_app.command("update")
    def update_pool(
        ctx: typer.Context,
        pool_id: str = typer.Argument(..., help="Browser profile pool id."),
        profile: list[str] = typer.Option(
            [],
            "--profile",
            help="Replace profiles. Can be provided multiple times.",
        ),
        target_host: list[str] = typer.Option(
            [],
            "--target-host",
            help="Replace target hosts. Can be provided multiple times.",
        ),
        display_name: str | None = typer.Option(None, "--display-name", help="Display name."),
        clear_display_name: bool = typer.Option(False, "--clear-display-name"),
        enabled: bool | None = typer.Option(None, "--enabled/--disabled"),
        selection_strategy: str | None = typer.Option(None, "--strategy"),
        max_concurrency_per_profile: int | None = typer.Option(
            None,
            "--max-per-profile",
            min=1,
        ),
        max_concurrency_total: int | None = typer.Option(
            None,
            "--max-total",
            min=1,
        ),
        clear_max_concurrency_total: bool = typer.Option(False, "--clear-max-total"),
        allocation_ttl_seconds: int | None = typer.Option(
            None,
            "--allocation-ttl-seconds",
            min=1,
        ),
        cooldown_seconds: int | None = typer.Option(
            None,
            "--cooldown-seconds",
            min=0,
        ),
        failure_cooldown_seconds: int | None = typer.Option(
            None,
            "--failure-cooldown-seconds",
            min=0,
        ),
        allow_attach_only: bool | None = typer.Option(
            None,
            "--allow-attach-only/--reject-attach-only",
        ),
        close_targets_on_release: bool | None = typer.Option(
            None,
            "--close-targets-on-release/--keep-targets-on-release",
        ),
        close_targets_on_expire: bool | None = typer.Option(
            None,
            "--close-targets-on-expire/--keep-targets-on-expire",
        ),
    ) -> None:
        container = ensure_container(ctx)
        updates: dict[str, object] = {}
        if display_name is not None:
            updates["display_name"] = display_name
        if clear_display_name:
            updates["display_name"] = None
        if enabled is not None:
            updates["enabled"] = enabled
        if profile:
            updates["profile_names"] = tuple(profile)
        if target_host:
            updates["target_hosts"] = tuple(target_host)
        if selection_strategy is not None:
            updates["selection_strategy"] = selection_strategy
        if max_concurrency_per_profile is not None:
            updates["max_concurrency_per_profile"] = max_concurrency_per_profile
        if max_concurrency_total is not None:
            updates["max_concurrency_total"] = max_concurrency_total
        if clear_max_concurrency_total:
            updates["max_concurrency_total"] = None
        if allocation_ttl_seconds is not None:
            updates["allocation_ttl_seconds"] = allocation_ttl_seconds
        if cooldown_seconds is not None:
            updates["cooldown_seconds"] = cooldown_seconds
        if failure_cooldown_seconds is not None:
            updates["failure_cooldown_seconds"] = failure_cooldown_seconds
        if allow_attach_only is not None:
            updates["allow_attach_only"] = allow_attach_only
        if close_targets_on_release is not None:
            updates["close_targets_on_release"] = close_targets_on_release
        if close_targets_on_expire is not None:
            updates["close_targets_on_expire"] = close_targets_on_expire
        try:
            container.require(AppKey.BROWSER_PROFILE_POOL_SERVICE).update_pool(
                pool_id=pool_id,
                **updates,
            )
        except BrowserValidationError as exc:
            raise typer.BadParameter(str(exc)) from exc
        echo_data(_pools_payload(container))

    @pool_app.command("enable")
    def enable_pool(
        ctx: typer.Context,
        pool_id: str = typer.Argument(..., help="Browser profile pool id."),
    ) -> None:
        container = ensure_container(ctx)
        try:
            container.require(AppKey.BROWSER_PROFILE_POOL_SERVICE).enable_pool(
                pool_id=pool_id,
            )
        except BrowserValidationError as exc:
            raise typer.BadParameter(str(exc)) from exc
        echo_data(_pools_payload(container))

    @pool_app.command("disable")
    def disable_pool(
        ctx: typer.Context,
        pool_id: str = typer.Argument(..., help="Browser profile pool id."),
    ) -> None:
        container = ensure_container(ctx)
        try:
            container.require(AppKey.BROWSER_PROFILE_POOL_SERVICE).disable_pool(
                pool_id=pool_id,
            )
        except BrowserValidationError as exc:
            raise typer.BadParameter(str(exc)) from exc
        echo_data(_pools_payload(container))

    @pool_app.command("delete")
    def delete_pool(
        ctx: typer.Context,
        pool_id: str = typer.Argument(..., help="Browser profile pool id."),
    ) -> None:
        container = ensure_container(ctx)
        try:
            container.require(AppKey.BROWSER_PROFILE_POOL_SERVICE).delete_pool(
                pool_id=pool_id,
            )
        except BrowserValidationError as exc:
            raise typer.BadParameter(str(exc)) from exc
        echo_data(_pools_payload(container))

    @pool_app.command("drain")
    def drain_pool(
        ctx: typer.Context,
        pool_id: str = typer.Argument(..., help="Browser profile pool id."),
    ) -> None:
        container = ensure_container(ctx)
        try:
            drained = container.require(AppKey.BROWSER_PROFILE_ALLOCATOR_SERVICE).drain_pool(
                pool_id=pool_id,
            )
        except BrowserValidationError as exc:
            raise typer.BadParameter(str(exc)) from exc
        echo_data(
            {
                "pool_id": pool_id.strip().lower(),
                "released": len(drained),
                "allocations": [
                    build_allocation_entry(allocation)
                    for allocation in drained
                ],
            }
        )

    @allocation_app.command("list")
    def list_allocations(ctx: typer.Context) -> None:
        container = ensure_container(ctx)
        echo_data(_allocations_payload(container))

    @allocation_app.command("allocate")
    def allocate_profile(
        ctx: typer.Context,
        consumer_id: str = typer.Argument(..., help="Allocation consumer id."),
        consumer_kind: str = typer.Option("manual", "--consumer-kind", help="Consumer kind."),
        pool_id: str | None = typer.Option(None, "--pool", help="Browser profile pool id."),
        profile_name: str | None = typer.Option(None, "--profile", help="Explicit browser profile."),
        target_host: str | None = typer.Option(None, "--target-host", help="Target host."),
    ) -> None:
        container = ensure_container(ctx)
        try:
            allocation = container.require(AppKey.BROWSER_PROFILE_ALLOCATOR_SERVICE).allocate(
                consumer_kind=consumer_kind,
                consumer_id=consumer_id,
                pool_id=pool_id,
                profile_name=profile_name,
                target_host=target_host,
            )
        except BrowserValidationError as exc:
            raise typer.BadParameter(str(exc)) from exc
        echo_data({"allocation": build_allocation_entry(allocation)})

    @allocation_app.command("release")
    def release_allocation(
        ctx: typer.Context,
        allocation_id: str = typer.Argument(..., help="Allocation id."),
        reason: str = typer.Option("released", "--reason", help="Release reason."),
        failed: bool = typer.Option(False, "--failed", help="Mark allocation as failed."),
        keep_targets: bool = typer.Option(
            False,
            "--keep-targets",
            help="Do not close browser targets owned by this allocation.",
        ),
    ) -> None:
        container = ensure_container(ctx)
        try:
            allocation = container.require(AppKey.BROWSER_PROFILE_ALLOCATOR_SERVICE).release_allocation(
                allocation_id=allocation_id,
                reason=reason,
                failed=failed,
                recycle_targets=not keep_targets,
            )
        except BrowserValidationError as exc:
            raise typer.BadParameter(str(exc)) from exc
        echo_data({"allocation": build_allocation_entry(allocation)})

    @allocation_app.command("heartbeat")
    def heartbeat_allocation(
        ctx: typer.Context,
        allocation_id: str = typer.Argument(..., help="Allocation id."),
        ttl_seconds: int | None = typer.Option(None, "--ttl-seconds", help="Extend lease TTL."),
    ) -> None:
        container = ensure_container(ctx)
        try:
            allocation = container.require(AppKey.BROWSER_PROFILE_ALLOCATOR_SERVICE).heartbeat_allocation(
                allocation_id=allocation_id,
                ttl_seconds=ttl_seconds,
            )
        except BrowserValidationError as exc:
            raise typer.BadParameter(str(exc)) from exc
        echo_data({"allocation": build_allocation_entry(allocation)})

    @allocation_app.command("reconcile")
    def reconcile_allocation(
        ctx: typer.Context,
        allocation_id: str | None = typer.Argument(None, help="Allocation id. Omit to reconcile all active allocations."),
    ) -> None:
        container = ensure_container(ctx)
        try:
            if allocation_id is None:
                allocations = container.require(AppKey.BROWSER_PROFILE_ALLOCATOR_SERVICE).reconcile_allocations()
                echo_data(
                    {
                        "reconciled": len(allocations),
                        "allocations": [
                            build_allocation_entry(allocation)
                            for allocation in allocations
                        ],
                    },
                )
                return
            allocation = container.require(AppKey.BROWSER_PROFILE_ALLOCATOR_SERVICE).reconcile_allocation(
                allocation_id=allocation_id,
            )
        except BrowserValidationError as exc:
            raise typer.BadParameter(str(exc)) from exc
        echo_data({"allocation": build_allocation_entry(allocation)})

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
        profile: str | None = typer.Option(None, "--profile", help="Browser profile name."),
        target_id: str | None = typer.Option(None, "--target-id", help="Browser tab id."),
        ref: str | None = typer.Option(None, "--ref", help="Element ref."),
        selector: str | None = typer.Option(None, "--selector", help="CSS selector."),
        payload: str | None = typer.Option(None, "--payload", help="JSON object payload."),
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

    app.add_typer(profile_app, name="profile")
    app.add_typer(pool_app, name="pool")
    app.add_typer(allocation_app, name="allocation")
    app.add_typer(host_app, name="host")

    return app
