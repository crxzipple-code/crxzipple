from __future__ import annotations

import typer


def exit_error(message: str) -> None:
    typer.secho(message, err=True, fg=typer.colors.RED)
    raise typer.Exit(code=1) from None
