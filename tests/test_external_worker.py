import unittest
from unittest.mock import patch

from bf4br import external_worker as worker


class ExternalWorkerTests(unittest.TestCase):
    def test_single_batch_success(self):
        claim = {"batch_id": "batch-1", "platform": 1, "persona_id": 99,
                 "reports": [{"report_id": 7, "token": "token-7"},
                             {"report_id": 8, "token": "token-8"}]}
        calls = []

        def api(base, key, route, payload):
            calls.append((route, payload))
            if route == "work/claim":
                return claim
            return {"stored": True}

        def fetch(platform, persona, item):
            return item, 200, {"id": item["report_id"]}, None, None

        with patch.object(worker, "api_post", side_effect=api), patch.object(
            worker, "request_detail", side_effect=fetch
        ):
            result = worker.run_batch("https://example.invalid", "secret", concurrency=2)
        self.assertEqual(result["stored"], 2)
        self.assertEqual(result["failed"], 0)
        self.assertEqual([name for name, _ in calls].count("enrichment"), 2)
        self.assertEqual(calls[-1][0], "work/complete")

    def test_429_stops_and_releases_undispatched(self):
        claim = {"batch_id": "batch-1", "platform": 1, "persona_id": 99,
                 "reports": [{"report_id": 7, "token": "a"},
                             {"report_id": 8, "token": "b"},
                             {"report_id": 9, "token": "c"}]}
        calls = []

        def api(base, key, route, payload):
            calls.append((route, payload))
            if route == "work/claim":
                return claim
            return {}

        def fetch(platform, persona, item):
            return item, 429, None, "limited", "300"

        with patch.object(worker, "api_post", side_effect=api), patch.object(
            worker, "request_detail", side_effect=fetch
        ):
            result = worker.run_batch("https://example.invalid", "secret", concurrency=1)
        self.assertTrue(result["rate_limited"])
        self.assertEqual(result["failed"], 3)
        self.assertEqual([name for name, _ in calls].count("work/fail"), 3)
        self.assertEqual([name for name, _ in calls].count("work/rate-limited"), 1)
        self.assertEqual(calls[-1][0], "work/complete")

    def test_http_200_non_object_is_logged_and_released(self):
        claim = {"batch_id": "batch-1", "platform": 1, "persona_id": 99,
                 "reports": [{"report_id": 7, "token": "token-7"}]}
        calls = []

        def api(base, key, route, payload):
            calls.append((route, payload))
            return claim if route == "work/claim" else {}

        def fetch(platform, persona, item):
            return item, 200, [], None, None

        with patch.object(worker, "api_post", side_effect=api), patch.object(
            worker, "request_detail", side_effect=fetch
        ), self.assertLogs("bf4br.external_worker", level="WARNING") as captured:
            result = worker.run_batch("https://example.invalid", "secret", concurrency=1)
        self.assertEqual(result["failed"], 1)
        self.assertEqual([name for name, _ in calls].count("enrichment"), 0)
        self.assertIn("unexpected JSON type: list", captured.output[0])
        self.assertIn("unexpected JSON type: list", next(body["reason"] for name, body in calls if name == "work/fail"))

    def test_continuous_worker_retries_temporary_transport_failure(self):
        from tempfile import NamedTemporaryFile
        with NamedTemporaryFile(mode="w", encoding="utf-8") as secret:
            secret.write("test-secret")
            secret.flush()
            with patch.object(worker, "run_batch", side_effect=[OSError("offline"),
                     {"claimed": 0}]), patch.object(worker.time, "sleep",
                     side_effect=[None, KeyboardInterrupt]) as sleeper:
                with self.assertRaises(KeyboardInterrupt):
                    worker.main(["--key-file", secret.name])
            self.assertEqual(sleeper.call_args_list[0].args[0], 15)
            self.assertEqual(sleeper.call_args_list[1].args[0], 61)

    def test_continuous_worker_stops_on_invalid_credentials(self):
        from tempfile import NamedTemporaryFile
        with NamedTemporaryFile(mode="w", encoding="utf-8") as secret:
            secret.write("test-secret")
            secret.flush()
            with patch.object(worker, "run_batch", side_effect=worker.APIError(401, "unauthorized")):
                self.assertEqual(worker.main(["--key-file", secret.name]), 3)

    def test_retry_after(self):
        self.assertEqual(worker.retry_after_seconds("180"), 180)
        self.assertEqual(worker.retry_after_seconds(None), 0)


if __name__ == "__main__":
    unittest.main()
