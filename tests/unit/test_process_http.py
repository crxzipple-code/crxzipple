from __future__ import annotations

from tests.unit.http_test_support import *


class ProcessHttpTestCase(HttpModuleTestCase):
    def test_process_endpoints_start_list_output_and_remove(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            start_response = self.client.post(
                "/processes",
                json={
                    "command": "printf 'hello\\n'; sleep 0.2; printf 'done\\n'",
                    "working_directory": tempdir,
                    "session_key": "agent:assistant:main",
                },
            )
            self.assertEqual(start_response.status_code, 201)
            process_id = start_response.json()["id"]

            list_response = self.client.get(
                "/processes",
                params={"session_key": "agent:assistant:main"},
            )
            self.assertEqual(list_response.status_code, 200)
            self.assertEqual([item["id"] for item in list_response.json()], [process_id])

            time.sleep(0.4)
            output_response = self.client.get(f"/processes/{process_id}/output")
            self.assertEqual(output_response.status_code, 200)
            output_payload = output_response.json()
            self.assertIn("hello", output_payload["stdout"])
            self.assertIn("done", output_payload["stdout"])

            remove_response = self.client.delete(f"/processes/{process_id}")
            self.assertEqual(remove_response.status_code, 204)

    def test_process_endpoints_can_terminate_running_process(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            start_response = self.client.post(
                "/processes",
                json={
                    "command": "sleep 5",
                    "working_directory": tempdir,
                },
            )
            self.assertEqual(start_response.status_code, 201)
            process_id = start_response.json()["id"]

            terminate_response = self.client.post(f"/processes/{process_id}/terminate")
            self.assertEqual(terminate_response.status_code, 200)

            get_response = self.client.get(f"/processes/{process_id}")
            self.assertEqual(get_response.status_code, 200)
            self.assertIn(get_response.json()["status"], {"running", "killed"})


if __name__ == "__main__":
    unittest.main()
