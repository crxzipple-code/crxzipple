from __future__ import annotations

from typing import cast

from fastapi import Request

from crxzipple.interfaces.runtime_container import AppContainer


def get_container(request: Request) -> AppContainer:
    return cast(AppContainer, request.app.state.container)
