"""Deterministic tests for the v4-inspired dispatch loop (no network/DB)."""
import threading
import unittest
from bf4br.detail_burst import run_burst


class BurstTests(unittest.TestCase):
    def test_bounded_dispatch_and_concurrency(self):
        lock = threading.Lock()
        active = [0]
        peak = [0]
        handled = []
        def fetch(job):
            with lock:
                active[0] += 1
                peak[0] = max(peak[0], active[0])
            with lock:
                active[0] -= 1
            return (200, job)
        count, limited = run_burst(range(100), fetch, lambda j,r: handled.append(j))
        self.assertEqual((count, limited), (40, False))
        self.assertEqual(sorted(handled), list(range(40)))
        self.assertLessEqual(peak[0], 4)

    def test_429_does_not_dispatch_replacements(self):
        handled=[]
        count, limited = run_burst(range(100), lambda j: (429 if j==0 else 200,j),
                                   lambda j,r: handled.append((j,r[0])))
        self.assertTrue(limited)
        self.assertLessEqual(count, 4)
        self.assertEqual(len(handled), count)

    def test_stop_prevents_dispatch(self):
        count, limited = run_burst(range(40), lambda j:(200,j), lambda j,r:None,
                                   stopped=lambda: True)
        self.assertEqual((count,limited), (0,False))


if __name__ == '__main__':
    unittest.main()
