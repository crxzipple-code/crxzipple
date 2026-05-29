from __future__ import annotations

import typer

from crxzipple.interfaces.runtime_container import (
    AppContainer,
    AppKey,
    AssemblyTarget,
    ensure_typer_runtime_container,
)


def ensure_container(ctx: typer.Context) -> AppContainer:
    return ensure_typer_runtime_container(
        ctx,
        target=AssemblyTarget.CLI_ADMIN,
        key="container",
    )


__all__ = ["AppContainer", "AppKey", "ensure_container"]
