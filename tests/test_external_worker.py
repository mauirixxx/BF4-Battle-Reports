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

    def test_retry_after(self):
        self.assertEqual(worker.retry_after_seconds("180"), 180)
        self.assertEqual(worker.retry_after_seconds(None), 0)


if __name__ == "__main__":
    unittest.main()
