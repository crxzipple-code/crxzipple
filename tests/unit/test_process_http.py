from __future__ import annotations

from tests.unit.http_test_support import *


class ProcessHttpBoundaryTestCase(HttpModuleTestCase):
    def test_process_endpoints_are_not_publicly_mounted(self) -> None:
        response = self.client.get("/processes")

        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
