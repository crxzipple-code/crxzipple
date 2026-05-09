from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from crxzipple.core.config import OpenApiCredentialBinding, OpenApiProviderSettings
from crxzipple.modules.access import AccessApplicationService
from crxzipple.modules.tool.domain.exceptions import ToolValidationError
from crxzipple.modules.tool.domain.value_objects import ToolParameter
from crxzipple.modules.tool.infrastructure.discovery.openapi import (
    OpenApiDiscoveryProvider,
    OpenApiOperation,
    OpenApiSecurityRequirement,
    OpenApiSecurityScheme,
)
from crxzipple.modules.tool.infrastructure.runtimes.openapi_remote import (
    _build_request,
    _resolve_secret_source,
)
from tests.unit.support import openapi_fixture_path


class OpenApiAccessTestCase(unittest.TestCase):
    def test_resolves_file_credential_source_through_injected_access_provider(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            credential_path = Path(tempdir) / "token.txt"
            credential_path.write_text("file-token\n", encoding="utf-8")

            resolved = _resolve_secret_source(
                f"file:{credential_path}",
                scheme_name="bearerAuth",
                operation=_operation(),
                credential_provider=AccessApplicationService(),
            )

        self.assertEqual(resolved, "file-token")

    def test_rejects_literal_sources_for_openapi_credentials(self) -> None:
        with self.assertRaises(ToolValidationError):
            _resolve_secret_source(
                "inline-token",
                scheme_name="bearerAuth",
                operation=_operation(),
                credential_provider=AccessApplicationService(),
            )

    def test_build_request_resolves_openapi_credentials_from_injected_provider(self) -> None:
        credential_provider = _FakeCredentialProvider("injected-openapi-token")
        operation = _operation(
            credential_bindings=(
                OpenApiCredentialBinding(
                    scheme_name="ApiKeyQuery",
                    source="env:OPENAPI_TOOL_TOKEN",
                ),
            ),
        )

        _url, query_items, _headers, _body = _build_request(
            operation,
            {"message": "hello"},
            credential_provider=credential_provider,
        )

        self.assertIn(("api_key", "injected-openapi-token"), query_items)
        self.assertEqual(len(credential_provider.calls), 1)
        binding, consumer = credential_provider.calls[0]
        self.assertEqual(binding.source_ref, "env:OPENAPI_TOOL_TOKEN")
        self.assertEqual(binding.source_type, "env")
        self.assertEqual(consumer.module, "tool")
        self.assertEqual(consumer.component, "openapi_remote")
        self.assertEqual(consumer.runtime_ref, "openapi.sample_api.echo_message")

    def test_openapi_discovery_projects_credentials_to_tool_access_requirements(self) -> None:
        provider = OpenApiDiscoveryProvider(
            OpenApiProviderSettings(
                name="sample_api",
                spec_location=openapi_fixture_path("sample_openapi.json"),
                base_url="https://api.example.test",
                credential_bindings=(
                    OpenApiCredentialBinding(
                        scheme_name="ApiKeyQuery",
                        source="env:SAMPLE_QUERY_KEY",
                    ),
                    OpenApiCredentialBinding(
                        scheme_name="BearerAuth",
                        source="env:SAMPLE_BEARER_TOKEN",
                    ),
                ),
            ),
        )

        specs = {spec.id: spec for spec in provider.discover_specs()}

        self.assertEqual(
            specs["sample_api.echo_message"].access_requirement_sets,
            (("env:SAMPLE_QUERY_KEY",),),
        )
        self.assertEqual(
            specs["sample_api.search_docs"].access_requirement_sets,
            (("env:SAMPLE_BEARER_TOKEN",),),
        )


class _FakeCredentialProvider:
    def __init__(self, credential: str) -> None:
        self.credential = credential
        self.calls = []

    def resolve_credential(self, binding, *, consumer, trace_context=None):  # noqa: ANN001, ANN201
        del trace_context
        self.calls.append((binding, consumer))
        return self.credential


def _operation(
    *,
    credential_bindings: tuple[OpenApiCredentialBinding, ...] = (),
) -> OpenApiOperation:
    return OpenApiOperation(
        provider_name="sample_api",
        tool_id="sample_api.echo_message",
        runtime_key="openapi.sample_api.echo_message",
        name="Echo Message",
        description="Echo a message.",
        method="POST",
        path_template="/echo/{message}",
        base_url="https://api.example.test",
        timeout_seconds=5,
        path_parameters=("message",),
        query_parameters=(),
        body_required=False,
        tags=(),
        parameters=(
            ToolParameter(name="message", data_type="string", required=True),
        ),
        security_schemes=(
            OpenApiSecurityScheme(
                name="ApiKeyQuery",
                scheme_type="apiKey",
                parameter_name="api_key",
                location="query",
            ),
        ),
        security_requirements=(
            OpenApiSecurityRequirement(
                scheme_names=("ApiKeyQuery",),
            ),
        ),
        credential_bindings=credential_bindings,
    )


if __name__ == "__main__":
    unittest.main()
