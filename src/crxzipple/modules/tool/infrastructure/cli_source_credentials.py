from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import tempfile
from typing import Any, Protocol

from crxzipple.core.logger import get_logger
from crxzipple.modules.tool.domain.exceptions import ToolValidationError
from crxzipple.shared.access import (
    AccessConsumerRef,
    AccessCredentialKind,
    CredentialBindingRef,
)


logger = get_logger(__name__)


class CliCredentialBinding(Protocol):
    binding_id: str
    injection: str
    env_name: str | None
    file_env_name: str | None
    file_name: str
    expected_kind: AccessCredentialKind
    provider: str | None
    slot: str | None


class CliCredentialSourceConfig(Protocol):
    source_id: str
    provider_name: str
    credential_bindings: tuple[CliCredentialBinding, ...]


@dataclass(frozen=True, slots=True)
class CliCredentialInjection:
    env: dict[str, str]
    cleanup_paths: tuple[Path, ...]
    metadata: tuple[dict[str, str | None], ...]
    redactions: tuple[str, ...] = ()

    def cleanup(self) -> None:
        for path in self.cleanup_paths:
            try:
                if path.is_file():
                    path.unlink(missing_ok=True)
                parent = path.parent
                if parent.name.startswith("crxzipple-tool-credential-"):
                    parent.rmdir()
            except OSError:
                logger.debug(
                    "failed to cleanup CLI credential temp path",
                    extra={"path": str(path)},
                )


def resolve_credential_injection(
    config: CliCredentialSourceConfig,
    *,
    credential_provider: Any | None,
    action: str,
) -> CliCredentialInjection:
    if action not in {"cli_execute", "cli_promoted_execute"} or not config.credential_bindings:
        return CliCredentialInjection(env={}, cleanup_paths=(), metadata=())
    if credential_provider is None:
        raise ToolValidationError(
            f"Configured CLI source '{config.source_id}' requires credential_provider.",
        )
    env: dict[str, str] = {}
    cleanup_paths: list[Path] = []
    metadata: list[dict[str, str | None]] = []
    redactions: list[str] = []
    try:
        for binding in config.credential_bindings:
            secret = _resolve_credential(
                binding,
                config=config,
                credential_provider=credential_provider,
                action=action,
            )
            if secret:
                redactions.append(secret)
            if binding.injection == "env":
                assert binding.env_name is not None
                env[binding.env_name] = secret
                metadata.append(credential_injection_metadata(binding))
                continue
            assert binding.file_env_name is not None
            credential_file = _write_credential_temp_file(
                secret,
                file_name=binding.file_name,
            )
            cleanup_paths.append(credential_file)
            env[binding.file_env_name] = str(credential_file)
            metadata.append(credential_injection_metadata(binding))
    except Exception:
        CliCredentialInjection(
            env=env,
            cleanup_paths=tuple(cleanup_paths),
            metadata=tuple(metadata),
            redactions=tuple(redactions),
        ).cleanup()
        raise
    return CliCredentialInjection(
        env=env,
        cleanup_paths=tuple(cleanup_paths),
        metadata=tuple(metadata),
        redactions=tuple(redactions),
    )


def credential_injection_metadata(
    binding: CliCredentialBinding,
) -> dict[str, str | None]:
    return {
        "binding_id": binding.binding_id,
        "injection": binding.injection,
        "env_name": binding.env_name,
        "file_env_name": binding.file_env_name,
        "file_name": binding.file_name if binding.injection == "file" else None,
        "expected_kind": binding.expected_kind.value,
        "provider": binding.provider,
        "slot": binding.slot,
    }


def _resolve_credential(
    binding: CliCredentialBinding,
    *,
    config: CliCredentialSourceConfig,
    credential_provider: Any,
    action: str,
) -> str:
    try:
        return credential_provider.resolve_credential(
            CredentialBindingRef(
                binding_id=binding.binding_id,
                source_type="binding",
                source_ref=binding.binding_id,
                expected_kind=binding.expected_kind,
                metadata={
                    "provider": binding.provider,
                    "slot": binding.slot or binding.binding_id,
                    "source_id": config.source_id,
                    "cli_action": action,
                },
            ),
            consumer=AccessConsumerRef(
                consumer_id=f"tool.cli_source:{config.source_id}:{action}",
                module="tool",
                component="cli_source",
                runtime_ref=f"cli.{config.source_id}.{action}",
                metadata={
                    "provider": config.provider_name,
                    "source_id": config.source_id,
                },
            ),
        )
    except Exception as exc:  # noqa: BLE001
        raise ToolValidationError(
            f"Configured CLI source '{config.source_id}' could not resolve credential binding '{binding.binding_id}'.",
        ) from exc


def _write_credential_temp_file(secret: str, *, file_name: str) -> Path:
    temp_dir = Path(tempfile.mkdtemp(prefix="crxzipple-tool-credential-"))
    os.chmod(temp_dir, 0o700)
    path = temp_dir / _safe_credential_file_name(file_name)
    path.write_text(secret, encoding="utf-8")
    os.chmod(path, 0o600)
    return path


def _safe_credential_file_name(value: str) -> str:
    normalized = "".join(
        ch
        for ch in value.strip()
        if ch.isalnum() or ch in {"-", "_", "."}
    ).strip(".")
    return normalized or "credential"


__all__ = [
    "CliCredentialInjection",
    "credential_injection_metadata",
    "resolve_credential_injection",
]
