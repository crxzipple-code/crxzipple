from __future__ import annotations

import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_ARTIFACT_STORE_DIR = PROJECT_ROOT / ".crxzipple" / "artifacts"
DEFAULT_ARTIFACT_IMAGE_PREVIEW_MAX_DIMENSION = 1024
DEFAULT_ARTIFACT_IMAGE_LLM_MAX_DIMENSION = 1568
DEFAULT_ARTIFACT_IMAGE_LLM_MAX_BYTES = 1_500_000
DEFAULT_ARTIFACT_FILE_LLM_MAX_BYTES = 4_000_000
DEFAULT_ARTIFACT_TEXT_FILE_LLM_MAX_CHARS = 20_000


def load_artifact_store_dir() -> str:
    return os.getenv(
        "APP_ARTIFACT_STORE_DIR",
        str(DEFAULT_ARTIFACT_STORE_DIR),
    )


def load_artifact_image_preview_max_dimension() -> int:
    return _positive_int_env(
        "APP_ARTIFACT_IMAGE_PREVIEW_MAX_DIMENSION",
        DEFAULT_ARTIFACT_IMAGE_PREVIEW_MAX_DIMENSION,
    )


def load_artifact_image_llm_max_dimension() -> int:
    return _positive_int_env(
        "APP_ARTIFACT_IMAGE_LLM_MAX_DIMENSION",
        DEFAULT_ARTIFACT_IMAGE_LLM_MAX_DIMENSION,
    )


def load_artifact_image_llm_max_bytes() -> int:
    return _positive_int_env(
        "APP_ARTIFACT_IMAGE_LLM_MAX_BYTES",
        DEFAULT_ARTIFACT_IMAGE_LLM_MAX_BYTES,
    )


def load_artifact_file_llm_max_bytes() -> int:
    return _positive_int_env(
        "APP_ARTIFACT_FILE_LLM_MAX_BYTES",
        DEFAULT_ARTIFACT_FILE_LLM_MAX_BYTES,
    )


def load_artifact_text_file_llm_max_chars() -> int:
    return _positive_int_env(
        "APP_ARTIFACT_TEXT_FILE_LLM_MAX_CHARS",
        DEFAULT_ARTIFACT_TEXT_FILE_LLM_MAX_CHARS,
    )


def _positive_int_env(name: str, default: int) -> int:
    return max(int(os.getenv(name, str(default))), 1)
