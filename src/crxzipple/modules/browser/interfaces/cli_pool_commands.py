from __future__ import annotations

import typer

from crxzipple.interfaces.cli.context import AppKey, ensure_container
from crxzipple.interfaces.cli.formatters import echo_data
from crxzipple.modules.browser.domain import BrowserValidationError

from .cli_helpers import _pools_payload, _system_config
from .profile_payloads import build_allocation_entry, build_pool_entry


def register_pool_commands(pool_app: typer.Typer) -> None:
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
        display_name: str | None = typer.Option(
            None, "--display-name", help="Display name."
        ),
        enabled: bool = typer.Option(
            True, "--enabled/--disabled", help="Enable this pool."
        ),
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
        display_name: str | None = typer.Option(
            None, "--display-name", help="Display name."
        ),
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
            drained = container.require(
                AppKey.BROWSER_PROFILE_ALLOCATOR_SERVICE
            ).drain_pool(
                pool_id=pool_id,
            )
        except BrowserValidationError as exc:
            raise typer.BadParameter(str(exc)) from exc
        echo_data(
            {
                "pool_id": pool_id.strip().lower(),
                "released": len(drained),
                "allocations": [
                    build_allocation_entry(allocation) for allocation in drained
                ],
            }
        )
