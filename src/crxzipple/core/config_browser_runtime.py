from __future__ import annotations

import os

from crxzipple.core.config_env import env_flag


DEFAULT_BROWSER_CDP_HOST = "127.0.0.1"
DEFAULT_BROWSER_CDP_PORT = 18800
DEFAULT_BROWSER_HEADLESS = False
DEFAULT_BROWSER_START_TIMEOUT_SECONDS = 10
DEFAULT_BROWSER_SANDBOX_DOCKER_IMAGE = "python:3.11-slim"


def load_browser_executable_path() -> str | None:
    return _optional_env_text("APP_BROWSER_EXECUTABLE_PATH")


def load_browser_sandbox_executable_path() -> str | None:
    return _optional_env_text("APP_BROWSER_SANDBOX_EXECUTABLE_PATH")


def load_browser_proxy_base_url() -> str | None:
    return _optional_env_text("APP_BROWSER_PROXY_BASE_URL")


def load_browser_proxy_egress_check_url() -> str | None:
    return _optional_env_text("APP_BROWSER_PROXY_EGRESS_CHECK_URL")


def load_browser_cdp_host() -> str:
    return (
        os.getenv("APP_BROWSER_CDP_HOST", DEFAULT_BROWSER_CDP_HOST).strip()
        or DEFAULT_BROWSER_CDP_HOST
    )


def load_browser_cdp_port() -> int:
    return max(int(os.getenv("APP_BROWSER_CDP_PORT", str(DEFAULT_BROWSER_CDP_PORT))), 1)


def load_browser_headless() -> bool:
    return env_flag("APP_BROWSER_HEADLESS", default=DEFAULT_BROWSER_HEADLESS)


def load_browser_start_timeout_seconds() -> int:
    return max(
        int(
            os.getenv(
                "APP_BROWSER_START_TIMEOUT_SECONDS",
                str(DEFAULT_BROWSER_START_TIMEOUT_SECONDS),
            ),
        ),
        1,
    )


def load_browser_sandbox_docker_image() -> str:
    fallback = os.getenv(
        "APP_SANDBOX_DOCKER_IMAGE",
        DEFAULT_BROWSER_SANDBOX_DOCKER_IMAGE,
    )
    configured = os.getenv("APP_BROWSER_SANDBOX_DOCKER_IMAGE")
    if configured is None:
        return fallback.strip() or DEFAULT_BROWSER_SANDBOX_DOCKER_IMAGE
    return (
        configured.strip()
        or fallback.strip()
        or DEFAULT_BROWSER_SANDBOX_DOCKER_IMAGE
    )


def _optional_env_text(name: str) -> str | None:
    return os.getenv(name, "").strip() or None
