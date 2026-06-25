from __future__ import annotations

import typer

from crxzipple.interfaces.cli.context import AppKey, ensure_container
from crxzipple.interfaces.cli.formatters import echo_data
from crxzipple.modules.browser.domain import BrowserValidationError

from .cli_helpers import _allocations_payload
from .profile_payloads import build_allocation_entry


def register_allocation_commands(allocation_app: typer.Typer) -> None:
    @allocation_app.command("list")
    def list_allocations(ctx: typer.Context) -> None:
        container = ensure_container(ctx)
        echo_data(_allocations_payload(container))

    @allocation_app.command("allocate")
    def allocate_profile(
        ctx: typer.Context,
        consumer_id: str = typer.Argument(..., help="Allocation consumer id."),
        consumer_kind: str = typer.Option(
            "manual", "--consumer-kind", help="Consumer kind."
        ),
        pool_id: str | None = typer.Option(
            None, "--pool", help="Browser profile pool id."
        ),
        profile_name: str | None = typer.Option(
            None, "--profile", help="Explicit browser profile."
        ),
        target_host: str | None = typer.Option(
            None, "--target-host", help="Target host."
        ),
    ) -> None:
        container = ensure_container(ctx)
        try:
            allocation = container.require(
                AppKey.BROWSER_PROFILE_ALLOCATOR_SERVICE
            ).allocate(
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
        failed: bool = typer.Option(
            False, "--failed", help="Mark allocation as failed."
        ),
        keep_targets: bool = typer.Option(
            False,
            "--keep-targets",
            help="Do not close browser targets owned by this allocation.",
        ),
    ) -> None:
        container = ensure_container(ctx)
        try:
            allocation = container.require(
                AppKey.BROWSER_PROFILE_ALLOCATOR_SERVICE
            ).release_allocation(
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
        ttl_seconds: int | None = typer.Option(
            None, "--ttl-seconds", help="Extend lease TTL."
        ),
    ) -> None:
        container = ensure_container(ctx)
        try:
            allocation = container.require(
                AppKey.BROWSER_PROFILE_ALLOCATOR_SERVICE
            ).heartbeat_allocation(
                allocation_id=allocation_id,
                ttl_seconds=ttl_seconds,
            )
        except BrowserValidationError as exc:
            raise typer.BadParameter(str(exc)) from exc
        echo_data({"allocation": build_allocation_entry(allocation)})

    @allocation_app.command("reconcile")
    def reconcile_allocation(
        ctx: typer.Context,
        allocation_id: str | None = typer.Argument(
            None, help="Allocation id. Omit to reconcile all active allocations."
        ),
    ) -> None:
        container = ensure_container(ctx)
        try:
            if allocation_id is None:
                allocations = container.require(
                    AppKey.BROWSER_PROFILE_ALLOCATOR_SERVICE
                ).reconcile_allocations()
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
            allocation = container.require(
                AppKey.BROWSER_PROFILE_ALLOCATOR_SERVICE
            ).reconcile_allocation(
                allocation_id=allocation_id,
            )
        except BrowserValidationError as exc:
            raise typer.BadParameter(str(exc)) from exc
        echo_data({"allocation": build_allocation_entry(allocation)})
