import unittest
from bf4br.supervisor_assignment import desired_specs,worker_module
from bf4br.assignment_runtime import WorkerSpec

class SupervisorAssignmentTests(unittest.TestCase):
    def test_daily_worker_module(self):
        spec=desired_specs(('daily',32),1,False)[0]
        self.assertEqual(worker_module(spec),'bf4br.daily_persona_worker')
        self.assertEqual(spec.platform,32)
    def test_historical_worker_module(self):
        spec=desired_specs(('historical',64),1,False)[0]
        self.assertEqual(worker_module(spec),'bf4br.persona_worker')
    def test_rotating_has_no_forced_platform(self):
        spec=desired_specs(('rotating',None),1,False)[0]
        self.assertIsNone(spec.platform)
    def test_paused_and_missing_assignment_fail_closed(self):
        self.assertEqual(desired_specs(('daily',1),1,True),[])
        self.assertEqual(desired_specs(None,1,False),[])
    def test_no_worker_target(self):
        self.assertEqual(desired_specs(('daily',1),0,False),[])
