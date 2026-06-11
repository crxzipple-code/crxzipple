from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from importlib.resources import files


RUNTIME_CONTRACT_VERSION = "2026-06-10"
_PROMPT_PACKAGE = "crxzipple.modules.context_workspace.application.prompts"
_PROMPT_FILENAME = "runtime_contract.md"


@dataclass(frozen=True, slots=True)
class RuntimeContract:
    version: str
    content: str
    content_hash: str


def load_runtime_contract() -> RuntimeContract:
    content = (
        files(_PROMPT_PACKAGE)
        .joinpath(_PROMPT_FILENAME)
        .read_text(encoding="utf-8")
        .strip()
    )
    if not content:
        raise RuntimeError("Runtime contract prompt asset is empty.")
    return RuntimeContract(
        version=RUNTIME_CONTRACT_VERSION,
        content=content,
        content_hash=sha256(content.encode("utf-8")).hexdigest(),
    )


__all__ = ["RuntimeContract", "load_runtime_contract"]
