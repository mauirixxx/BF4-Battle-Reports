"""Pure scheduling tests; never access production or Battlelog."""
import unittest
from bf4br.detail_batch import batches, validate_burst_policy


class DetailBatchTests(unittest.TestCase):
    def test_exact_boundary(self):
        self.assertEqual([len(b) for b in batches(range(80))], [40, 40])

    def test_partial_final_batch(self):
        self.assertEqual([len(b) for b in batches(range(91))], [40, 40, 11])

    def test_empty(self):
        self.assertEqual(list(batches([])), [])

    def test_lazy_stream(self):
        stream=(i for i in range(41))
        first=next(batches(stream))
        self.assertEqual(first, tuple(range(40)))
        self.assertEqual(next(stream), 40)

    def test_invalid_sizes(self):
        for size in (0, -1, True, 1.5):
            with self.subTest(size=size), self.assertRaises(ValueError):
                list(batches([1], size))

    def test_policy(self):
        self.assertEqual(validate_burst_policy(), (40, 4, 61))
        for values in ((40, 41, 61), (41, 4, 61), (40, 0, 61), (40, 4, 60), (True, 4, 61)):
            with self.subTest(values=values), self.assertRaises(ValueError):
                validate_burst_policy(*values)


if __name__ == '__main__':
    unittest.main()
