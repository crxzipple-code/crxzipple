from __future__ import annotations

from dataclasses import dataclass

from crxzipple.modules.access.application.ports import AccessSettingsQueryPort
from crxzipple.modules.access.application.repositories import (
    AccessAssetRecord,
    AccessConsumerBindingRecord,
    AccessCredentialBindingRecord,
)
from crxzipple.modules.access.application.settings_record_models import (
    _asset_record,
    _consumer_binding_record,
    _credential_binding_record,
)
from crxzipple.modules.settings.application.materialization import (
    SettingsEffectiveConfigMaterializer,
)
from crxzipple.shared.settings import AccessConfig


@dataclass(slots=True)
class AccessSettingsConfigView:
    configs: tuple[AccessConfig, ...]

    def list_assets(self) -> tuple[AccessAssetRecord, ...]:
        return tuple(
            _asset_record(item)
            for config in self.configs
            if config.enabled
            for item in config.assets
        )

    def list_credential_bindings(self) -> tuple[AccessCredentialBindingRecord, ...]:
        return tuple(
            _credential_binding_record(item)
            for config in self.configs
            if config.enabled
            for item in config.credential_bindings
        )

    def get_credential_binding(
        self,
        binding_id: str,
    ) -> AccessCredentialBindingRecord | None:
        normalized = binding_id.strip()
        return next(
            (
                item
                for item in self.list_credential_bindings()
                if item.binding_id == normalized
            ),
            None,
        )

    def get_consumer_binding(
        self,
        binding_id: str,
    ) -> AccessConsumerBindingRecord | None:
        normalized = binding_id.strip()
        return next(
            (
                item
                for item in self.list_consumer_bindings()
                if item.binding_id == normalized
            ),
            None,
        )

    def list_consumer_bindings(self) -> tuple[AccessConsumerBindingRecord, ...]:
        return tuple(
            _consumer_binding_record(item)
            for config in self.configs
            if config.enabled
            for item in config.consumer_bindings
        )


@dataclass(slots=True)
class AccessSettingsConfigProvider:
    query_service: AccessSettingsQueryPort | None
    environment: str | None = None

    def view(self) -> AccessSettingsConfigView:
        if self.query_service is None:
            return AccessSettingsConfigView(configs=())
        materializer = SettingsEffectiveConfigMaterializer(
            self.query_service,
            environment=self.environment,
        )
        return AccessSettingsConfigView(configs=materializer.access_configs())

    def get_credential_binding(
        self,
        binding_id: str,
    ) -> AccessCredentialBindingRecord | None:
        return self.view().get_credential_binding(binding_id)

    def get_consumer_binding(
        self,
        binding_id: str,
    ) -> AccessConsumerBindingRecord | None:
        return self.view().get_consumer_binding(binding_id)

    def list_assets(self) -> tuple[AccessAssetRecord, ...]:
        return self.view().list_assets()

    def list_credential_bindings(self) -> tuple[AccessCredentialBindingRecord, ...]:
        return self.view().list_credential_bindings()

    def list_consumer_bindings(self) -> tuple[AccessConsumerBindingRecord, ...]:
        return self.view().list_consumer_bindings()
