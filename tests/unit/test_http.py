from __future__ import annotations

from tests.unit.http_test_support import *


class HttpInterfaceTestCase(HttpModuleTestCase):
    def test_health_endpoint(self) -> None:
            response = self.client.get("/health")

            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), {"status": "ok"})


if __name__ == "__main__":
    unittest.main()
