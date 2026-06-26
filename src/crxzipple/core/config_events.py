from __future__ import annotations

import os
from typing import Literal

from crxzipple.core.config_env import env_flag


DEFAULT_EVENTS_BACKEND = "redis"
DEFAULT_EVENTS_REDIS_URL = "redis://127.0.0.1:6379/0"
DEFAULT_EVENTS_REDIS_KEY_PREFIX = "crx:events"
DEFAULT_EVENTS_REDIS_BLOCK_MS = 1000
DEFAULT_EVENTS_REDIS_DEDUPE_TTL_SECONDS = 3600


def load_events_backend() -> Literal["file", "redis"]:
    raw = os.getenv("APP_EVENTS_BACKEND", DEFAULT_EVENTS_BACKEND).strip().lower()
    if not raw:
        return DEFAULT_EVENTS_BACKEND
    if raw == "redis":
        return "redis"
    if raw == "file":
        return "file"
    raise ValueError("APP_EVENTS_BACKEND must be one of: file, redis.")


def load_events_file_sync_writes() -> bool:
    return env_flag("APP_EVENTS_FILE_SYNC_WRITES", default=False)


def load_events_redis_url() -> str:
    return (
        os.getenv(
            "APP_EVENTS_REDIS_URL",
            DEFAULT_EVENTS_REDIS_URL,
        ).strip()
        or DEFAULT_EVENTS_REDIS_URL
    )


def load_events_redis_key_prefix() -> str:
    return (
        os.getenv(
            "APP_EVENTS_REDIS_KEY_PREFIX",
            DEFAULT_EVENTS_REDIS_KEY_PREFIX,
        ).strip()
        or DEFAULT_EVENTS_REDIS_KEY_PREFIX
    )


def load_events_redis_block_ms() -> int:
    return max(
        int(
            os.getenv(
                "APP_EVENTS_REDIS_BLOCK_MS",
                str(DEFAULT_EVENTS_REDIS_BLOCK_MS),
            ),
        ),
        1,
    )


def load_events_redis_dedupe_ttl_seconds() -> int:
    return max(
        int(
            os.getenv(
                "APP_EVENTS_REDIS_DEDUPE_TTL_SECONDS",
                str(DEFAULT_EVENTS_REDIS_DEDUPE_TTL_SECONDS),
            ),
        ),
        1,
    )
