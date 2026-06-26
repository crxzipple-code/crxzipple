from __future__ import annotations

import os

from crxzipple.core.config_env import env_flag


DEFAULT_LOG_LEVEL = "INFO"
DEFAULT_LOG_JSON = False


def load_log_level() -> str:
    return os.getenv("APP_LOG_LEVEL", DEFAULT_LOG_LEVEL).upper()


def load_log_json() -> bool:
    return env_flag("APP_LOG_JSON", default=DEFAULT_LOG_JSON)
