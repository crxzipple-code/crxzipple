from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol

from crxzipple.modules.llm.application.llm_profile_credentials import (
    credential_binding_matches_expectation,
    credential_binding_type_label,
    credential_expectation_for,
    optional_string_config_value,
)
from crxzipple.modules.llm.domain.entities import LlmProfile
from crxzipple.modules.llm.domain.exceptions import (
    LlmAlreadyExistsError,
    LlmInvocationNotAllowedError,
    LlmNotFoundError,
    LlmValidationError,
)
from crxzipple.modules.llm.domain.repositories import (
    LlmInvocationRepository,
    LlmProfileRepository,
)
from crxzipple.modules.llm.domain import (
    LlmApiFamily,
    LlmCapability,
    LlmDefaults,
    LlmModelFamily,
    LlmProviderKind,
    LlmSourceKind,
)
from crxzipple.shared.access import CredentialProvider
from crxzipple.shared.domain.aggregates import AggregateRoot
from crxzipple.shared.domain.events import Event


class RegisterLlmProfileData(Protocol):
    id: str
    provider: LlmProviderKind
    api_family: LlmApiFamily
    model_name: str
    context_window_tokens: int | None
    model_family: LlmModelFamily
    capabilities: tuple[LlmCapability, ...]
    default_params: LlmDefaults
    base_url: str | None
    credential_binding_id: str | None
    timeout_seconds: int
    max_concurrency: int | None
    concurrency_key: str | None
    source_kind: LlmSourceKind
    enabled: bool


class LlmProfileUnitOfWork(Protocol):
    llm_profiles: LlmProfileRepository
    llm_invocations: LlmInvocationRepository

    def __enter__(self) -> "LlmProfileUnitOfWork": ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: Any,
    ) -> None: ...

    def collect(self, aggregate: AggregateRoot[Any]) -> None: ...

    def commit(self) -> None: ...


