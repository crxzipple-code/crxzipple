from __future__ import annotations

from types import SimpleNamespace

from crxzipple.modules.access.application.query import AccessControlPlaneQueryProvider
from crxzipple.modules.access.application.repositories import (
    AccessCredentialBindingRecord,
)
from crxzipple.modules.access.interfaces.external_consumers import (
    external_access_consumer_bindings,
)


class _BrowserProfiles:
    def list_profiles(self):
        return (
            SimpleNamespace(
                name="work",
                proxy_mode="access_binding",
                proxy_binding_id="proxy-basic",
                proxy_credential_kind="basic",
            ),
            SimpleNamespace(
                name="bearer",
                proxy_mode="access_binding",
                proxy_binding_id="proxy-bearer",
                proxy_credential_kind="bearer_token",
            ),
            SimpleNamespace(
                name="plain",
                proxy_mode="none",
                proxy_binding_id=None,
            ),
        )


class _Container:
    def require(self, key: str):  # noqa: ANN201
        if key == "browser.query_service":
            return _BrowserProfiles()
        raise KeyError(key)


class _SettingsConfigProvider:
    def __init__(self, *, credential_bindings=()) -> None:  # noqa: ANN001
        self._view = SimpleNamespace(
            list_assets=lambda: (),
            list_credential_bindings=lambda: tuple(credential_bindings),
            list_consumer_bindings=lambda: (),
        )

    def view(self) -> object:
        return self._view


class _EmptyAccessRepository:
    def list_readiness_snapshots(self) -> tuple[object, ...]:
        return ()

    def list_setup_sessions(self) -> tuple[object, ...]:
        return ()


def test_browser_access_binding_proxy_is_external_access_consumer() -> None:
    consumers = external_access_consumer_bindings(_Container())

    assert len(consumers) == 2
    consumer = consumers[0]
    assert consumer.consumer_module == "browser"
    assert consumer.consumer_kind == "browser_profile_proxy"
    assert consumer.consumer_id == "browser.profile:work:proxy"
    assert consumer.credential_bindings == {"proxy": "proxy-basic"}
    assert consumer.requirement_sets == (("browser_proxy:basic(proxy)",),)
    bearer = consumers[1]
    assert bearer.credential_bindings == {"proxy": "proxy-bearer"}
    assert bearer.requirement_sets == (("browser_proxy:bearer_token(proxy)",),)


def test_access_query_projects_browser_proxy_requirement_readiness() -> None:
    provider = AccessControlPlaneQueryProvider(
        governance_repository=_EmptyAccessRepository(),
        settings_config_provider=_SettingsConfigProvider(
            credential_bindings=(
                AccessCredentialBindingRecord(
                    binding_id="proxy-basic",
                    asset_id="asset:proxy",
                    binding_kind="basic",
                    source_kind="env",
                    source_ref="BROWSER_PROXY_AUTH",
                    masked_preview="env:BROWSER_PROXY_AUTH",
                ),
                AccessCredentialBindingRecord(
                    binding_id="proxy-bearer",
                    asset_id="asset:proxy-bearer",
                    binding_kind="bearer_token",
                    source_kind="env",
                    source_ref="BROWSER_PROXY_TOKEN",
                    masked_preview="env:BROWSER_PROXY_TOKEN",
                ),
            ),
        ),
        external_consumer_binding_provider=lambda: external_access_consumer_bindings(
            _Container(),
        ),
    )

    payload = provider.credential_requirements().to_payload()

    assert len(payload["credential_requirements"]) == 2
    row = payload["credential_requirements"][0]
    assert row["consumer_module"] == "browser"
    assert row["slot"] == "proxy"
    assert row["expected_kind"] == "basic"
    assert row["binding_id"] == "proxy-basic"
    assert row["ready"] is True
    bearer = payload["credential_requirements"][1]
    assert bearer["expected_kind"] == "bearer_token"
    assert bearer["binding_id"] == "proxy-bearer"
    assert bearer["ready"] is True
