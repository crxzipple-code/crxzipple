from __future__ import annotations

from typing import Any, cast

import typer

from crxzipple.bootstrap import AppContainer, build_container


def ensure_container(ctx: typer.Context) -> AppContainer:
    root = ctx.find_root()
    if root.obj is None:
        root.obj = {}

    payload = cast(dict[str, Any], root.obj)
    container = payload.get("container")
    if container is None:
        container = build_container()
        payload["container"] = container
        root.call_on_close(container.close)

    return cast(AppContainer, container)
