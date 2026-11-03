import unittest
from unittest.mock import patch
from bf4br.fleet_upgrade import registered_hosts

class RegistryTests(unittest.TestCase):
    @patch('bf4br.fleet_upgrade.subprocess.check_output', return_value='["hnl-01", "mak-01"]')
    def test_database_discovery(self, run):
        self.assertEqual(registered_hosts(), ['hnl-01', 'mak-01'])
        self.assertIn('runuser', run.call_args.args[0])

    @patch('bf4br.fleet_upgrade.subprocess.check_output', return_value='["hnl-01;bad"]')
    def test_rejects_unsafe_host(self, run):
        with self.assertRaises(ValueError):
            registered_hosts()
