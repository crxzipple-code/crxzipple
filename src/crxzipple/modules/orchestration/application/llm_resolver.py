from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from crxzipple.modules.agent.domain.value_objects import AgentLlmRoutingPolicy
from crxzipple.modules.llm.domain.exceptions import LlmNotFoundError
from crxzipple.modules.llm.domain.value_objects import LlmCapability
from crxzipple.modules.orchestration.application.ports import (
    AccessReadinessPort,
    LlmPort,
)
from crxzipple.modules.orchestration.domain import OrchestrationValidationError
from crxzipple.shared.content_blocks import (
    FILE_BLOCK_TYPE,
    FILE_REF_BLOCK_TYPE,
    IMAGE_BLOCK_TYPE,
    IMAGE_REF_BLOCK_TYPE,
    normalize_content_blocks,
)


AUTO_LLM_ID = "auto"


@dataclass(frozen=True, slots=True)
class ResolvedLlmSelection:
    requested_llm_id: str
    resolved_llm_id: str
    strategy: str
    input_has_image: bool = False
    input_has_file: bool = False


def is_auto_llm_id(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() == AUTO_LLM_ID


def normalize_requested_llm_id(
    *,
    requested_llm_id: str | None,
    routing_policy: AgentLlmRoutingPolicy,
) -> str:
    normalized = (requested_llm_id or "").strip()
    if normalized:
        return normalized
    return routing_policy.default_llm_id


@dataclass(slots=True)
class LlmResolver:
    llm_port: LlmPort
    access_port: AccessReadinessPort | None = None

    def resolve(
        self,
        *,
        requested_llm_id: str | None,
        routing_policy: AgentLlmRoutingPolicy,
        input_content: Any | None,
        workspace_dir: str | None = None,
        validate_access: bool = True,
    ) -> ResolvedLlmSelection:
        normalized_requested = normalize_requested_llm_id(
            requested_llm_id=requested_llm_id,
            routing_policy=routing_policy,
        )
        input_has_image, input_has_file = _detect_input_modalities(input_content)
        if not is_auto_llm_id(normalized_requested):
            try:
                profile = self.llm_port.get_profile(normalized_requested)
            except LlmNotFoundError as exc:
                raise OrchestrationValidationError(
                    f"LLM profile '{normalized_requested}' was not found.",
                    code="llm_profile_not_found",
                    details={"llm_id": normalized_requested},
                ) from exc
            if not profile.enabled:
                raise OrchestrationValidationError(
                    f"LLM profile '{profile.id}' is disabled.",
                )
            if validate_access:
                self._ensure_profile_access_ready(
                    profile,
                    workspace_dir=workspace_dir,
                )
            strategy = (
                "explicit"
                if requested_llm_id is not None and requested_llm_id.strip()
                else "profile-default"
            )
            return ResolvedLlmSelection(
                requested_llm_id=normalized_requested,
                resolved_llm_id=normalized_requested,
                strategy=strategy,
                input_has_image=input_has_image,
                input_has_file=input_has_file,
            )

        candidates: list[str | None]
        required_capabilities: tuple[LlmCapability, ...] = ()
        if input_has_image:
            strategy = "auto-image"
            required_capabilities = (LlmCapability.VISION_INPUT,)
            candidates = [
                routing_policy.image_llm_id,
                routing_policy.default_llm_id,
                *routing_policy.fallback_llm_ids,
            ]
        elif input_has_file:
            strategy = "auto-document"
            candidates = [
                routing_policy.document_llm_id,
                routing_policy.default_llm_id,
                *routing_policy.fallback_llm_ids,
            ]
        else:
            strategy = "auto-default"
            candidates = [
                routing_policy.default_llm_id,
                *routing_policy.fallback_llm_ids,
            ]

        attempted = _normalize_candidates(candidates)
        for candidate in attempted:
            try:
                profile = self.llm_port.get_profile(candidate)
            except LlmNotFoundError:
                continue
            if not profile.enabled:
                continue
            if any(capability not in profile.capabilities for capability in required_capabilities):
                continue
            if validate_access and not self._profile_access_ready(
                profile,
                workspace_dir=workspace_dir,
            ):
                continue
            return ResolvedLlmSelection(
                requested_llm_id=normalized_requested,
                resolved_llm_id=profile.id,
                strategy=strategy,
                input_has_image=input_has_image,
                input_has_file=input_has_file,
            )

        if input_has_image:
            raise OrchestrationValidationError(
                "Auto LLM routing could not find an enabled vision-capable model. "
                f"Checked: {', '.join(attempted) or '(none)'}."
            )
        if input_has_file:
            raise OrchestrationValidationError(
                "Auto LLM routing could not find an enabled document model. "
                f"Checked: {', '.join(attempted) or '(none)'}."
            )
        raise OrchestrationValidationError(
            "Auto LLM routing could not find an enabled model. "
            f"Checked: {', '.join(attempted) or '(none)'}."
        )

    def _ensure_profile_access_ready(
        self,
        profile,
        *,
        workspace_dir: str | None,
    ) -> None:
        readiness = self._profile_access_readiness(profile, workspace_dir=workspace_dir)
        if readiness is None or readiness.ready:
            return
        access_payload = readiness.to_payload()
        raise OrchestrationValidationError(
            "LLM profile "
            f"'{profile.id}' access is not ready: {readiness.reason}",
            code="access_not_ready",
            details={
                "resource_type": "llm_profile",
                "resource_id": profile.id,
                "access": access_payload,
            },
        )

    def _profile_access_ready(
        self,
        profile,
        *,
        workspace_dir: str | None,
    ) -> bool:
        readiness = self._profile_access_readiness(profile, workspace_dir=workspace_dir)
        return readiness is None or readiness.ready

    def _profile_access_readiness(
        self,
        profile,
        *,
        workspace_dir: str | None,
    ):
        if self.access_port is None:
            return None
        binding = (
            profile.credential_binding_id.strip()
            if isinstance(profile.credential_binding_id, str)
            else ""
        )
        if not binding:
            return None
        return self.access_port.check_credential_binding(
            binding,
            workspace_dir=workspace_dir,
            allow_literal=False,
        )


def _detect_input_modalities(value: Any | None) -> tuple[bool, bool]:
    try:
        blocks = normalize_content_blocks(value)
    except ValueError:
        return False, False
    has_image = any(
        block.get("type") in {IMAGE_BLOCK_TYPE, IMAGE_REF_BLOCK_TYPE}
        for block in blocks
    )
    has_file = any(
        block.get("type") in {FILE_BLOCK_TYPE, FILE_REF_BLOCK_TYPE}
        for block in blocks
    )
    return has_image, has_file


def _normalize_candidates(values: list[str | None]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in values:
        candidate = (raw or "").strip()
        if not candidate or candidate in seen or is_auto_llm_id(candidate):
            continue
        seen.add(candidate)
        normalized.append(candidate)
    return normalized
