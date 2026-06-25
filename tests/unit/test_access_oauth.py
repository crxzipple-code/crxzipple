from __future__ import annotations

import base64
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import json
import threading
import unittest
from urllib.parse import parse_qs, urlparse
from unittest.mock import patch

import requests

from crxzipple.modules.access.application import oauth_callback_listener as callback_module
from crxzipple.modules.access.application.oauth_contracts import AccessOAuthSetupResult
from crxzipple.modules.access.application.oauth_token_client import (
    AccessOAuthTokenEndpointError,
)
from crxzipple.modules.access.application.settings_config_views import (
    AccessSettingsConfigProvider,
)
from crxzipple.modules.access.infrastructure.oauth_tokens import OAuthTokenDocument
from crxzipple.interfaces.runtime_container import AppKey
from tests.unit.support import SqliteTestHarness


class _FakeOAuthResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        return dict(self._payload)


class AccessOAuthServiceTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.harness = SqliteTestHarness()
        self.harness.initialize_schema()
        self.container = self.harness.build_runtime_container()
        self.settings = self.container.require(AppKey.CORE_SETTINGS)
        self.settings_query_service = self.container.require(
            AppKey.SETTINGS_QUERY_SERVICE,
        )
        self.access_service = self.container.require(AppKey.ACCESS_SERVICE)
        self.access_governance_repository = self.container.require(
            AppKey.ACCESS_GOVERNANCE_REPOSITORY,
        )
        self.service = self.container.require(AppKey.ACCESS_OAUTH_SERVICE)

    def tearDown(self) -> None:
        self.harness.close()

    def test_oauth_setup_payload_redacts_secret_metadata(self) -> None:
        result = AccessOAuthSetupResult(
            session_id="oauthsetup-redaction",
            provider_id="example-oauth",
            flow_kind="browser_oauth",
            metadata={
                "code_verifier": "raw-verifier",
                "device_code": "raw-device-code",
                "access_token_hint": "raw-token",
                "safe_label": "visible",
            },
        )

        payload = result.to_payload()

        self.assertEqual(payload["metadata"]["code_verifier"], "[redacted]")
        self.assertEqual(payload["metadata"]["device_code"], "[redacted]")
        self.assertEqual(payload["metadata"]["access_token_hint"], "[redacted]")
        self.assertEqual(payload["metadata"]["safe_label"], "visible")

    def test_browser_oauth_setup_completes_account_and_binding(self) -> None:
        self.service.register_provider(
            provider_id="example-oauth",
            display_name="Example OAuth",
            authorization_url="https://auth.example.test/authorize",
            token_url="https://auth.example.test/token",
            client_id="example-client",
            callback_url="http://127.0.0.1:1455/callback",
            default_scopes=("profile", "tools:read"),
        )

        setup = self.service.begin_browser_setup(provider_id="example-oauth")
        session = self.access_governance_repository.get_setup_session(
            setup.session_id,
        )
        assert session is not None

        with patch(
            "crxzipple.modules.access.application.oauth_token_client.requests.post",
            return_value=_FakeOAuthResponse(
                {
                    "access_token": "oauth-access-token",
                    "refresh_token": "oauth-refresh-token",
                    "expires_in": 3600,
                    "scope": "profile",
                    "email": "operator@example.test",
                },
            ),
        ):
            result = self.service.complete_browser_setup(
                session_id=setup.session_id,
                code="oauth-code",
                state=str(session.metadata["state"]),
                account_id="example-oauth:operator",
                credential_binding_id="example-oauth-operator",
            )

        self.assertEqual(result.account.status, "active")
        self.assertEqual(result.credential_binding_id, "example-oauth-operator")
        self.assertEqual(
            result.to_payload()["scope_diff"],
            {
                "declared": ["profile", "tools:read"],
                "requested": ["profile", "tools:read"],
                "granted": ["profile"],
                "missing": ["tools:read"],
                "extra": [],
            },
        )
        config = AccessSettingsConfigProvider(
            self.settings_query_service,
            environment=self.settings.environment,
        ).view()
        binding = config.get_credential_binding("example-oauth-operator")
        self.assertIsNotNone(binding)
        assert binding is not None
        self.assertEqual(binding.binding_kind, "oauth2_account")
        self.assertEqual(binding.source_kind, "oauth_account")
        self.assertEqual(binding.source_ref, "example-oauth:operator")

        self.access_service.config_view = config
        self.assertEqual(
            self.access_service.resolve_credential("example-oauth-operator"),
            "oauth-access-token",
        )

    def test_refresh_account_updates_token_and_account_metadata(self) -> None:
        self.service.register_provider(
            provider_id="refresh-oauth",
            display_name="Refresh OAuth",
            authorization_url="https://auth.example.test/authorize",
            token_url="https://auth.example.test/token",
            client_id="refresh-client",
            callback_url="http://127.0.0.1:1455/callback",
            default_scopes=("profile",),
        )
        setup = self.service.begin_browser_setup(provider_id="refresh-oauth")
        session = self.access_governance_repository.get_setup_session(setup.session_id)
        assert session is not None
        with patch(
            "crxzipple.modules.access.application.oauth_token_client.requests.post",
            return_value=_FakeOAuthResponse(
                {
                    "access_token": "old-access-token",
                    "refresh_token": "old-refresh-token",
                    "expires_in": 30,
                    "scope": "profile",
                    "email": "refresh@example.test",
                },
            ),
        ):
            self.service.complete_browser_setup(
                session_id=setup.session_id,
                code="oauth-code",
                state=str(session.metadata["state"]),
                account_id="refresh-oauth:operator",
                credential_binding_id="refresh-oauth-operator",
            )

        with patch(
            "crxzipple.modules.access.application.oauth_token_client.requests.post",
            return_value=_FakeOAuthResponse(
                {
                    "access_token": "new-access-token",
                    "refresh_token": "new-refresh-token",
                    "expires_in": 3600,
                    "scope": "profile tools:read",
                },
            ),
        ) as post:
            refreshed = self.service.refresh_account("refresh-oauth:operator")

        self.assertEqual(refreshed.account.masked_preview, "new-...oken")
        self.assertEqual(refreshed.account.granted_scopes, ("profile", "tools:read"))
        self.assertTrue(refreshed.account.refresh_ready)
        self.assertIn("last_refresh_at", refreshed.account.metadata)
        self.assertEqual(post.call_args.kwargs["data"]["grant_type"], "refresh_token")
        self.assertEqual(post.call_args.kwargs["data"]["refresh_token"], "old-refresh-token")
        token_store = self.container.require(AppKey.ACCESS_OAUTH_TOKEN_STORE)
        stored = token_store.read_token(refreshed.account.storage_key or "")
        self.assertEqual(stored.access_token, "new-access-token")

    def test_refresh_account_failure_redacts_refresh_token(self) -> None:
        self.service.register_provider(
            provider_id="refresh-failure-oauth",
            display_name="Refresh Failure OAuth",
            authorization_url="https://auth.example.test/authorize",
            token_url="https://auth.example.test/token",
            client_id="refresh-failure-client",
            callback_url="http://127.0.0.1:1455/callback",
            default_scopes=("profile",),
        )
        setup = self.service.begin_browser_setup(provider_id="refresh-failure-oauth")
        session = self.access_governance_repository.get_setup_session(setup.session_id)
        assert session is not None
        with patch(
            "crxzipple.modules.access.application.oauth_token_client.requests.post",
            return_value=_FakeOAuthResponse(
                {
                    "access_token": "old-access-token",
                    "refresh_token": "old-refresh-token",
                    "expires_in": 30,
                    "scope": "profile",
                    "email": "refresh-failure@example.test",
                },
            ),
        ):
            created = self.service.complete_browser_setup(
                session_id=setup.session_id,
                code="oauth-code",
                state=str(session.metadata["state"]),
                account_id="refresh-failure-oauth:operator",
                credential_binding_id="refresh-failure-oauth-operator",
            )

        self.service.token_client.retry_backoff_seconds = 0
        with (
            patch(
                "crxzipple.modules.access.application.oauth_token_client.requests.post",
                side_effect=requests.ConnectionError("old-refresh-token leaked"),
            ) as post,
            self.assertRaises(AccessOAuthTokenEndpointError) as context,
        ):
            self.service.refresh_account("refresh-failure-oauth:operator")

        self.assertEqual(post.call_count, 2)
        error_text = str(context.exception)
        self.assertIn("OAuth refresh token endpoint request failed", error_text)
        self.assertNotIn("old-refresh-token", error_text)
        self.assertNotIn("leaked", error_text)
        token_store = self.container.require(AppKey.ACCESS_OAUTH_TOKEN_STORE)
        stored = token_store.read_token(created.account.storage_key or "")
        self.assertEqual(stored.access_token, "old-access-token")

    def test_resolve_access_token_skips_duplicate_auto_refresh_after_locked_reread(
        self,
    ) -> None:
        self.service.register_provider(
            provider_id="refresh-lock-oauth",
            display_name="Refresh Lock OAuth",
            authorization_url="https://auth.example.test/authorize",
            token_url="https://auth.example.test/token",
            client_id="refresh-lock-client",
            callback_url="http://127.0.0.1:1455/callback",
            default_scopes=("profile",),
        )
        setup = self.service.begin_browser_setup(provider_id="refresh-lock-oauth")
        session = self.access_governance_repository.get_setup_session(setup.session_id)
        assert session is not None
        with patch(
            "crxzipple.modules.access.application.oauth_token_client.requests.post",
            return_value=_FakeOAuthResponse(
                {
                    "access_token": "old-access-token",
                    "refresh_token": "old-refresh-token",
                    "expires_in": 30,
                    "scope": "profile",
                    "email": "refresh-lock@example.test",
                },
            ),
        ):
            created = self.service.complete_browser_setup(
                session_id=setup.session_id,
                code="oauth-code",
                state=str(session.metadata["state"]),
                account_id="refresh-lock-oauth:operator",
                credential_binding_id="refresh-lock-oauth-operator",
            )

        token_store = self.container.require(AppKey.ACCESS_OAUTH_TOKEN_STORE)
        storage_key = created.account.storage_key or ""

        @contextmanager
        def refreshed_by_other_worker(_storage_key: str):
            token_store.write_token(
                storage_key,
                OAuthTokenDocument(
                    access_token="fresh-access-token",
                    refresh_token="old-refresh-token",
                    expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
                    scopes=("profile",),
                ),
            )
            yield

        with (
            patch.object(token_store, "token_lock", refreshed_by_other_worker),
            patch(
                "crxzipple.modules.access.application.oauth_token_client.AccessOAuthTokenClient.refresh_token",
            ) as refresh,
        ):
            resolved = self.service.resolve_access_token("refresh-lock-oauth:operator")

        self.assertEqual(resolved, "fresh-access-token")
        refresh.assert_not_called()

    def test_oauth_token_store_serializes_same_storage_key_lock(self) -> None:
        token_store = self.container.require(AppKey.ACCESS_OAUTH_TOKEN_STORE)
        storage_key = "oauth_tokens/lock-test.json"
        entered = threading.Event()

        def enter_same_lock() -> None:
            with token_store.token_lock(storage_key):
                entered.set()

        with token_store.token_lock(storage_key):
            thread = threading.Thread(target=enter_same_lock)
            thread.start()
            self.assertFalse(entered.wait(0.05))

        self.assertTrue(entered.wait(1.0))
        thread.join(timeout=1.0)
        self.assertFalse(thread.is_alive())

    def test_revoking_account_revokes_remote_token_and_deletes_storage(self) -> None:
        self.service.register_provider(
            provider_id="revoke-oauth",
            display_name="Revoke OAuth",
            authorization_url="https://auth.example.test/authorize",
            token_url="https://auth.example.test/token",
            revocation_url="https://auth.example.test/revoke",
            client_id="revoke-client",
            callback_url="http://127.0.0.1:1455/callback",
            default_scopes=("profile",),
        )
        setup = self.service.begin_browser_setup(provider_id="revoke-oauth")
        session = self.access_governance_repository.get_setup_session(setup.session_id)
        assert session is not None
        with patch(
            "crxzipple.modules.access.application.oauth_token_client.requests.post",
            return_value=_FakeOAuthResponse(
                {
                    "access_token": "revoked-access-token",
                    "refresh_token": "revoked-refresh-token",
                    "expires_in": 3600,
                    "scope": "profile",
                    "email": "revoke@example.test",
                },
            ),
        ):
            created = self.service.complete_browser_setup(
                session_id=setup.session_id,
                code="oauth-code",
                state=str(session.metadata["state"]),
                account_id="revoke-oauth:operator",
                credential_binding_id="revoke-oauth-operator",
            )

        with patch(
            "crxzipple.modules.access.application.oauth_token_client.requests.post",
            return_value=_FakeOAuthResponse({}),
        ) as post:
            revoked = self.service.set_account_status(
                "revoke-oauth:operator",
                status="revoked",
            )

        self.assertEqual(revoked.status, "revoked")
        self.assertEqual(post.call_args.args[0], "https://auth.example.test/revoke")
        self.assertEqual(post.call_args.kwargs["data"]["token"], "revoked-access-token")
        token_store = self.container.require(AppKey.ACCESS_OAUTH_TOKEN_STORE)
        with self.assertRaises(LookupError):
            token_store.read_token(created.account.storage_key or "")

    def test_revoking_account_retries_transient_failure_before_deleting_storage(self) -> None:
        self.service.register_provider(
            provider_id="revoke-retry-oauth",
            display_name="Revoke Retry OAuth",
            authorization_url="https://auth.example.test/authorize",
            token_url="https://auth.example.test/token",
            revocation_url="https://auth.example.test/revoke",
            client_id="revoke-retry-client",
            callback_url="http://127.0.0.1:1455/callback",
            default_scopes=("profile",),
        )
        setup = self.service.begin_browser_setup(provider_id="revoke-retry-oauth")
        session = self.access_governance_repository.get_setup_session(setup.session_id)
        assert session is not None
        with patch(
            "crxzipple.modules.access.application.oauth_token_client.requests.post",
            return_value=_FakeOAuthResponse(
                {
                    "access_token": "revoked-retry-access-token",
                    "refresh_token": "revoked-retry-refresh-token",
                    "expires_in": 3600,
                    "scope": "profile",
                    "email": "revoke-retry@example.test",
                },
            ),
        ):
            created = self.service.complete_browser_setup(
                session_id=setup.session_id,
                code="oauth-code",
                state=str(session.metadata["state"]),
                account_id="revoke-retry-oauth:operator",
                credential_binding_id="revoke-retry-oauth-operator",
            )

        self.service.token_client.retry_backoff_seconds = 0
        with patch(
            "crxzipple.modules.access.application.oauth_token_client.requests.post",
            side_effect=[
                requests.ConnectionError("revoked-retry-access-token leaked"),
                _FakeOAuthResponse({}),
            ],
        ) as post:
            revoked = self.service.set_account_status(
                "revoke-retry-oauth:operator",
                status="revoked",
            )

        self.assertEqual(post.call_count, 2)
        self.assertEqual(revoked.status, "revoked")
        token_store = self.container.require(AppKey.ACCESS_OAUTH_TOKEN_STORE)
        with self.assertRaises(LookupError):
            token_store.read_token(created.account.storage_key or "")

    def test_default_codex_provider_uses_builtin_oauth_flow(self) -> None:
        setup = self.service.begin_browser_setup(provider_id="openai-codex")

        parsed = urlparse(setup.authorize_url or "")
        params = parse_qs(parsed.query)

        self.assertEqual(parsed.scheme, "https")
        self.assertEqual(parsed.netloc, "auth.openai.com")
        self.assertEqual(parsed.path, "/oauth/authorize")
        self.assertEqual(params["client_id"], ["app_EMoamEEZ73f0CkXaXp7hrann"])
        self.assertEqual(params["redirect_uri"], ["http://localhost:1455/auth/callback"])
        self.assertEqual(params["scope"], ["openid profile email offline_access"])
        self.assertEqual(params["id_token_add_organizations"], ["true"])
        self.assertEqual(params["codex_cli_simplified_flow"], ["true"])
        self.assertEqual(params["originator"], ["pi"])
        self.assertEqual(setup.metadata["callback_mode"], "local_callback_or_manual")

    def test_codex_browser_oauth_completion_creates_account_binding(self) -> None:
        setup = self.service.begin_browser_setup(provider_id="openai-codex")
        session = self.access_governance_repository.get_setup_session(
            setup.session_id,
        )
        assert session is not None
        access_token = _jwt(
            {
                "https://api.openai.com/auth": {
                    "chatgpt_account_id": "acct_codex",
                },
                "https://api.openai.com/profile": {
                    "email": "operator@example.test",
                },
            },
        )

        with (
            patch(
                "crxzipple.modules.access.application.oauth_token_client.requests.post",
                return_value=_FakeOAuthResponse(
                    {
                        "access_token": access_token,
                        "refresh_token": "codex-refresh-token",
                        "expires_in": 3600,
                        "scope": "openid profile email offline_access",
                    },
                ),
            ),
        ):
            result = self.service.complete_browser_setup(
                session_id=setup.session_id,
                code="oauth-code",
                state=str(session.metadata["state"]),
                account_id="openai-codex:default",
                credential_binding_id="codex-oauth-default",
            )

        self.assertEqual(result.account.provider_id, "openai-codex")
        self.assertEqual(result.account.account_id, "openai-codex:default")
        self.assertEqual(result.account.subject, "operator@example.test")
        self.assertEqual(result.credential_binding_id, "codex-oauth-default")
        self.access_service.config_view = AccessSettingsConfigProvider(
            self.settings_query_service,
            environment=self.settings.environment,
        ).view()
        self.assertEqual(
            self.access_service.resolve_credential("codex-oauth-default"),
            access_token,
        )

    def test_begin_codex_oauth_login_starts_callback_listener_and_browser(self) -> None:
        with (
            patch(
                "crxzipple.modules.access.application.oauth.start_codex_oauth_callback_listener",
                return_value={"status": "listening"},
            ),
            patch(
                "crxzipple.modules.access.application.oauth.open_browser_url",
                return_value=True,
            ) as open_browser,
        ):
            setup = self.service.begin_codex_oauth_login(
                account_id="openai-codex:default",
                credential_binding_id="codex-oauth-default",
            )

        self.assertEqual(setup.provider_id, "openai-codex")
        self.assertEqual(setup.metadata["callback_listener"], {"status": "listening"})
        self.assertEqual(setup.metadata["browser_opened"], True)
        open_browser.assert_called_once_with(setup.authorize_url)

    def test_codex_oauth_listener_supersedes_active_listener(self) -> None:
        class _FakeServer(callback_module.HTTPServer):
            def __init__(self) -> None:
                self.shutdown_called = False
                self.close_called = False

            def shutdown(self) -> None:
                self.shutdown_called = True

            def server_close(self) -> None:
                self.close_called = True

        old_setup = self.service.begin_browser_setup(provider_id="openai-codex")
        server = _FakeServer()
        completed = {"value": False}
        previous_active = callback_module._CODEX_OAUTH_CALLBACK_ACTIVE
        try:
            callback_module._CODEX_OAUTH_CALLBACK_ACTIVE = {
                "session_id": old_setup.session_id,
                "server": server,
                "completed": completed,
            }
            callback_module.stop_active_codex_oauth_callback_listener(
                service=self.service,
                reason=(
                    "OpenAI Codex OAuth callback listener was superseded by a "
                    "newer login."
                ),
                superseded_by_session_id="new-session",
            )
        finally:
            callback_module._CODEX_OAUTH_CALLBACK_ACTIVE = previous_active

        old_session = self.access_governance_repository.get_setup_session(
            old_setup.session_id,
        )
        assert old_session is not None
        self.assertEqual(old_session.status, "expired")
        self.assertEqual(old_session.metadata["superseded_by_session_id"], "new-session")
        self.assertEqual(
            old_session.metadata["callback_listener"],
            {"status": "superseded"},
        )
        self.assertTrue(completed["value"])
        self.assertTrue(server.shutdown_called)
        self.assertTrue(server.close_called)

    def test_device_code_setup_has_structured_unsupported_and_ready_entries(self) -> None:
        self.service.register_provider(
            provider_id="device-missing",
            display_name="Device Missing",
            authorization_url="https://auth.example.test/authorize",
            token_url="https://auth.example.test/token",
            client_id="example-client",
            default_scopes=("profile",),
        )
        unsupported = self.service.begin_device_code_setup(provider_id="device-missing")

        self.assertEqual(unsupported.flow_kind, "device_code")
        self.assertEqual(unsupported.status, "unsupported")
        self.assertEqual(unsupported.metadata["unsupported"], True)
        session = self.access_governance_repository.get_setup_session(
            unsupported.session_id,
        )
        assert session is not None
        self.assertEqual(session.status, "unsupported")
        self.assertEqual(session.flow_kind, "device_code")

        self.service.register_provider(
            provider_id="device-ready",
            display_name="Device Ready",
            device_code_url="https://auth.example.test/device",
            token_url="https://auth.example.test/token",
            client_id="example-client",
            default_scopes=("profile",),
        )
        with patch(
            "crxzipple.modules.access.application.oauth_token_client.requests.post",
            return_value=_FakeOAuthResponse(
                {
                    "device_code": "device-secret-code",
                    "user_code": "ABCD-EFGH",
                    "verification_uri": "https://auth.example.test/verify",
                    "expires_in": 600,
                    "interval": 5,
                },
            ),
        ) as post:
            ready = self.service.begin_device_code_setup(
                provider_id="device-ready",
                account_id="device-ready:operator",
                credential_binding_id="device-ready-operator",
            )

        self.assertEqual(ready.flow_kind, "device_code")
        self.assertEqual(ready.status, "waiting_for_user")
        self.assertEqual(ready.verification_url, "https://auth.example.test/verify")
        self.assertEqual(ready.user_code, "ABCD-EFGH")
        self.assertEqual(ready.metadata["ready"], True)
        self.assertEqual(
            post.call_args.kwargs["data"],
            {"client_id": "example-client", "scope": "profile"},
        )

    def test_device_code_setup_completes_account_and_binding(self) -> None:
        self.service.register_provider(
            provider_id="device-ready",
            display_name="Device Ready",
            device_code_url="https://auth.example.test/device",
            token_url="https://auth.example.test/token",
            client_id="example-client",
            default_scopes=("profile", "offline_access"),
        )

        with patch(
            "crxzipple.modules.access.application.oauth_token_client.requests.post",
            return_value=_FakeOAuthResponse(
                {
                    "device_code": "device-secret-code",
                    "user_code": "ABCD-EFGH",
                    "verification_uri_complete": "https://auth.example.test/verify?user_code=ABCD-EFGH",
                    "expires_in": 600,
                    "interval": 5,
                },
            ),
        ):
            setup = self.service.begin_device_code_setup(
                provider_id="device-ready",
                account_id="device-ready:operator",
                credential_binding_id="device-ready-operator",
            )

        session = self.access_governance_repository.get_setup_session(
            setup.session_id,
        )
        assert session is not None
        self.assertEqual(session.metadata["device_code"], "device-secret-code")

        with patch(
            "crxzipple.modules.access.application.oauth_token_client.requests.post",
            return_value=_FakeOAuthResponse(
                {
                    "access_token": "device-access-token",
                    "refresh_token": "device-refresh-token",
                    "expires_in": 3600,
                    "scope": "profile offline_access",
                    "email": "device@example.test",
                },
            ),
        ) as post:
            result = self.service.complete_setup_session(session_id=setup.session_id)

        self.assertEqual(result.account.account_id, "device-ready:operator")
        self.assertEqual(result.credential_binding_id, "device-ready-operator")
        self.assertEqual(result.account.status, "active")
        self.assertEqual(
            post.call_args.kwargs["data"]["grant_type"],
            "urn:ietf:params:oauth:grant-type:device_code",
        )
        config = AccessSettingsConfigProvider(
            self.settings_query_service,
            environment=self.settings.environment,
        ).view()
        binding = config.get_credential_binding("device-ready-operator")
        self.assertIsNotNone(binding)
        assert binding is not None
        self.assertEqual(binding.source_kind, "oauth_account")
        self.access_service.config_view = config
        self.assertEqual(
            self.access_service.resolve_credential("device-ready-operator"),
            "device-access-token",
        )


def _jwt(payload: dict[str, object]) -> str:
    header = {"alg": "none", "typ": "JWT"}
    return ".".join(
        (
            _b64_json(header),
            _b64_json(payload),
            "signature",
        ),
    )


def _b64_json(payload: dict[str, object]) -> str:
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


if __name__ == "__main__":
    unittest.main()
