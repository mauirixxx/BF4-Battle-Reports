"""Safety regression: the rolling deployer must drain all four lease queues."""
import unittest
from unittest.mock import patch
from bf4br import fleet_upgrade


class FleetDrainTests(unittest.TestCase):
    def test_drain_checks_historical_and_daily_leases(self):
        scripts=[]
        class Result:
            returncode=0
            stdout='1 0\\n'
        def fake_run(argv, **kwargs):
            script=argv[argv.index('-c')+1]
            scripts.append(script)
            return Result()
        with patch.object(fleet_upgrade.subprocess,'run',side_effect=fake_run):
            fleet_upgrade.drain('mak-01',timeout=10)
        self.assertEqual(len(scripts),1)
        for table in ('bf4br_persona_jobs','bf4br_report_jobs',
                      'bf4br_daily_persona_jobs','bf4br_daily_report_jobs'):
            self.assertIn(table,scripts[0])
        self.assertEqual(scripts[0].count('lease_until>now()'),4)
        self.assertEqual(scripts[0].count("'mak-01-%'"),4)

    def test_drain_refuses_when_any_lease_remains(self):
        class Result:
            returncode=1
        with (patch.object(fleet_upgrade.subprocess,'run',return_value=Result()),
              patch.object(fleet_upgrade.time,'monotonic',side_effect=[0,11])):
            with self.assertRaises(TimeoutError):
                fleet_upgrade.drain('mak-01',timeout=10)