class LlmProfileService:
    def __init__(
        self,
        uow_factory: Callable[[], LlmProfileUnitOfWork],
        *,
        credential_provider: CredentialProvider | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._credential_provider = credential_provider

    @property
    def credential_provider(self) -> CredentialProvider | None:
        return self._credential_provider

    @credential_provider.setter
    def credential_provider(self, value: CredentialProvider | None) -> None:
        self._credential_provider = value

    def register_profile(self, data: RegisterLlmProfileData) -> LlmProfile:
        with self._uow_factory() as uow:
            if uow.llm_profiles.get(data.id) is not None:
                raise LlmAlreadyExistsError(f"LLM profile '{data.id}' already exists.")

            profile = self._build_profile(data)
            profile.record_event(
                Event(
                    name="llm.profile_registered",
                    payload={
                        "llm_id": profile.id,
                        "provider": profile.provider.value,
                        "api_family": profile.api_family.value,
                    },
                ),
            )
            uow.llm_profiles.add(profile)
            uow.collect(profile)
            uow.commit()
            return profile

    def upsert_profile(self, data: RegisterLlmProfileData) -> LlmProfile:
        with self._uow_factory() as uow:
            existing = uow.llm_profiles.get(data.id)
            profile = self._build_profile(data)
            profile.record_event(
                Event(
                    name=(
                        "llm.profile_registered"
                        if existing is None
                        else "llm.profile_updated"
                    ),
                    payload={
                        "llm_id": profile.id,
                        "provider": profile.provider.value,
                        "api_family": profile.api_family.value,
                        "source_kind": profile.source_kind.value,
                    },
                ),
            )
            uow.llm_profiles.add(profile)
            uow.collect(profile)
            uow.commit()
            return profile

    def update_profile(self, data: RegisterLlmProfileData) -> LlmProfile:
        with self._uow_factory() as uow:
            if uow.llm_profiles.get(data.id) is None:
                raise LlmNotFoundError(f"LLM profile '{data.id}' was not found.")
            profile = self._build_profile(data)
            profile.record_event(
                Event(
                    name="llm.profile_updated",
                    payload={
                        "llm_id": profile.id,
                        "provider": profile.provider.value,
                        "api_family": profile.api_family.value,
                        "source_kind": profile.source_kind.value,
                    },
                ),
            )
            uow.llm_profiles.add(profile)
            uow.collect(profile)
            uow.commit()
            return profile

    def set_profile_enabled(self, llm_id: str, *, enabled: bool) -> LlmProfile:
        with self._uow_factory() as uow:
            existing = uow.llm_profiles.get(llm_id)
            if existing is None:
                raise LlmNotFoundError(f"LLM profile '{llm_id}' was not found.")
            profile = LlmProfile(
                id=existing.id,
                provider=existing.provider,
                api_family=existing.api_family,
                model_name=existing.model_name,
                context_window_tokens=existing.context_window_tokens,
                model_family=existing.model_family,
                capabilities=existing.capabilities,
                default_params=existing.default_params,
                base_url=existing.base_url,
                credential_binding_id=existing.credential_binding_id,
                timeout_seconds=existing.timeout_seconds,
                max_concurrency=existing.max_concurrency,
                concurrency_key=existing.concurrency_key,
                source_kind=existing.source_kind,
                enabled=enabled,
            )
            profile.record_event(
                Event(
                    name=("llm.profile_enabled" if enabled else "llm.profile_disabled"),
                    payload={
                        "llm_id": profile.id,
                        "provider": profile.provider.value,
                        "api_family": profile.api_family.value,
                        "enabled": profile.enabled,
                    },
                ),
            )
            uow.llm_profiles.add(profile)
            uow.collect(profile)
            uow.commit()
            return profile

    def delete_profile(self, llm_id: str) -> None:
        with self._uow_factory() as uow:
            existing = uow.llm_profiles.get(llm_id)
            if existing is None:
                raise LlmNotFoundError(f"LLM profile '{llm_id}' was not found.")
            existing.record_event(
                Event(
                    name="llm.profile_deleted",
                    payload={
                        "llm_id": existing.id,
                        "provider": existing.provider.value,
                        "api_family": existing.api_family.value,
                    },
                ),
            )
            uow.llm_profiles.delete(llm_id)
            uow.collect(existing)
            uow.commit()

    def get_profile(self, llm_id: str) -> LlmProfile:
        with self._uow_factory() as uow:
            profile = uow.llm_profiles.get(llm_id)
            if profile is None:
                raise LlmNotFoundError(f"LLM profile '{llm_id}' was not found.")
            return profile

    def get_profile_optional(self, llm_id: str) -> LlmProfile | None:
        with self._uow_factory() as uow:
            return uow.llm_profiles.get(llm_id)

    def list_profiles(self) -> list[LlmProfile]:
        with self._uow_factory() as uow:
            return uow.llm_profiles.list()

    def get_enabled_profile(self, llm_id: str) -> LlmProfile:
        with self._uow_factory() as uow:
            profile = uow.llm_profiles.get(llm_id)
            if profile is None:
                raise LlmNotFoundError(f"LLM profile '{llm_id}' was not found.")
            if not profile.enabled:
                raise LlmInvocationNotAllowedError(
                    f"LLM profile '{profile.id}' is disabled.",
                )
            return profile

    def sync_profiles(
        self,
        profiles: tuple[RegisterLlmProfileData, ...],
        *,
        emit_events: bool = True,
    ) -> list[LlmProfile]:
        if not profiles:
            return []

        synced_profiles: list[LlmProfile] = []
        with self._uow_factory() as uow:
            for data in profiles:
                existing = uow.llm_profiles.get(data.id)
                if (
                    existing is not None
                    and existing.source_kind == LlmSourceKind.MANUAL
                    and data.source_kind != LlmSourceKind.MANUAL
                ):
                    synced_profiles.append(existing)
                    continue

                profile = self._build_profile(data)
                event_name = (
                    "llm.profile_registered"
                    if existing is None
                    else "llm.profile_updated"
                )
                if emit_events:
                    profile.record_event(
                        Event(
                            name=event_name,
                            payload={
                                "llm_id": profile.id,
                                "provider": profile.provider.value,
                                "api_family": profile.api_family.value,
                                "source_kind": profile.source_kind.value,
                            },
                        ),
                    )
                uow.llm_profiles.add(profile)
                uow.collect(profile)
                synced_profiles.append(profile)

            uow.commit()
            return synced_profiles

    def build_profile(self, data: RegisterLlmProfileData) -> LlmProfile:
        return self._build_profile(data)

    def _build_profile(self, data: RegisterLlmProfileData) -> LlmProfile:
        self._validate_credential_binding_expectation(data)
        return llm_profile_from_register_input(data)

    def _validate_credential_binding_expectation(
        self,
        data: RegisterLlmProfileData,
    ) -> None:
        inspector = getattr(self._credential_provider, "describe_credential_binding", None)
        if not callable(inspector):
            return
        expectation = credential_expectation_for(data.provider, data.api_family)
        binding_id = optional_string_config_value(data.credential_binding_id)
        if binding_id is None:
            if expectation["required"]:
                raise LlmValidationError(
                    f"LLM profile '{data.id}' requires {expectation['label']} credential binding.",
                )
            return
        metadata = inspector(binding_id)
        if metadata is None:
            raise LlmValidationError(
                f"LLM profile '{data.id}' references unknown Access credential binding '{binding_id}'.",
            )
        if not credential_binding_matches_expectation(metadata, expectation["kind"]):
            actual = credential_binding_type_label(metadata)
            raise LlmValidationError(
                f"LLM profile '{data.id}' expects {expectation['label']} credential binding, "
                f"but '{binding_id}' is {actual}.",
            )


def llm_profile_from_register_input(data: RegisterLlmProfileData) -> LlmProfile:
    return LlmProfile(
        id=data.id,
        provider=data.provider,
        api_family=data.api_family,
        model_name=data.model_name,
        context_window_tokens=data.context_window_tokens,
        model_family=data.model_family,
        capabilities=data.capabilities,
        default_params=data.default_params,
        base_url=data.base_url,
        credential_binding_id=data.credential_binding_id,
        timeout_seconds=data.timeout_seconds,
        max_concurrency=data.max_concurrency,
        concurrency_key=data.concurrency_key,
        source_kind=data.source_kind,
        enabled=data.enabled,
    )
