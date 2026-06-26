from __future__ import annotations

from crxzipple.interfaces.runtime_container import AppContainer, AppKey
from crxzipple.modules.authorization.application import AuthorizationApplicationService


def authorization_service(container: AppContainer) -> AuthorizationApplicationService:
    return container.require(AppKey.AUTHORIZATION_SERVICE)


__all__ = ["authorization_service"]
