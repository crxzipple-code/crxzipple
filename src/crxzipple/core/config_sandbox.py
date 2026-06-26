from __future__ import annotations

import os
import tempfile


DEFAULT_SANDBOX_BASE_DIR = os.path.join(
    tempfile.gettempdir(),
    "crxzipple-sandboxes",
)
DEFAULT_SANDBOX_BACKEND = "subprocess"
DEFAULT_SANDBOX_DOCKER_BINARY = "docker"
DEFAULT_SANDBOX_DOCKER_IMAGE = "python:3.11-slim"


def load_sandbox_base_dir() -> str:
    return os.getenv("APP_SANDBOX_BASE_DIR", DEFAULT_SANDBOX_BASE_DIR)


def load_sandbox_backend() -> str:
    return os.getenv("APP_SANDBOX_BACKEND", DEFAULT_SANDBOX_BACKEND).strip().lower()


def load_sandbox_docker_binary() -> str:
    return os.getenv("APP_SANDBOX_DOCKER_BINARY", DEFAULT_SANDBOX_DOCKER_BINARY)


def load_sandbox_docker_image() -> str:
    return os.getenv("APP_SANDBOX_DOCKER_IMAGE", DEFAULT_SANDBOX_DOCKER_IMAGE)
