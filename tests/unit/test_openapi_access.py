from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from crxzipple.core.config import OpenApiCredentialBinding, OpenApiProviderSettings
from crxzipple.modules.tool.application.catalog_models import ToolFunctionCandidate
from crxzipple.modules.tool.domain.exceptions import ToolValidationError
from crxzipple.modules.tool.domain.value_objects import ToolParameter
from crxzipple.modules.tool.infrastructure.discovery.openapi import (
    OpenApiDiscoveryProvider,
    OpenApiOperation,
    OpenApiSecurityRequirement,
    OpenApiSecurityScheme,
)
from crxzipple.modules.tool.infrastructure.runtimes.openapi_remote_requests import (
    build_request as _build_request,
)
from crxzipple.modules.tool.infrastructure.runtimes.openapi_remote_results import (
    openapi_result_details as _openapi_result_details,
    openapi_result_text as _openapi_result_text,
)
from crxzipple.modules.tool.infrastructure.runtimes.openapi_remote_security import (
    resolve_credential_binding as _resolve_credential_binding,
)
from crxzipple.shared.access import AccessCredentialKind
from tests.unit.support import openapi_fixture_path


class OpenApiAccessTestCase(unittest.TestCase):
    def test_resolves_access_binding_id_through_injected_access_provider(self) -> None:
        credential_provider = _FakeCredentialProvider("access-token")

        resolved = _resolve_credential_binding(
            "binding.openapi.token",
            scheme_name="bearerAuth",
            operation=_operation(),
            credential_provider=credential_provider,
        )

        self.assertEqual(resolved, "access-token")
        binding, _consumer = credential_provider.calls[0]
        self.assertEqual(binding.binding_id, "binding.openapi.token")
        self.assertEqual(binding.source_ref, "binding.openapi.token")
        self.assertEqual(binding.source_type, "binding")

    def test_rejects_missing_openapi_credential_binding_id(self) -> None:
        with self.assertRaises(ToolValidationError):
            _resolve_credential_binding(
                None,
                scheme_name="bearerAuth",
                operation=_operation(),
                credential_provider=_FakeCredentialProvider("unused"),
            )

    def test_build_request_resolves_openapi_credentials_from_injected_provider(self) -> None:
        credential_provider = _FakeCredentialProvider("injected-openapi-token")
        operation = _operation(
            credential_bindings=(
                OpenApiCredentialBinding(
                    scheme_name="ApiKeyQuery",
                    credential_binding_id="binding.openapi.query",
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
        self.assertEqual(binding.source_ref, "binding.openapi.query")
        self.assertEqual(binding.source_type, "binding")
        self.assertEqual(binding.expected_kind, AccessCredentialKind.API_KEY)
        self.assertEqual(consumer.module, "tool")
        self.assertEqual(consumer.component, "openapi_remote")
        self.assertEqual(consumer.runtime_ref, "openapi.sample_api.echo_message")

    def test_build_request_normalizes_openapi_parameter_aliases(self) -> None:
        operation = OpenApiOperation(
            provider_name="brave_search",
            tool_id="brave_search.web_search",
            runtime_key="openapi.brave_search.web_search",
            name="Search",
            description="Search.",
            method="GET",
            path_template="/res/v1/web/search",
            base_url="https://api.search.brave.com",
            timeout_seconds=5,
            path_parameters=(),
            query_parameters=("q", "search_lang", "ui_lang"),
            body_required=False,
            tags=(),
            parameters=(
                ToolParameter(name="q", data_type="string", required=True),
                ToolParameter(
                    name="search_lang",
                    data_type="string",
                    required=False,
                    json_schema={
                        "type": "string",
                        "enum": ["en", "zh-hans", "zh-hant"],
                    },
                ),
                ToolParameter(
                    name="ui_lang",
                    data_type="string",
                    required=False,
                    json_schema={
                        "type": "string",
                        "enum": ["en-US", "zh-CN", "zh-TW"],
                    },
                ),
            ),
        )

        _url, query_items, _headers, _body = _build_request(
            operation,
            {"q": "黄金", "search_lang": "zh-cn", "ui_lang": "zh-cn"},
            credential_provider=_FakeCredentialProvider("unused"),
        )

        self.assertIn(("search_lang", "zh-hans"), query_items)
        self.assertIn(("ui_lang", "zh-CN"), query_items)

    def test_build_request_rejects_openapi_enum_values_locally(self) -> None:
        operation = OpenApiOperation(
            provider_name="search_api",
            tool_id="search_api.web_search",
            runtime_key="openapi.search_api.web_search",
            name="Search",
            description="Search.",
            method="GET",
            path_template="/search",
            base_url="https://api.example.test",
            timeout_seconds=5,
            path_parameters=(),
            query_parameters=("search_lang",),
            body_required=False,
            tags=(),
            parameters=(
                ToolParameter(
                    name="search_lang",
                    data_type="string",
                    required=False,
                    json_schema={"type": "string", "enum": ["en", "zh-hans"]},
                ),
            ),
        )

        with self.assertRaises(ToolValidationError):
            _build_request(
                operation,
                {"search_lang": "klingon"},
                credential_provider=_FakeCredentialProvider("unused"),
            )

    def test_openapi_result_details_compacts_oversized_remote_payload(self) -> None:
        payload = {
            "web": {
                "results": [
                    {
                        "title": f"result {index}",
                        "url": f"https://example.test/{index}",
                        "description": "x" * 400,
                        "extra_snippets": ["y" * 300 for _ in range(5)],
                    }
                    for index in range(500)
                ],
            },
        }

        details = _openapi_result_details(payload)

        self.assertLess(
            len(json.dumps(details, ensure_ascii=False, separators=(",", ":"))),
            131072,
        )
        self.assertTrue(details["details_compacted"])
        self.assertEqual(
            details["web"]["results"][-1]["items_omitted_from_details"],
            460,
        )

    def test_openapi_result_text_summarizes_weather_hourly_arrays(self) -> None:
        payload = {
            "current": {
                "time": "2026-06-10T10:00",
                "temperature_2m": 18.5,
                "weather_code": 3,
            },
            "hourly_units": {
                "temperature_2m": "°C",
                "precipitation_probability": "%",
            },
            "hourly": {
                "time": [f"2026-06-10T{hour:02d}:00" for hour in range(24)],
                "temperature_2m": [
                    14,
                    14.2,
                    14.4,
                    14.9,
                    15.2,
                    15.8,
                    16,
                    16.7,
                    17.1,
                    17.8,
                    18.4,
                    18.9,
                    19.3,
                    20,
                    20.4,
                    20.1,
                    19.8,
                    19.1,
                    18.5,
                    17.8,
                    17.1,
                    16.4,
                    15.7,
                    15,
                ],
                "precipitation_probability": [
                    10,
                    10,
                    12,
                    15,
                    18,
                    20,
                    50,
                    55,
                    58,
                    60,
                    62,
                    64,
                    66,
                    68,
                    78,
                    72,
                    66,
                    60,
                    54,
                    48,
                    42,
                    36,
                    30,
                    24,
                ],
                "weather_code": [3] * 24,
            },
        }

        text = _openapi_result_text(_operation(), payload)

        self.assertIn("Weather forecast summary:", text)
        self.assertIn("2026-06-10T06:00", text)
        self.assertIn("precipitation_probability=50%", text)
        self.assertIn("2026-06-10T12:00", text)
        self.assertIn("Highest precipitation probability: 78% at 2026-06-10T14:00", text)
        self.assertIn("Raw response:", text)

    def test_openapi_discovery_projects_credentials_to_tool_access_requirements(self) -> None:
        provider = OpenApiDiscoveryProvider(
            OpenApiProviderSettings(
                name="sample_api",
                spec_location=openapi_fixture_path("sample_openapi.json"),
                base_url="https://api.example.test",
                credential_bindings=(
                    OpenApiCredentialBinding(
                        scheme_name="ApiKeyQuery",
                        credential_binding_id="binding.sample.query",
                    ),
                    OpenApiCredentialBinding(
                        scheme_name="BearerAuth",
                        credential_binding_id="binding.sample.bearer",
                    ),
                ),
            ),
        )

        specs = {spec.id: spec for spec in provider.discover_specs()}

        self.assertEqual(
            specs["sample_api.echo_message"].access_requirement_sets,
            (("binding.sample.query",),),
        )
        self.assertEqual(
            specs["sample_api.search_docs"].access_requirement_sets,
            (("binding.sample.bearer",),),
        )
        echo_requirement = specs[
            "sample_api.echo_message"
        ].credential_requirements[0].requirements[0]
        self.assertEqual(echo_requirement.slot.slot, "ApiKeyQuery")
        self.assertEqual(echo_requirement.slot.binding_id, "binding.sample.query")
        self.assertEqual(echo_requirement.slot.expected_kind.value, "api_key")
        self.assertEqual(echo_requirement.transport.value, "query")
        self.assertEqual(echo_requirement.parameter_name, "api_key")

        search_requirement = specs[
            "sample_api.search_docs"
        ].credential_requirements[0].requirements[0]
        self.assertEqual(search_requirement.slot.slot, "BearerAuth")
        self.assertEqual(search_requirement.slot.binding_id, "binding.sample.bearer")
        self.assertEqual(search_requirement.slot.expected_kind.value, "bearer_token")
        self.assertEqual(search_requirement.transport.value, "oauth_authorization_header")

    def test_openapi_discovery_preserves_parameter_schema_constraints(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            spec_path = Path(tempdir) / "search.json"
            spec_path.write_text(
                """
                {
                  "openapi": "3.0.3",
                  "info": {"title": "Search API", "version": "1.0.0"},
                  "servers": [{"url": "https://search.example.test"}],
                  "paths": {
                    "/search": {
                      "get": {
                        "operationId": "web_search",
                        "parameters": [
                          {
                            "name": "search_lang",
                            "in": "query",
                            "required": false,
                            "description": "Content language.",
                            "schema": {
                              "type": "string",
                              "enum": ["en", "zh-hans", "zh-hant"],
                              "default": "zh-hans"
                            }
                          }
                        ],
                        "responses": {"200": {"description": "ok"}}
                      }
                    }
                  }
                }
                """,
                encoding="utf-8",
            )
            provider = OpenApiDiscoveryProvider(
                OpenApiProviderSettings(
                    name="search_api",
                    spec_location=str(spec_path),
                ),
            )

            spec = provider.discover_specs()[0]
            candidate = ToolFunctionCandidate.from_tool_spec(
                spec,
                source_id="configured.openapi.search_api",
            )

        parameter = spec.parameters[0]
        self.assertEqual(parameter.json_schema["enum"], ["en", "zh-hans", "zh-hant"])
        properties = candidate.input_schema["properties"]
        self.assertEqual(
            properties["search_lang"]["enum"],
            ["en", "zh-hans", "zh-hant"],
        )
        self.assertEqual(properties["search_lang"]["default"], "zh-hans")
        self.assertEqual(properties["search_lang"]["description"], "Content language.")

    def test_openapi_discovery_maps_security_scheme_credential_kinds(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            spec_path = Path(tempdir) / "security.json"
            spec_path.write_text(
                """
                {
                  "openapi": "3.0.3",
                  "info": {"title": "Security API", "version": "1.0.0"},
                  "servers": [{"url": "https://security.example.test"}],
                  "components": {
                    "securitySchemes": {
                      "HeaderKey": {
                        "type": "apiKey",
                        "in": "header",
                        "name": "X-Api-Key"
                      },
                      "BasicAuth": {"type": "http", "scheme": "basic"},
                      "OAuth": {
                        "type": "oauth2",
                        "flows": {
                          "authorizationCode": {
                            "authorizationUrl": "https://auth.example.test/authorize",
                            "tokenUrl": "https://auth.example.test/token",
                            "scopes": {"docs:read": "Read docs"}
                          }
                        }
                      },
                      "Oidc": {
                        "type": "openIdConnect",
                        "openIdConnectUrl": "https://auth.example.test/.well-known/openid-configuration"
                      }
                    }
                  },
                  "paths": {
                    "/header": {
                      "get": {
                        "operationId": "header",
                        "security": [{"HeaderKey": []}],
                        "responses": {"200": {"description": "ok"}}
                      }
                    },
                    "/basic": {
                      "get": {
                        "operationId": "basic",
                        "security": [{"BasicAuth": []}],
                        "responses": {"200": {"description": "ok"}}
                      }
                    },
                    "/oauth": {
                      "get": {
                        "operationId": "oauth",
                        "security": [{"OAuth": ["docs:read"]}],
                        "responses": {"200": {"description": "ok"}}
                      }
                    },
                    "/oidc": {
                      "get": {
                        "operationId": "oidc",
                        "security": [{"Oidc": []}],
                        "responses": {"200": {"description": "ok"}}
                      }
                    }
                  }
                }
                """,
                encoding="utf-8",
            )

            specs = {
                spec.id: spec
                for spec in OpenApiDiscoveryProvider(
                    OpenApiProviderSettings(
                        name="security_api",
                        spec_location=str(spec_path),
                        credential_bindings=(
                            OpenApiCredentialBinding(
                                scheme_name="HeaderKey",
                                credential_binding_id="binding.header",
                            ),
                            OpenApiCredentialBinding(
                                scheme_name="BasicAuth",
                                username_binding_id="binding.basic.username",
                                password_binding_id="binding.basic.password",
                            ),
                            OpenApiCredentialBinding(
                                scheme_name="OAuth",
                                credential_binding_id="account.oauth",
                            ),
                            OpenApiCredentialBinding(
                                scheme_name="Oidc",
                                credential_binding_id="account.oidc",
                            ),
                        ),
                    ),
                ).discover_specs()
            }

        header = specs["security_api.header"].credential_requirements[0].requirements[0]
        self.assertEqual(header.slot.expected_kind.value, "api_key")
        self.assertEqual(header.transport.value, "header")
        self.assertEqual(header.parameter_name, "X-Api-Key")

        basic = specs["security_api.basic"].credential_requirements[0].requirements
        self.assertEqual(
            [item.slot.slot for item in basic],
            ["BasicAuth.username", "BasicAuth.password"],
        )
        self.assertEqual(
            [item.slot.binding_id for item in basic],
            ["binding.basic.username", "binding.basic.password"],
        )
        self.assertEqual({item.slot.expected_kind.value for item in basic}, {"basic"})

        oauth = specs["security_api.oauth"].credential_requirements[0].requirements[0]
        self.assertEqual(oauth.slot.expected_kind.value, "oauth2_account")
        self.assertEqual(oauth.slot.scopes, ("docs:read",))
        self.assertEqual(
            oauth.setup_flow_hint.authorization_url,
            "https://auth.example.test/authorize",
        )
        self.assertEqual(oauth.setup_flow_hint.token_url, "https://auth.example.test/token")

        oidc = specs["security_api.oidc"].credential_requirements[0].requirements[0]
        self.assertEqual(oidc.slot.expected_kind.value, "openid_connect")
        self.assertEqual(
            oidc.setup_flow_hint.authorization_url,
            "https://auth.example.test/.well-known/openid-configuration",
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
