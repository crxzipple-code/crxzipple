from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from crxzipple.core.config import OpenApiCredentialBinding, OpenApiProviderSettings
from crxzipple.modules.tool.domain.exceptions import ToolValidationError
from crxzipple.modules.tool.infrastructure.discovery.openapi import (
    OpenApiDiscoveryProvider,
)
from crxzipple.modules.tool.infrastructure.runtimes.openapi_remote import (
    _resolve_secret_source,
)
from tests.unit.support import openapi_fixture_path


class OpenApiAccessTestCase(unittest.TestCase):
    def test_resolves_file_credential_source_through_access(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            credential_path = Path(tempdir) / "token.txt"
            credential_path.write_text("file-token\n", encoding="utf-8")

            resolved = _resolve_secret_source(
                f"file:{credential_path}",
                scheme_name="bearerAuth",
            )

        self.assertEqual(resolved, "file-token")

    def test_rejects_literal_sources_for_openapi_credentials(self) -> None:
        with self.assertRaises(ToolValidationError):
            _resolve_secret_source("inline-token", scheme_name="bearerAuth")

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


if __name__ == "__main__":
    unittest.main()
