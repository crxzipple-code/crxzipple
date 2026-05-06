from __future__ import annotations

from contextlib import asynccontextmanager
from time import perf_counter
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi import Request
from fastapi.responses import JSONResponse

from crxzipple.bootstrap import AppContainer, build_container
from crxzipple.core.config import Settings, load_settings
from crxzipple.core.logger import configure_logging, get_logger
from crxzipple.interfaces.http.router import api_router
from crxzipple.modules.authorization.domain import AuthorizationDeniedError
from crxzipple.shared.infrastructure.event_bus import EventBus
from crxzipple.shared.infrastructure.http import install_json_exception_handler

logger = get_logger(__name__)


@asynccontextmanager
async def _container_lifespan(
    app: FastAPI,
    *,
    manage_container_lifecycle: bool,
) -> AsyncIterator[None]:
    try:
        yield
    finally:
        if manage_container_lifecycle:
            app.state.container.close()


def create_app(
    *,
    settings: Settings | None = None,
    database_url: str | None = None,
    event_bus: EventBus | None = None,
    container: AppContainer | None = None,
    manage_container_lifecycle: bool = True,
) -> FastAPI:
    if settings is not None:
        resolved_settings = settings
    elif container is not None:
        resolved_settings = container.settings
    else:
        resolved_settings = load_settings()
    configure_logging(resolved_settings)
    app = FastAPI(
        title=resolved_settings.app_name,
        lifespan=lambda app: _container_lifespan(
            app,
            manage_container_lifecycle=manage_container_lifecycle,
        ),
    )
    app.state.container = container or build_container(
        settings=resolved_settings,
        database_url=database_url,
        event_bus=event_bus,
        enable_memory_watchers=True,
    )
    install_json_exception_handler(app, logger=logger)

    @app.exception_handler(AuthorizationDeniedError)
    async def handle_authorization_denied(
        request: Request,
        exc: AuthorizationDeniedError,
    ) -> JSONResponse:
        logger.warning(
            "authorization denied for HTTP request",
            extra={
                "method": request.method,
                "path": request.url.path,
                "reason": str(exc),
            },
        )
        return JSONResponse(
            status_code=403,
            content={"detail": str(exc)},
        )

    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        started = perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            duration_ms = (perf_counter() - started) * 1000
            logger.exception(
                "HTTP %s %s failed in %.2fms",
                request.method,
                request.url.path,
                duration_ms,
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "duration_ms": round(duration_ms, 2),
                },
            )
            raise

        duration_ms = (perf_counter() - started) * 1000
        logger.info(
            "HTTP %s %s -> %s in %.2fms",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
            extra={
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": round(duration_ms, 2),
            },
        )
        return response

    app.include_router(api_router)
    logger.info(
        "http app initialized",
        extra={
            "app_name": resolved_settings.app_name,
            "environment": resolved_settings.environment,
        },
    )
    return app


app = create_app()


def run() -> None:
    import uvicorn

    uvicorn.run("crxzipple.interfaces.http.app:app", host="127.0.0.1", port=8000)
