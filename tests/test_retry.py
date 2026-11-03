import unittest
from datetime import datetime, timezone
from bf4br.retry import retry_after_seconds, retry_delay

class FixedRandom:
    def uniform(self, a, b):
        return b

class RetryTests(unittest.TestCase):
    def test_retry_after_seconds(self):
        self.assertEqual(retry_after_seconds("30"), 30)
        self.assertEqual(retry_after_seconds("999999"), 3600)
        self.assertEqual(retry_after_seconds("nonsense"), None)
        self.assertEqual(retry_after_seconds("Wed, 21 Oct 2015 07:28:00 GMT",
            now=datetime(2015,10,21,7,27,30,tzinfo=timezone.utc)), 30)

    def test_transient_codes(self):
        for code in (429, 503, 502, 504):
            self.assertIsNotNone(retry_delay(code, 3, rng=FixedRandom()))
        self.assertIsNone(retry_delay(404, 3, rng=FixedRandom()))
        self.assertIsNone(retry_delay(200, 3, rng=FixedRandom()))

    def test_retry_after_honored(self):
        self.assertEqual(retry_delay(429, 1, "120", FixedRandom()), 120)
        self.assertEqual(retry_delay(503, 1, "60", FixedRandom()), 60)
        self.assertEqual(retry_delay(503, 1, "99999", FixedRandom()), 3600)

    def test_backoff_cap(self):
        self.assertEqual(retry_delay(503, 100, rng=FixedRandom()), 3600)

if __name__ == "__main__":
    unittest.main()
