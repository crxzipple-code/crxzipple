from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from crxzipple.interfaces.http.app import create_app
from tests.unit.skill_test_support import write_skill_package
from tests.unit.support import SqliteTestHarness


class ArtifactsHttpTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.previous_openapi_provider_paths = os.environ.get(
            "APP_TOOL_OPENAPI_PROVIDER_PATHS",
        )
        os.environ["APP_TOOL_OPENAPI_PROVIDER_PATHS"] = os.pathsep
        self._skills_tempdir = tempfile.TemporaryDirectory()
        self._artifact_tempdir = tempfile.TemporaryDirectory()
        os.environ["APP_ARTIFACT_STORE_DIR"] = self._artifact_tempdir.name
        skills_root = Path(self._skills_tempdir.name)
        self._global_skills_patcher = patch(
            "crxzipple.modules.skills.infrastructure.filesystem.repository.DEFAULT_GLOBAL_SKILLS_DIR",
            skills_root / "global",
        )
        self._system_skills_patcher = patch(
            "crxzipple.modules.skills.infrastructure.filesystem.repository.DEFAULT_SYSTEM_SKILLS_DIR",
            skills_root / "system",
        )
        self._global_skills_patcher.start()
        self._system_skills_patcher.start()
        write_skill_package(
            skills_root / "system" / "memory-recall",
            name="memory-recall",
            description="Memory recall skill",
            instructions="# Memory Recall\n",
            allowed_tools=("memory_search",),
        )
        self.harness = SqliteTestHarness()
        self.harness.initialize_schema()
        self.client = TestClient(create_app(database_url=self.harness.database_url))

    def tearDown(self) -> None:
        self.client.close()
        self.client.app.state.container.close()
        self.harness.close()
        self._system_skills_patcher.stop()
        self._global_skills_patcher.stop()
        self._skills_tempdir.cleanup()
        self._artifact_tempdir.cleanup()
        os.environ.pop("APP_ARTIFACT_STORE_DIR", None)
        if self.previous_openapi_provider_paths is None:
            os.environ.pop("APP_TOOL_OPENAPI_PROVIDER_PATHS", None)
        else:
            os.environ["APP_TOOL_OPENAPI_PROVIDER_PATHS"] = (
                self.previous_openapi_provider_paths
            )

    def test_upload_and_serve_artifact(self) -> None:
        response = self.client.post(
            "/artifacts",
            params={"name": "duck.png", "mime_type": "image/png"},
            content=b"not-a-real-png",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["kind"], "image")
        self.assertEqual(payload["mime_type"], "image/png")
        self.assertEqual(payload["name"], "duck.png")
        self.assertTrue(payload["id"])
        self.assertEqual(
            payload["preview_url"],
            f"/artifacts/{payload['id']}/preview",
        )

        metadata = self.client.get(f"/artifacts/{payload['id']}")
        self.assertEqual(metadata.status_code, 200)
        self.assertEqual(metadata.json()["id"], payload["id"])

        preview = self.client.get(payload["preview_url"])
        self.assertEqual(preview.status_code, 200)
        self.assertEqual(preview.content, b"not-a-real-png")
        self.assertEqual(preview.headers["content-type"], "image/png")

        download = self.client.get(payload["download_url"])
        self.assertEqual(download.status_code, 200)
        self.assertEqual(download.content, b"not-a-real-png")

    def test_missing_artifact_returns_not_found(self) -> None:
        response = self.client.get("/artifacts/missing")
        self.assertEqual(response.status_code, 404)
