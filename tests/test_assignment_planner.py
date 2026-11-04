import unittest
from collections import Counter

from bf4br.assignment_planner import PLATFORMS, next_platform, plan


class AssignmentPlannerTests(unittest.TestCase):
    def setUp(self):
        self.nodes = [f"node-{n:02d}" for n in range(10)]

    def test_ten_slots_three_each_and_rotator(self):
        assignments = plan(self.nodes)
        self.assertEqual(len(assignments), 10)
        self.assertEqual(Counter(a.platform for a in assignments if a.platform is not None),
                         {p: 3 for p in PLATFORMS})
        self.assertEqual(Counter(a.role for a in assignments),
                         {"daily": 3, "historical": 6, "rotating": 1})

    def test_daily_one_per_platform(self):
        daily = [a.platform for a in plan(self.nodes) if a.role == "daily"]
        self.assertEqual(set(daily), set(PLATFORMS))

    def test_order_and_duplicate_nodes_do_not_change_plan(self):
        self.assertEqual(plan(self.nodes), plan(list(reversed(self.nodes)) + self.nodes))

    def test_paused_or_dead_nodes_not_assigned(self):
        healthy = self.nodes[1:]
        self.assertTrue(all(a.node in healthy for a in plan(healthy)))
        self.assertEqual(len(plan(healthy)), 9)

    def test_historical_failure_does_not_reshuffle_healthy_nodes(self):
        before=plan(self.nodes)
        failed=next(a.node for a in before if a.role=='historical')
        after=plan([n for n in self.nodes if n!=failed],previous=before)
        prior={a.node:a for a in before}
        self.assertTrue(all(a==prior[a.node] for a in after))

    def test_daily_failure_promotes_only_one_worker(self):
        before=plan(self.nodes)
        failed=next(a.node for a in before if a.role=='daily')
        after=plan([n for n in self.nodes if n!=failed],previous=before)
        changes=[a for a in after if a!=next(b for b in before if b.node==a.node)]
        self.assertEqual(len(changes),1)
        self.assertEqual(changes[0].role,'daily')
        self.assertEqual({a.platform for a in after if a.role=='daily'},set(PLATFORMS))

    def test_recovery_does_not_displace_incumbents(self):
        before=plan(self.nodes)
        missing=next(a.node for a in before if a.role=='historical')
        partial=plan([n for n in self.nodes if n!=missing],previous=before)
        recovered=plan(self.nodes,previous=partial)
        self.assertTrue(all(a in recovered for a in partial))

    def test_rotation(self):
        platform = None
        seen = []
        for _ in range(6):
            platform = next_platform(platform)
            seen.append(platform)
        self.assertEqual(seen, list(PLATFORMS) * 2)

    def test_invalid_input(self):
        with self.assertRaises(ValueError):
            plan(self.nodes, capacity=11)
        with self.assertRaises(ValueError):
            next_platform(999)


if __name__ == "__main__":
    unittest.main()
