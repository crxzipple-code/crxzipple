from __future__ import annotations

from dataclasses import replace
from typing import Any

from crxzipple.modules.channels.application.ports import ChannelRuntimeRegistryStore
from crxzipple.modules.channels.application.service_helpers import (
    normalize_identifier,
    normalize_key,
    utcnow,
)
from crxzipple.modules.channels.domain import (
    ChannelAccountRuntimeBinding,
    ChannelConnectionBinding,
    ChannelRuntimeRegistration,
    ChannelRuntimeRegistry,
    ChannelValidationError,
)


class ChannelRuntimeManager:
    def __init__(self, *, registry_store: ChannelRuntimeRegistryStore) -> None:
        self.registry_store = registry_store

    def snapshot(self) -> ChannelRuntimeRegistry:
        return self.registry_store.load()

    def list_runtimes(
        self,
        *,
        channel_type: str | None = None,
    ) -> tuple[ChannelRuntimeRegistration, ...]:
        registry = self.registry_store.load()
        if channel_type is None:
            return registry.runtimes
        normalized = normalize_key(channel_type)
        return tuple(
            item
            for item in registry.runtimes
            if normalize_key(item.channel_type) == normalized
        )

    def register_runtime(
        self,
        registration: ChannelRuntimeRegistration,
    ) -> ChannelRuntimeRegistration:
        if not registration.runtime_id.strip():
            raise ChannelValidationError("runtime registration must include runtime_id.")
        if not registration.channel_type.strip():
            raise ChannelValidationError("runtime registration must include channel_type.")
        registry = self.registry_store.update(
            lambda current: replace(
                current,
                runtimes=tuple(
                    {
                        **{item.runtime_id: item for item in current.runtimes},
                        registration.runtime_id: registration,
                    }[key]
                    for key in sorted(
                        {
                            *(item.runtime_id for item in current.runtimes),
                            registration.runtime_id,
                        },
                    )
                ),
            ),
        )
        resolved = next(
            (
                item
                for item in registry.runtimes
                if item.runtime_id == registration.runtime_id
            ),
            None,
        )
        if resolved is None:
            raise ChannelValidationError("runtime registration did not persist.")
        return resolved

    def get_runtime(self, runtime_id: str) -> ChannelRuntimeRegistration | None:
        for runtime in self.registry_store.load().runtimes:
            if runtime.runtime_id == runtime_id:
                return runtime
        return None

    def heartbeat_runtime(self, runtime_id: str) -> ChannelRuntimeRegistration | None:
        found = False

        def _mutate(registry: ChannelRuntimeRegistry) -> ChannelRuntimeRegistry:
            nonlocal found
            runtimes: list[ChannelRuntimeRegistration] = []
            for item in registry.runtimes:
                if item.runtime_id == runtime_id:
                    found = True
                    runtimes.append(replace(item, last_heartbeat_at=utcnow()))
                else:
                    runtimes.append(item)
            if not found:
                return registry
            return replace(registry, runtimes=tuple(runtimes))

        registry = self.registry_store.update(_mutate)
        if not found:
            return None
        return next((item for item in registry.runtimes if item.runtime_id == runtime_id), None)

    def merge_runtime_metadata(
        self,
        runtime_id: str,
        *,
        metadata: dict[str, object],
        touch_heartbeat: bool = False,
    ) -> ChannelRuntimeRegistration | None:
        if not metadata:
            return self.get_runtime(runtime_id)
        found = False

        def _mutate(registry: ChannelRuntimeRegistry) -> ChannelRuntimeRegistry:
            nonlocal found
            runtimes: list[ChannelRuntimeRegistration] = []
            for item in registry.runtimes:
                if item.runtime_id == runtime_id:
                    found = True
                    runtimes.append(
                        replace(
                            item,
                            metadata={
                                **dict(item.metadata),
                                **dict(metadata),
                            },
                            last_heartbeat_at=(
                                utcnow() if touch_heartbeat else item.last_heartbeat_at
                            ),
                        )
                    )
                else:
                    runtimes.append(item)
            if not found:
                return registry
            return replace(registry, runtimes=tuple(runtimes))

        registry = self.registry_store.update(_mutate)
        if not found:
            return None
        return next((item for item in registry.runtimes if item.runtime_id == runtime_id), None)

    def unregister_runtime(self, runtime_id: str) -> ChannelRuntimeRegistry:
        saved = self.registry_store.update(
            lambda registry: replace(
                registry,
                runtimes=tuple(
                    item for item in registry.runtimes if item.runtime_id != runtime_id
                ),
                account_bindings=tuple(
                    item
                    for item in registry.account_bindings
                    if item.runtime_id != runtime_id
                ),
                connection_bindings=tuple(
                    item
                    for item in registry.connection_bindings
                    if item.runtime_id != runtime_id
                ),
            ),
        )
        return saved

    def bind_account(
        self,
        binding: ChannelAccountRuntimeBinding,
    ) -> ChannelAccountRuntimeBinding:
        registry = self.registry_store.update(
            lambda current: self._bind_account_in_registry(current, binding),
        )
        resolved = next(
            (
                item
                for item in registry.account_bindings
                if (
                    normalize_key(item.channel_type) == normalize_key(binding.channel_type)
                    and normalize_identifier(item.channel_account_id)
                    == normalize_identifier(binding.channel_account_id)
                )
            ),
            None,
        )
        if resolved is None:
            raise ChannelValidationError("account binding did not persist.")
        return resolved

    def resolve_account_binding(
        self,
        *,
        channel_type: str,
        channel_account_id: str,
    ) -> ChannelAccountRuntimeBinding | None:
        normalized_channel = normalize_key(channel_type)
        normalized_account = normalize_identifier(channel_account_id)
        for item in self.registry_store.load().account_bindings:
            if (
                normalize_key(item.channel_type) == normalized_channel
                and normalize_identifier(item.channel_account_id) == normalized_account
            ):
                return item
        return None

    def resolve_account_runtime(
        self,
        *,
        channel_type: str,
        channel_account_id: str,
    ) -> ChannelRuntimeRegistration | None:
        binding = self.resolve_account_binding(
            channel_type=channel_type,
            channel_account_id=channel_account_id,
        )
        if binding is None:
            return None
        return self.get_runtime(binding.runtime_id)

    def list_account_bindings(
        self,
        *,
        runtime_id: str | None = None,
        channel_type: str | None = None,
    ) -> tuple[ChannelAccountRuntimeBinding, ...]:
        bindings = self.registry_store.load().account_bindings
        if runtime_id is not None:
            bindings = tuple(item for item in bindings if item.runtime_id == runtime_id)
        if channel_type is not None:
            normalized = normalize_key(channel_type)
            bindings = tuple(
                item
                for item in bindings
                if normalize_key(item.channel_type) == normalized
            )
        return bindings

    def bind_connection(
        self,
        binding: ChannelConnectionBinding,
    ) -> ChannelConnectionBinding:
        registry = self.registry_store.update(
            lambda current: self._bind_connection_in_registry(current, binding),
        )
        resolved = next(
            (
                item
                for item in registry.connection_bindings
                if (
                    normalize_key(item.channel_type) == normalize_key(binding.channel_type)
                    and normalize_identifier(item.connection_id)
                    == normalize_identifier(binding.connection_id)
                )
            ),
            None,
        )
        if resolved is None:
            raise ChannelValidationError("connection binding did not persist.")
        return resolved

    def update_connection_subscription(
        self,
        *,
        channel_type: str,
        connection_id: str,
        conversation_id: str | None,
    ) -> ChannelConnectionBinding | None:
        binding = self.resolve_connection_binding(
            channel_type=channel_type,
            connection_id=connection_id,
        )
        if binding is None:
            return None
        normalized_conversation_id = (
            normalize_identifier(conversation_id)
            if isinstance(conversation_id, str) and normalize_identifier(conversation_id)
            else None
        )
        current_conversation_id = (
            normalize_identifier(binding.conversation_id)
            if isinstance(binding.conversation_id, str)
            and normalize_identifier(binding.conversation_id)
            else None
        )
        metadata = dict(binding.metadata)
        if current_conversation_id != normalized_conversation_id:
            metadata.pop("observe_cursor", None)
            metadata.pop("live_cursor", None)
            metadata["observe_subscription_updated_at"] = utcnow().isoformat()
        return self.bind_connection(
            replace(
                binding,
                conversation_id=normalized_conversation_id,
                metadata=metadata,
                updated_at=utcnow(),
            ),
        )

    def merge_connection_metadata(
        self,
        *,
        channel_type: str,
        connection_id: str,
        metadata: dict[str, Any],
    ) -> ChannelConnectionBinding | None:
        normalized_channel = normalize_key(channel_type)
        normalized_connection = normalize_identifier(connection_id)
        saved = self.registry_store.update(
            lambda registry: replace(
                registry,
                connection_bindings=tuple(
                    replace(
                        item,
                        metadata={
                            **dict(item.metadata),
                            **dict(metadata),
                        },
                        updated_at=utcnow(),
                    )
                    if (
                        normalize_key(item.channel_type) == normalized_channel
                        and normalize_identifier(item.connection_id)
                        == normalized_connection
                    )
                    else item
                    for item in registry.connection_bindings
                ),
            ),
        )
        for item in saved.connection_bindings:
            if (
                normalize_key(item.channel_type) == normalized_channel
                and normalize_identifier(item.connection_id) == normalized_connection
            ):
                return item
        return None

    def resolve_connection_binding(
        self,
        *,
        channel_type: str,
        connection_id: str,
    ) -> ChannelConnectionBinding | None:
        normalized_channel = normalize_key(channel_type)
        normalized_connection = normalize_identifier(connection_id)
        for item in self.registry_store.load().connection_bindings:
            if (
                normalize_key(item.channel_type) == normalized_channel
                and normalize_identifier(item.connection_id) == normalized_connection
            ):
                return item
        return None

    def resolve_connection_runtime(
        self,
        *,
        channel_type: str,
        connection_id: str,
    ) -> ChannelRuntimeRegistration | None:
        binding = self.resolve_connection_binding(
            channel_type=channel_type,
            connection_id=connection_id,
        )
        if binding is None:
            return None
        return self.get_runtime(binding.runtime_id)

    def list_connection_bindings(
        self,
        *,
        runtime_id: str | None = None,
        channel_type: str | None = None,
    ) -> tuple[ChannelConnectionBinding, ...]:
        bindings = self.registry_store.load().connection_bindings
        if runtime_id is not None:
            bindings = tuple(item for item in bindings if item.runtime_id == runtime_id)
        if channel_type is not None:
            normalized = normalize_key(channel_type)
            bindings = tuple(
                item
                for item in bindings
                if normalize_key(item.channel_type) == normalized
            )
        return bindings

    def unbind_connection(
        self,
        *,
        channel_type: str,
        connection_id: str,
    ) -> ChannelRuntimeRegistry:
        normalized_channel = normalize_key(channel_type)
        normalized_connection = normalize_identifier(connection_id)
        return self.registry_store.update(
            lambda registry: replace(
                registry,
                connection_bindings=tuple(
                    item
                    for item in registry.connection_bindings
                    if not (
                        normalize_key(item.channel_type) == normalized_channel
                        and normalize_identifier(item.connection_id)
                        == normalized_connection
                    )
                ),
            ),
        )

    def _bind_account_in_registry(
        self,
        registry: ChannelRuntimeRegistry,
        binding: ChannelAccountRuntimeBinding,
    ) -> ChannelRuntimeRegistry:
        runtime = next(
            (item for item in registry.runtimes if item.runtime_id == binding.runtime_id),
            None,
        )
        if runtime is None:
            raise ChannelValidationError(
                f"runtime '{binding.runtime_id}' does not exist.",
            )
        if normalize_key(runtime.channel_type) != normalize_key(binding.channel_type):
            raise ChannelValidationError(
                "account binding channel_type must match registered runtime channel_type.",
            )
        account_bindings = [
            item
            for item in registry.account_bindings
            if not (
                normalize_key(item.channel_type) == normalize_key(binding.channel_type)
                and normalize_identifier(item.channel_account_id)
                == normalize_identifier(binding.channel_account_id)
            )
        ]
        account_bindings.append(replace(binding, updated_at=utcnow()))
        return replace(
            registry,
            account_bindings=tuple(
                sorted(
                    account_bindings,
                    key=lambda item: (
                        normalize_key(item.channel_type),
                        normalize_identifier(item.channel_account_id),
                        item.runtime_id,
                    ),
                ),
            ),
        )

    def _bind_connection_in_registry(
        self,
        registry: ChannelRuntimeRegistry,
        binding: ChannelConnectionBinding,
    ) -> ChannelRuntimeRegistry:
        runtime = next(
            (item for item in registry.runtimes if item.runtime_id == binding.runtime_id),
            None,
        )
        if runtime is None:
            raise ChannelValidationError(
                f"runtime '{binding.runtime_id}' does not exist.",
            )
        if normalize_key(runtime.channel_type) != normalize_key(binding.channel_type):
            raise ChannelValidationError(
                "connection binding channel_type must match registered runtime channel_type.",
            )
        connection_bindings = [
            item
            for item in registry.connection_bindings
            if not (
                normalize_key(item.channel_type) == normalize_key(binding.channel_type)
                and normalize_identifier(item.connection_id)
                == normalize_identifier(binding.connection_id)
            )
        ]
        connection_bindings.append(replace(binding, updated_at=utcnow()))
        return replace(
            registry,
            connection_bindings=tuple(
                sorted(
                    connection_bindings,
                    key=lambda item: (
                        normalize_key(item.channel_type),
                        normalize_identifier(item.connection_id),
                        item.runtime_id,
                    ),
                ),
            ),
        )
