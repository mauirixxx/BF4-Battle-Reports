import unittest
from bf4br.detail_assignment import v2_assignment,detail_worker_module


class V2AssignmentTests(unittest.TestCase):
    def test_daily_unchanged_when_enabled(self):
        for platform in (1,32,64):
            self.assertEqual(detail_worker_module(('daily',platform),True),
                             'bf4br.daily_persona_worker')

    def test_seven_historical_slots_become_details(self):
        assignments=[('daily',1),('daily',32),('daily',64)]
        assignments += [('historical',p) for p in (1,32,64,1,32,64)]
        assignments += [('rotating',None)]
        self.assertEqual(sum(detail_worker_module(a,True)=='bf4br.detail_worker'
                             for a in assignments),7)
        self.assertEqual(sum(detail_worker_module(a,True)=='bf4br.daily_persona_worker'
                             for a in assignments),3)

    def test_disabled_preserves_old_behavior(self):
        self.assertEqual(detail_worker_module(('historical',1)), 'bf4br.persona_worker')
        self.assertEqual(detail_worker_module(('rotating',None)), 'bf4br.persona_worker')

    def test_no_assignment_fails_closed(self):
        self.assertIsNone(v2_assignment(None,True))
        self.assertIsNone(detail_worker_module(None,True))

    def test_invalid_assignments_rejected(self):
        for a in [('daily',None),('rotating',1),('detail',1),('historical',None),('unknown',1)]:
            with self.subTest(a=a),self.assertRaises(ValueError):
                v2_assignment(a,True)


if __name__=='__main__':
    unittest.main()
