from __future__ import annotations

from dataclasses import replace

from crxzipple.modules.channels.application.ports import ChannelSystemConfigStore
from crxzipple.modules.channels.application.service_helpers import normalize_key
from crxzipple.modules.channels.domain import (
    ChannelProfile,
    ChannelSystemConfig,
    ChannelValidationError,
)


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
        normalized = normalize_key(channel_type)
        for profile in self.system_config_store.load().profiles:
            if normalize_key(profile.channel_type) == normalized:
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
                            normalize_key(item.channel_type): item
                            for item in config.profiles
                        },
                        normalize_key(profile.channel_type): profile,
                    }[key]
                    for key in sorted(
                        {
                            *(normalize_key(item.channel_type) for item in config.profiles),
                            normalize_key(profile.channel_type),
                        },
                    )
                ),
            ),
        )
        resolved = next(
            (
                item
                for item in updated.profiles
                if normalize_key(item.channel_type)
                == normalize_key(profile.channel_type)
            ),
            None,
        )
        if resolved is None:
            raise ChannelValidationError("channel profile upsert did not persist.")
        return resolved

    def set_profile_enabled(self, channel_type: str, *, enabled: bool) -> ChannelProfile:
        normalized = normalize_key(channel_type)
        if not normalized:
            raise ChannelValidationError("channel_type is required.")
        resolved: ChannelProfile | None = None

        def _mutate(config: ChannelSystemConfig) -> ChannelSystemConfig:
            nonlocal resolved
            profiles: list[ChannelProfile] = []
            for item in config.profiles:
                if normalize_key(item.channel_type) == normalized:
                    resolved = replace(item, enabled=enabled)
                    profiles.append(resolved)
                else:
                    profiles.append(item)
            return replace(config, profiles=tuple(profiles))

        self.system_config_store.update(_mutate)
        if resolved is None:
            raise ChannelValidationError(
                f"channel profile '{channel_type}' was not found.",
                code="channel_profile_not_found",
                details={"channel_type": channel_type},
            )
        return resolved

    def enable_profile(self, channel_type: str) -> ChannelProfile:
        return self.set_profile_enabled(channel_type, enabled=True)

    def disable_profile(self, channel_type: str) -> ChannelProfile:
        return self.set_profile_enabled(channel_type, enabled=False)

    def remove_profile(self, channel_type: str) -> ChannelSystemConfig:
        normalized = normalize_key(channel_type)
        return self.system_config_store.update(
            lambda config: replace(
                config,
                profiles=tuple(
                    item
                    for item in config.profiles
                    if normalize_key(item.channel_type) != normalized
                ),
            ),
        )
