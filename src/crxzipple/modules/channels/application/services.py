from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

from crxzipple.modules.channels.application.ports import (
    ChannelInteractionRegistryStore,
    ChannelRuntimeRegistryStore,
    ChannelSystemConfigStore,
)
from crxzipple.modules.channels.domain import (
    ChannelAccountRuntimeBinding,
    ChannelConnectionBinding,
    ChannelInteraction,
    ChannelInteractionRegistry,
    ChannelProfile,
    ChannelRuntimeRegistration,
    ChannelRuntimeRegistry,
    ChannelSystemConfig,
    ChannelValidationError,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_key(value: str) -> str:
    return value.strip().lower()


def _normalize_identifier(value: str) -> str:
    return value.strip()


class ChannelProfileApplicationService:
    def __init__(self, *, system_config_store: ChannelSystemConfigStore) -> None:
        self.system_config_store = system_config_store

    def get_system_config(self) -> ChannelSystemConfig:
        return self.system_config_store.load()

    def save_system_config(self, config: ChannelSystemConfig) -> ChannelSystemConfig:
        return self.system_config_store.save(config)

    def list_profiles(self) -> tuple[ChannelProfile, ...]:
        return self.system_config_store.load().profiles

    def get_profile(self, channel_type: str) -> ChannelProfile | None:
        normalized = _normalize_key(channel_type)
        for profile in self.system_config_store.load().profiles:
            if _normalize_key(profile.channel_type) == normalized:
                return profile
        return None

    def upsert_profile(self, profile: ChannelProfile) -> ChannelProfile:
        if not profile.channel_type.strip():
            raise ChannelValidationError("channel profile must include a channel_type.")
        updated = self.system_config_store.update(
            lambda config: replace(
                config,
                profiles=tuple(
                    {
                        **{
                            _normalize_key(item.channel_type): item
                            for item in config.profiles
                        },
                        _normalize_key(profile.channel_type): profile,
                    }[key]
                    for key in sorted(
                        {
                            *(
                                _normalize_key(item.channel_type)
                                for item in config.profiles
                            ),
                            _normalize_key(profile.channel_type),
                        },
                    )
                ),
            ),
        )
        resolved = next(
            (
                item
                for item in updated.profiles
                if _normalize_key(item.channel_type) == _normalize_key(profile.channel_type)
            ),
            None,
        )
        if resolved is None:
            raise ChannelValidationError("channel profile upsert did not persist.")
        return resolved

    def remove_profile(self, channel_type: str) -> ChannelSystemConfig:
        normalized = _normalize_key(channel_type)
        return self.system_config_store.update(
            lambda config: replace(
                config,
                profiles=tuple(
                    item
                    for item in config.profiles
                    if _normalize_key(item.channel_type) != normalized
                ),
            ),
        )


class ChannelInteractionService:
    def __init__(self, *, registry_store: ChannelInteractionRegistryStore) -> None:
        self.registry_store = registry_store

    def snapshot(self) -> ChannelInteractionRegistry:
        return self.registry_store.load()

    def list_interactions(
        self,
        *,
        channel_type: str | None = None,
        run_id: str | None = None,
        session_key: str | None = None,
    ) -> tuple[ChannelInteraction, ...]:
        interactions = self.registry_store.load().interactions
        if channel_type is not None:
            normalized_channel = _normalize_key(channel_type)
            interactions = tuple(
                item
                for item in interactions
                if _normalize_key(item.channel_type) == normalized_channel
            )
        if run_id is not None:
            normalized_run_id = _normalize_identifier(run_id)
            interactions = tuple(
                item
                for item in interactions
                if _normalize_identifier(item.run_id or "") == normalized_run_id
            )
        if session_key is not None:
            normalized_session_key = _normalize_identifier(session_key)
            interactions = tuple(
                item
                for item in interactions
                if _normalize_identifier(item.session_key or "") == normalized_session_key
            )
        return interactions

    def get_interaction(self, interaction_id: str) -> ChannelInteraction | None:
        normalized = _normalize_identifier(interaction_id)
        for interaction in self.registry_store.load().interactions:
            if interaction.interaction_id == normalized:
                return interaction
        return None

    def get_interaction_by_run_id(self, run_id: str) -> ChannelInteraction | None:
        normalized = _normalize_identifier(run_id)
        if not normalized:
            return None
        for interaction in self.registry_store.load().interactions:
            if _normalize_identifier(interaction.run_id or "") == normalized:
                return interaction
        return None

    def upsert_interaction(
        self,
        interaction: ChannelInteraction,
    ) -> ChannelInteraction:
        if not interaction.interaction_id.strip():
            raise ChannelValidationError("channel interaction must include interaction_id.")
        if not interaction.channel_type.strip():
            raise ChannelValidationError("channel interaction must include channel_type.")

        def _mutate(registry: ChannelInteractionRegistry) -> ChannelInteractionRegistry:
            existing = next(
                (
                    item
                    for item in registry.interactions
                    if item.interaction_id == interaction.interaction_id
                ),
                None,
            )
            updated_interaction = replace(
                interaction,
                created_at=existing.created_at if existing is not None else interaction.created_at,
                updated_at=_utcnow(),
            )
            interactions_by_id = {
                item.interaction_id: item
                for item in registry.interactions
            }
            interactions_by_id[updated_interaction.interaction_id] = updated_interaction
            return replace(
                registry,
                interactions=tuple(
                    interactions_by_id[key]
                    for key in sorted(interactions_by_id)
                ),
            )

        registry = self.registry_store.update(_mutate)
        resolved = next(
            (
                item
                for item in registry.interactions
                if item.interaction_id == interaction.interaction_id
            ),
            None,
        )
        if resolved is None:
            raise ChannelValidationError("channel interaction upsert did not persist.")
        return resolved

    def bind_run(
        self,
        interaction_id: str,
        *,
        run_id: str,
        session_key: str | None = None,
        agent_id: str | None = None,
        status: str = "submitted",
        metadata: dict[str, object] | None = None,
    ) -> ChannelInteraction | None:
        normalized_interaction_id = _normalize_identifier(interaction_id)
        normalized_run_id = _normalize_identifier(run_id)
        if not normalized_interaction_id:
            raise ChannelValidationError("interaction_id is required to bind a run.")
        if not normalized_run_id:
            raise ChannelValidationError("run_id is required to bind a run.")
        found = False

        def _mutate(registry: ChannelInteractionRegistry) -> ChannelInteractionRegistry:
            nonlocal found
            interactions: list[ChannelInteraction] = []
            for item in registry.interactions:
                if item.interaction_id == normalized_interaction_id:
                    found = True
                    interactions.append(
                        replace(
                            item,
                            run_id=normalized_run_id,
                            session_key=(
                                _normalize_identifier(session_key)
                                if isinstance(session_key, str) and session_key.strip()
                                else item.session_key
                            ),
                            agent_id=(
                                _normalize_identifier(agent_id)
                                if isinstance(agent_id, str) and agent_id.strip()
                                else item.agent_id
                            ),
                            status=_normalize_identifier(status) or item.status,
                            metadata={
                                **dict(item.metadata),
                                **dict(metadata or {}),
                            },
                            updated_at=_utcnow(),
                        )
                    )
                else:
                    interactions.append(item)
            if not found:
                return registry
            return replace(registry, interactions=tuple(interactions))

        registry = self.registry_store.update(_mutate)
        if not found:
            return None
        return next(
            (
                item
                for item in registry.interactions
                if item.interaction_id == normalized_interaction_id
            ),
            None,
        )

    def bind_run_by_run_id(
        self,
        run_id: str,
        *,
        session_key: str | None = None,
        agent_id: str | None = None,
        status: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> tuple[ChannelInteraction, ...]:
        normalized_run_id = _normalize_identifier(run_id)
        if not normalized_run_id:
            raise ChannelValidationError("run_id is required to bind channel interactions.")
        normalized_status = (
            _normalize_identifier(status)
            if isinstance(status, str) and status.strip()
            else None
        )
        updated_ids: list[str] = []

        def _mutate(registry: ChannelInteractionRegistry) -> ChannelInteractionRegistry:
            interactions: list[ChannelInteraction] = []
            for item in registry.interactions:
                if _normalize_identifier(item.run_id or "") != normalized_run_id:
                    interactions.append(item)
                    continue
                updated = replace(
                    item,
                    session_key=(
                        _normalize_identifier(session_key)
                        if isinstance(session_key, str) and session_key.strip()
                        else item.session_key
                    ),
                    agent_id=(
                        _normalize_identifier(agent_id)
                        if isinstance(agent_id, str) and agent_id.strip()
                        else item.agent_id
                    ),
                    status=normalized_status or item.status,
                    metadata={
                        **dict(item.metadata),
                        **dict(metadata or {}),
                    },
                    updated_at=_utcnow(),
                )
                updated_ids.append(updated.interaction_id)
                interactions.append(updated)
            if not updated_ids:
                return registry
            return replace(registry, interactions=tuple(interactions))

        registry = self.registry_store.update(_mutate)
        if not updated_ids:
            return ()
        updated_id_set = set(updated_ids)
        return tuple(
            item
            for item in registry.interactions
            if item.interaction_id in updated_id_set
        )

    def mark_status(
        self,
        interaction_id: str,
        *,
        status: str,
        last_error: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> ChannelInteraction | None:
        normalized_interaction_id = _normalize_identifier(interaction_id)
        normalized_status = _normalize_identifier(status)
        if not normalized_interaction_id:
            raise ChannelValidationError("interaction_id is required to update interaction status.")
        if not normalized_status:
            raise ChannelValidationError("status is required to update interaction status.")
        found = False

        def _mutate(registry: ChannelInteractionRegistry) -> ChannelInteractionRegistry:
            nonlocal found
            interactions: list[ChannelInteraction] = []
            for item in registry.interactions:
                if item.interaction_id == normalized_interaction_id:
                    found = True
                    interactions.append(
                        replace(
                            item,
                            status=normalized_status,
                            last_error=last_error,
                            metadata={
                                **dict(item.metadata),
                                **dict(metadata or {}),
                            },
                            updated_at=_utcnow(),
                        )
                    )
                else:
                    interactions.append(item)
            if not found:
                return registry
            return replace(registry, interactions=tuple(interactions))

        registry = self.registry_store.update(_mutate)
        if not found:
            return None
        return next(
            (
                item
                for item in registry.interactions
                if item.interaction_id == normalized_interaction_id
            ),
            None,
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
        normalized = _normalize_key(channel_type)
        return tuple(
            item
            for item in registry.runtimes
            if _normalize_key(item.channel_type) == normalized
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
            (item for item in registry.runtimes if item.runtime_id == registration.runtime_id),
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
                    runtimes.append(replace(item, last_heartbeat_at=_utcnow()))
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
                                _utcnow() if touch_heartbeat else item.last_heartbeat_at
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
                    _normalize_key(item.channel_type) == _normalize_key(binding.channel_type)
                    and _normalize_identifier(item.channel_account_id)
                    == _normalize_identifier(binding.channel_account_id)
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
        normalized_channel = _normalize_key(channel_type)
        normalized_account = _normalize_identifier(channel_account_id)
        for item in self.registry_store.load().account_bindings:
            if (
                _normalize_key(item.channel_type) == normalized_channel
                and _normalize_identifier(item.channel_account_id) == normalized_account
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
            normalized = _normalize_key(channel_type)
            bindings = tuple(
                item
                for item in bindings
                if _normalize_key(item.channel_type) == normalized
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
                    _normalize_key(item.channel_type) == _normalize_key(binding.channel_type)
                    and _normalize_identifier(item.connection_id)
                    == _normalize_identifier(binding.connection_id)
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
            _normalize_identifier(conversation_id)
            if isinstance(conversation_id, str) and _normalize_identifier(conversation_id)
            else None
        )
        current_conversation_id = (
            _normalize_identifier(binding.conversation_id)
            if isinstance(binding.conversation_id, str)
            and _normalize_identifier(binding.conversation_id)
            else None
        )
        metadata = dict(binding.metadata)
        if current_conversation_id != normalized_conversation_id:
            metadata.pop("observe_cursor", None)
            metadata.pop("live_cursor", None)
            metadata["observe_subscription_updated_at"] = _utcnow().isoformat()
        return self.bind_connection(
            replace(
                binding,
                conversation_id=normalized_conversation_id,
                metadata=metadata,
                updated_at=_utcnow(),
            ),
        )

    def merge_connection_metadata(
        self,
        *,
        channel_type: str,
        connection_id: str,
        metadata: dict[str, Any],
    ) -> ChannelConnectionBinding | None:
        normalized_channel = _normalize_key(channel_type)
        normalized_connection = _normalize_identifier(connection_id)
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
                        updated_at=_utcnow(),
                    )
                    if (
                        _normalize_key(item.channel_type) == normalized_channel
                        and _normalize_identifier(item.connection_id)
                        == normalized_connection
                    )
                    else item
                    for item in registry.connection_bindings
                ),
            ),
        )
        for item in saved.connection_bindings:
            if (
                _normalize_key(item.channel_type) == normalized_channel
                and _normalize_identifier(item.connection_id) == normalized_connection
            ):
                return item
        return None

    def resolve_connection_binding(
        self,
        *,
        channel_type: str,
        connection_id: str,
    ) -> ChannelConnectionBinding | None:
        normalized_channel = _normalize_key(channel_type)
        normalized_connection = _normalize_identifier(connection_id)
        for item in self.registry_store.load().connection_bindings:
            if (
                _normalize_key(item.channel_type) == normalized_channel
                and _normalize_identifier(item.connection_id) == normalized_connection
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
            normalized = _normalize_key(channel_type)
            bindings = tuple(
                item
                for item in bindings
                if _normalize_key(item.channel_type) == normalized
            )
        return bindings

    def unbind_connection(
        self,
        *,
        channel_type: str,
        connection_id: str,
    ) -> ChannelRuntimeRegistry:
        normalized_channel = _normalize_key(channel_type)
        normalized_connection = _normalize_identifier(connection_id)
        return self.registry_store.update(
            lambda registry: replace(
                registry,
                connection_bindings=tuple(
                    item
                    for item in registry.connection_bindings
                    if not (
                        _normalize_key(item.channel_type) == normalized_channel
                        and _normalize_identifier(item.connection_id)
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
        if _normalize_key(runtime.channel_type) != _normalize_key(binding.channel_type):
            raise ChannelValidationError(
                "account binding channel_type must match registered runtime channel_type.",
            )
        account_bindings = [
            item
            for item in registry.account_bindings
            if not (
                _normalize_key(item.channel_type) == _normalize_key(binding.channel_type)
                and _normalize_identifier(item.channel_account_id)
                == _normalize_identifier(binding.channel_account_id)
            )
        ]
        account_bindings.append(replace(binding, updated_at=_utcnow()))
        return replace(
            registry,
            account_bindings=tuple(
                sorted(
                    account_bindings,
                    key=lambda item: (
                        _normalize_key(item.channel_type),
                        _normalize_identifier(item.channel_account_id),
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
        if _normalize_key(runtime.channel_type) != _normalize_key(binding.channel_type):
            raise ChannelValidationError(
                "connection binding channel_type must match registered runtime channel_type.",
            )
        connection_bindings = [
            item
            for item in registry.connection_bindings
            if not (
                _normalize_key(item.channel_type) == _normalize_key(binding.channel_type)
                and _normalize_identifier(item.connection_id)
                == _normalize_identifier(binding.connection_id)
            )
        ]
        connection_bindings.append(replace(binding, updated_at=_utcnow()))
        return replace(
            registry,
            connection_bindings=tuple(
                sorted(
                    connection_bindings,
                    key=lambda item: (
                        _normalize_key(item.channel_type),
                        _normalize_identifier(item.connection_id),
                        item.runtime_id,
                    ),
                ),
            ),
        )
