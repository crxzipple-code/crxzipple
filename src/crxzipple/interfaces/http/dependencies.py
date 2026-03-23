from __future__ import annotations

from typing import cast

from fastapi import Request

from crxzipple.bootstrap import AppContainer


def get_container(request: Request) -> AppContainer:
    return cast(AppContainer, request.app.state.container)

