import unittest
from bf4br.assignment_runtime import WorkerSpec, desired_persona_specs, changed

class AssignmentRuntimeTests(unittest.TestCase):
    def test_daily(self):
        self.assertEqual(desired_persona_specs(('daily',32),1), [WorkerSpec('persona','daily',32)])
    def test_historical(self):
        self.assertEqual(desired_persona_specs(('historical',64),1), [WorkerSpec('persona','historical',64)])
    def test_rotating_is_explicit(self):
        self.assertEqual(desired_persona_specs(('rotating',None),1), [WorkerSpec('persona','rotating',None)])
    def test_no_assignment_is_fail_closed(self):
        self.assertEqual(desired_persona_specs(None,1), [])
    def test_no_unnecessary_restart(self):
        spec=WorkerSpec('persona','daily',1)
        self.assertFalse(changed(spec,spec))
        self.assertTrue(changed(spec,WorkerSpec('persona','daily',32)))
    def test_reject_ambiguous_multiworker(self):
        with self.assertRaises(ValueError):
            desired_persona_specs(('daily',1),2)
    def test_invalid_assignment(self):
        for assignment in [('rotating',1),('daily',None),('unknown',1)]:
            with self.subTest(assignment=assignment), self.assertRaises(ValueError):
                desired_persona_specs(assignment,1)
