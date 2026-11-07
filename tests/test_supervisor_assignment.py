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
    def test_v2_detail_role_is_explicit_and_platform_flexible(self):
        for role,platform in [('historical',1),('historical',32),('historical',64),('rotating',None)]:
            spec=desired_specs((role,platform),1,False,detail_enabled=True)[0]
            self.assertEqual(spec.role,'detail')
            self.assertIsNone(spec.platform)
            self.assertEqual(worker_module(spec),'bf4br.detail_worker')

    def test_v2_daily_stays_daily_and_pause_drains(self):
        for platform in (1,32,64):
            spec=desired_specs(('daily',platform),1,False,detail_enabled=True)[0]
            self.assertEqual(worker_module(spec),'bf4br.daily_persona_worker')
        self.assertEqual(desired_specs(('historical',1),1,True,detail_enabled=True),[])
        self.assertEqual(desired_specs(('historical',1),0,False,detail_enabled=True),[])

    def test_no_worker_target(self):
        self.assertEqual(desired_specs(('daily',1),0,False),[])
