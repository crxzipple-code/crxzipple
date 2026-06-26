from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import uuid4

from crxzipple.modules.tool.application.catalog_function_models import (
    ToolFunctionCandidate,
    ToolProviderBackendCandidate,
)
from crxzipple.modules.tool.application.catalog_model_helpers import (
    hash_payload,
    normalize_mapping,
    normalize_text_tuple,
    required_text,
    utc_now,
)
from crxzipple.modules.tool.application.catalog_model_types import (
    ToolSourceCatalogKind,
    ToolSourceDiscoveryStatus,
    ToolSourceStatus,
)
from crxzipple.modules.tool.domain.exceptions import ToolValidationError
from crxzipple.shared.access import AccessCredentialRequirementSet


@dataclass(frozen=True, slots=True)
class ToolSourceCatalogRecord:
    source_id: str
    kind: ToolSourceCatalogKind | str
    display_name: str
    description: str = ""
    config: Mapping[str, Any] = field(default_factory=dict)
    credential_requirements: tuple[AccessCredentialRequirementSet, ...] = ()
    runtime_requirements: tuple[str, ...] = ()
    status: ToolSourceStatus | str = ToolSourceStatus.ACTIVE
    revision: int = 1
    config_hash: str = ""
    last_discovered_at: datetime | None = None
    last_discovery_status: ToolSourceDiscoveryStatus | str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "source_id",
            required_text(self.source_id, field_name="source_id"),
        )
        object.__setattr__(self, "kind", ToolSourceCatalogKind(str(self.kind)))
        object.__setattr__(
            self,
            "display_name",
            required_text(self.display_name, field_name="display_name"),
        )
        object.__setattr__(self, "description", str(self.description).strip())
        config = normalize_mapping(self.config, field_name="config")
        object.__setattr__(self, "config", config)
        object.__setattr__(
            self,
            "credential_requirements",
            tuple(self.credential_requirements),
        )
        object.__setattr__(
            self,
            "runtime_requirements",
            normalize_text_tuple(self.runtime_requirements),
        )
        object.__setattr__(self, "status", ToolSourceStatus(str(self.status)))
        if self.revision < 1:
            raise ToolValidationError("Tool source revision must be at least 1.")
        config_hash = str(self.config_hash).strip()
        if not config_hash:
            config_hash = hash_payload({"config": config})
        object.__setattr__(self, "config_hash", config_hash)
        if self.last_discovery_status is not None:
            object.__setattr__(
                self,
                "last_discovery_status",
                ToolSourceDiscoveryStatus(str(self.last_discovery_status)),
            )


@dataclass(frozen=True, slots=True)
class ToolSourceDiscoveryResult:
    source_id: str
    candidates: tuple[ToolFunctionCandidate, ...] = ()
    provider_backend_candidates: tuple[ToolProviderBackendCandidate, ...] = ()
    discovered_at: datetime = field(default_factory=utc_now)
    status: ToolSourceDiscoveryStatus | str = ToolSourceDiscoveryStatus.COMPLETED
    error_message: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        source_id = required_text(self.source_id, field_name="source_id")
        object.__setattr__(self, "source_id", source_id)
        object.__setattr__(self, "candidates", tuple(self.candidates))
        object.__setattr__(
            self,
            "provider_backend_candidates",
            tuple(self.provider_backend_candidates),
        )
        object.__setattr__(self, "status", ToolSourceDiscoveryStatus(str(self.status)))
        error_message = (
            str(self.error_message).strip()
            if self.error_message is not None
            else None
        )
        object.__setattr__(self, "error_message", error_message or None)
        object.__setattr__(
            self,
            "metadata",
            normalize_mapping(self.metadata, field_name="metadata"),
        )
        for candidate in self.candidates:
            if candidate.source_id != source_id:
                raise ToolValidationError(
                    "Tool discovery result candidate source_id must match result source_id.",
                )
        for candidate in self.provider_backend_candidates:
            if candidate.source_id != source_id:
                raise ToolValidationError(
                    "Tool discovery result backend source_id must match result source_id.",
                )

    @classmethod
    def completed(
        cls,
        *,
        source_id: str,
        candidates: tuple[ToolFunctionCandidate, ...] = (),
        provider_backend_candidates: tuple[ToolProviderBackendCandidate, ...] = (),
        discovered_at: datetime | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> "ToolSourceDiscoveryResult":
        return cls(
            source_id=source_id,
            candidates=candidates,
            provider_backend_candidates=provider_backend_candidates,
            discovered_at=discovered_at or utc_now(),
            status=ToolSourceDiscoveryStatus.COMPLETED,
            metadata=dict(metadata or {}),
        )

    @classmethod
    def failed(
        cls,
        *,
        source_id: str,
        error_message: str,
        discovered_at: datetime | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> "ToolSourceDiscoveryResult":
        return cls(
            source_id=source_id,
            discovered_at=discovered_at or utc_now(),
            status=ToolSourceDiscoveryStatus.FAILED,
            error_message=error_message,
            metadata=dict(metadata or {}),
        )


@dataclass(frozen=True, slots=True)
class ToolSourceDiscoveryRunRecord:
    discovery_run_id: str
    source_id: str
    source_revision: int
    config_hash: str
    status: ToolSourceDiscoveryStatus | str
    discovered_at: datetime
    function_count: int = 0
    provider_backend_count: int = 0
    error_message: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        discovery_run_id = str(self.discovery_run_id or "").strip() or uuid4().hex
        object.__setattr__(self, "discovery_run_id", discovery_run_id)
        object.__setattr__(
            self,
            "source_id",
            required_text(self.source_id, field_name="source_id"),
        )
        if self.source_revision < 1:
            raise ToolValidationError(
                "Tool source discovery source_revision must be at least 1.",
            )
        object.__setattr__(
            self,
            "config_hash",
            required_text(self.config_hash, field_name="config_hash"),
        )
        object.__setattr__(
            self,
            "status",
            ToolSourceDiscoveryStatus(str(self.status)),
        )
        if self.function_count < 0:
            raise ToolValidationError(
                "Tool source discovery function_count must not be negative.",
            )
        if self.provider_backend_count < 0:
            raise ToolValidationError(
                "Tool source discovery provider_backend_count must not be negative.",
            )
        error_message = (
            str(self.error_message).strip()
            if self.error_message is not None
            else None
        )
        object.__setattr__(self, "error_message", error_message or None)
        object.__setattr__(
            self,
            "metadata",
            normalize_mapping(self.metadata, field_name="metadata"),
        )

    @classmethod
    def from_result(
        cls,
        *,
        source: ToolSourceCatalogRecord,
        discovery: ToolSourceDiscoveryResult,
        discovery_run_id: str | None = None,
    ) -> "ToolSourceDiscoveryRunRecord":
        return cls(
            discovery_run_id=discovery_run_id or uuid4().hex,
            source_id=source.source_id,
            source_revision=source.revision,
            config_hash=source.config_hash,
            status=discovery.status,
            discovered_at=discovery.discovered_at,
            function_count=len(discovery.candidates),
            provider_backend_count=len(discovery.provider_backend_candidates),
            error_message=discovery.error_message,
            metadata=discovery.metadata,
        )
