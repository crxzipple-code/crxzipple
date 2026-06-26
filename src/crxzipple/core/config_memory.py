from __future__ import annotations

import os


DEFAULT_MEMORY_RETRIEVAL_BACKEND = "keyword"
DEFAULT_MEMORY_VECTOR_PROVIDER = "local"
DEFAULT_MEMORY_VECTOR_TIMEOUT_SECONDS = 30
DEFAULT_MEMORY_WATCH_INTERVAL_SECONDS = 300.0


def load_memory_retrieval_backend() -> str:
    raw = os.getenv(
        "APP_MEMORY_RETRIEVAL_BACKEND",
        DEFAULT_MEMORY_RETRIEVAL_BACKEND,
    ).strip().lower()
    if not raw:
        return DEFAULT_MEMORY_RETRIEVAL_BACKEND
    if raw in {"keyword", "hybrid", "vector"}:
        return raw
    raise ValueError(
        "APP_MEMORY_RETRIEVAL_BACKEND must be one of: keyword, hybrid, vector.",
    )


def load_memory_vector_provider() -> str:
    raw = os.getenv(
        "APP_MEMORY_VECTOR_PROVIDER",
        DEFAULT_MEMORY_VECTOR_PROVIDER,
    ).strip().lower()
    if not raw:
        return DEFAULT_MEMORY_VECTOR_PROVIDER
    if raw in {"local", "openai_compatible"}:
        return raw
    raise ValueError(
        "APP_MEMORY_VECTOR_PROVIDER must be one of: local, openai_compatible.",
    )


def load_memory_vector_timeout_seconds() -> int:
    return max(
        int(
            os.getenv(
                "APP_MEMORY_VECTOR_TIMEOUT_SECONDS",
                str(DEFAULT_MEMORY_VECTOR_TIMEOUT_SECONDS),
            ),
        ),
        1,
    )


def load_memory_watch_interval_seconds() -> float:
    return max(
        float(
            os.getenv(
                "APP_MEMORY_WATCH_INTERVAL_SECONDS",
                str(DEFAULT_MEMORY_WATCH_INTERVAL_SECONDS),
            ),
        ),
        0.0,
    )
