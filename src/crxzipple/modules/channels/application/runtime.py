from __future__ import annotations

import logging
from threading import Event as ThreadEvent
from typing import TYPE_CHECKING, Any


from crxzipple.modules.channels.application.services import (
    ChannelProfileApplicationService,
    ChannelRuntimeManager,
)
from crxzipple.modules.channels.application.bindings import (
    collect_channel_access_requirements,
    mask_channel_metadata,
    resolve_channel_metadata_binding,
)
from crxzipple.modules.channels.application.ports import (
    ChannelAccessReadinessPort,
)
from crxzipple.modules.channels.domain import (
    ChannelAccountRuntimeBinding,
    ChannelCapabilities,
    ChannelProfile,
    ChannelRuntimeRegistration,
    ChannelRuntimeRegistry,
    ChannelValidationError,
)
from crxzipple.shared.access import AccessConsumerRef, CredentialProvider

if TYPE_CHECKING:
    pass


logger = logging.getLogger(__name__)


class ChannelRuntimeBootstrapService:
    def __init__(
        self,
        *,
        profile_service: ChannelProfileApplicationService,
        runtime_manager: ChannelRuntimeManager,
        access_service: ChannelAccessReadinessPort | None = None,
        credential_provider: CredentialProvider | None = None,
    ) -> None:
        self.profile_service = profile_service
        self.runtime_manager = runtime_manager
        self.access_service = access_service
        self.credential_provider = credential_provider or access_service

    def ensure_registered(
        self,
        channel_type: str,
        *,
        runtime_id: str | None = None,
        service_key: str | None = None,
        status: str = "online",
        metadata: dict[str, Any] | None = None,
    ) -> ChannelRuntimeRegistration:
        normalized_channel = channel_type.strip().lower()
        resolved_runtime_id = runtime_id or f"{normalized_channel}-runtime-1"
        resolved_service_key = service_key or f"channel:{normalized_channel}"
        profile = self.profile_service.get_profile(normalized_channel)
        if profile is not None and not profile.enabled:
            raise ChannelValidationError(
                f"Channel '{normalized_channel}' profile is disabled.",
                code="channel_profile_disabled",
                details={"channel_type": normalized_channel},
            )
        self._ensure_profile_access_ready(normalized_channel, profile)
        existing = self.runtime_manager.get_runtime(resolved_runtime_id)
        capabilities = (
            profile.capabilities
            if profile is not None
            else ChannelCapabilities()
        )
        resolved_metadata = {
            **(dict(existing.metadata) if existing is not None else {}),
            **dict(metadata or {}),
        }
        registration = self.runtime_manager.register_runtime(
            ChannelRuntimeRegistration(
                runtime_id=resolved_runtime_id,
                channel_type=normalized_channel,
                service_key=resolved_service_key,
                status=status,
                capabilities=capabilities,
                metadata=resolved_metadata,
            ),
        )
        self._sync_profile_accounts(runtime_id=registration.runtime_id, profile=profile)
        return registration

    def heartbeat(self, runtime_id: str) -> ChannelRuntimeRegistration | None:
        return self.runtime_manager.heartbeat_runtime(runtime_id)

    def run_runtime_loop(
        self,
        channel_type: str,
        *,
        runtime_id: str | None = None,
        service_key: str | None = None,
        poll_interval_seconds: float,
        max_cycles: int | None = None,
        stop_event: ThreadEvent | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ChannelRuntimeRegistration:
        stopper = stop_event or ThreadEvent()
        registration = self.ensure_registered(
            channel_type,
            runtime_id=runtime_id,
            service_key=service_key,
            metadata=metadata,
        )
        completed_cycles = 0
        while not stopper.is_set():
            completed_cycles += 1
            if max_cycles is not None and completed_cycles >= max_cycles:
                break
            stopper.wait(max(float(poll_interval_seconds), 0.05))
            refreshed = self.heartbeat(registration.runtime_id)
            if refreshed is not None:
                registration = refreshed
        return registration

    def unregister_runtime(self, runtime_id: str) -> ChannelRuntimeRegistry:
        return self.runtime_manager.unregister_runtime(runtime_id)

    def _sync_profile_accounts(
        self,
        *,
        runtime_id: str,
        profile: ChannelProfile | None,
    ) -> None:
        if profile is None:
            return
        for account in profile.accounts:
            if not account.enabled:
                continue
            self.runtime_manager.bind_account(
                ChannelAccountRuntimeBinding(
                    channel_type=profile.channel_type,
                    channel_account_id=account.account_id,
                    runtime_id=runtime_id,
                    metadata={
                        "transport_mode": account.transport_mode,
                        **mask_channel_metadata(account.metadata),
                    },
                ),
            )

    def _ensure_profile_access_ready(
        self,
        channel_type: str,
        profile: ChannelProfile | None,
    ) -> None:
        if self.access_service is None or profile is None:
            return
        requirements = self._profile_access_requirements(profile)
        if not requirements:
            return
        readiness = self.access_service.check_requirements(requirements)
        missing = tuple(item for item in readiness if not item.ready)
        if not missing:
            return
        reason = "; ".join(
            f"{item.requirement.raw}: {item.reason}" for item in missing
        )
        raise ChannelValidationError(
            f"Channel '{channel_type}' access is not ready. {reason}",
            code="access_not_ready",
            details={
                "resource_type": "channel_runtime",
                "resource_id": channel_type,
                "access": [item.to_payload() for item in missing],
            },
        )

    def profile_access_requirements(
        self,
        profile: ChannelProfile,
    ) -> tuple[str, ...]:
        return self._profile_access_requirements(profile)

    def _profile_access_requirements(
        self,
        profile: ChannelProfile,
    ) -> tuple[str, ...]:
        resolved: list[str] = []
        for requirement in collect_channel_access_requirements(profile.metadata):
            if requirement not in resolved:
                resolved.append(requirement)
        for account in profile.accounts:
            if not account.enabled:
                continue
            for binding_id in account.credential_bindings.values():
                if isinstance(binding_id, str) and binding_id.strip():
                    normalized_binding = binding_id.strip()
                    if normalized_binding not in resolved:
                        resolved.append(normalized_binding)
            for requirement in collect_channel_access_requirements(account.metadata):
                if requirement not in resolved:
                    resolved.append(requirement)
        return tuple(resolved)

    def _access_consumer(
        self,
        *,
        channel_type: str,
        component: str,
        channel_account_id: str | None = None,
        field: str | None = None,
        runtime_ref: str | None = None,
    ) -> AccessConsumerRef:
        normalized_channel = channel_type.strip().lower()
        account = (
            channel_account_id.strip()
            if isinstance(channel_account_id, str) and channel_account_id.strip()
            else None
        )
        consumer_id = f"channels.{normalized_channel}"
        if account is not None:
            consumer_id = f"{consumer_id}.account:{account}"
        if field is not None and field.strip():
            consumer_id = f"{consumer_id}.{field.strip()}"
        return AccessConsumerRef(
            consumer_id=consumer_id,
            module="channels",
            component=component,
            runtime_ref=runtime_ref or normalized_channel,
            metadata={
                "channel_type": normalized_channel,
                "channel_account_id": account,
                "field": field,
            },
        )

    def _resolve_metadata_credential(
        self,
        metadata: dict[str, Any],
        *,
        key: str,
        description: str,
        required: bool,
        channel_type: str,
        component: str,
        channel_account_id: str | None = None,
        runtime_ref: str | None = None,
    ) -> str | None:
        return resolve_channel_metadata_binding(
            metadata,
            key=key,
            description=description,
            required=required,
            credential_provider=self.credential_provider,
            consumer=self._access_consumer(
                channel_type=channel_type,
                component=component,
                channel_account_id=channel_account_id,
                field=key,
                runtime_ref=runtime_ref,
            ),
        )
