from __future__ import annotations

import os


DEFAULT_OCR_BACKEND = "local"
DEFAULT_OCR_PROVIDER = "host"
DEFAULT_OCR_HOST = "127.0.0.1"
DEFAULT_OCR_PORT = 18900


def load_ocr_backend() -> str:
    raw = os.getenv("APP_OCR_BACKEND", DEFAULT_OCR_BACKEND).strip().lower()
    if not raw:
        return DEFAULT_OCR_BACKEND
    if raw in {"local", "remote"}:
        return raw
    raise ValueError("APP_OCR_BACKEND must be one of: local, remote.")


def load_ocr_provider() -> str:
    raw = os.getenv("APP_OCR_PROVIDER", DEFAULT_OCR_PROVIDER).strip().lower()
    if not raw:
        return DEFAULT_OCR_PROVIDER
    if raw in {"host", "ppstructurev3"}:
        return raw
    raise ValueError("APP_OCR_PROVIDER must be one of: host, ppstructurev3.")


def load_ocr_host() -> str:
    return os.getenv("APP_OCR_HOST", DEFAULT_OCR_HOST).strip() or DEFAULT_OCR_HOST


def load_ocr_port() -> int:
    return max(int(os.getenv("APP_OCR_PORT", str(DEFAULT_OCR_PORT))), 1)


def validate_ocr_backend_provider(*, backend: str, provider: str) -> None:
    if backend == "local" and provider != "host":
        raise ValueError(
            "APP_OCR_PROVIDER must be 'host' when APP_OCR_BACKEND=local.",
        )


def resolve_ocr_base_url(*, backend: str, host: str, port: int) -> str:
    explicit = os.getenv("APP_OCR_BASE_URL", "").strip()
    if explicit:
        return explicit.rstrip("/")
    if backend == "remote":
        raise ValueError(
            "APP_OCR_BASE_URL must be set when APP_OCR_BACKEND=remote.",
        )
    return f"http://{host}:{port}"
