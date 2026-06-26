from __future__ import annotations

import os


DEFAULT_PROMPT_SYSTEM_MAX_CHARS = 120_000
DEFAULT_PROMPT_SYSTEM_MAX_TOKENS = 30_000
DEFAULT_PROMPT_SYSTEM_CONTEXT_WINDOW_RATIO = 0.15


def load_prompt_system_max_chars() -> int:
    return _positive_int_env(
        "APP_PROMPT_SYSTEM_MAX_CHARS",
        DEFAULT_PROMPT_SYSTEM_MAX_CHARS,
    )


def load_prompt_system_max_tokens() -> int:
    return _positive_int_env(
        "APP_PROMPT_SYSTEM_MAX_TOKENS",
        DEFAULT_PROMPT_SYSTEM_MAX_TOKENS,
    )


def load_prompt_system_context_window_ratio() -> float:
    return max(
        float(
            os.getenv(
                "APP_PROMPT_SYSTEM_CONTEXT_WINDOW_RATIO",
                str(DEFAULT_PROMPT_SYSTEM_CONTEXT_WINDOW_RATIO),
            ),
        ),
        0.01,
    )


def _positive_int_env(name: str, default: int) -> int:
    return max(int(os.getenv(name, str(default))), 1)
