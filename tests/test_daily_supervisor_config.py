import unittest
from pathlib import Path
class DailySupervisorConfigTests(unittest.TestCase):
    def test_daily_platform_is_opt_in(self):
        source=(Path(__file__).resolve().parents[1]/'bf4br/supervisor.py').read_text()
        self.assertIn('BF4BR_DAILY_PLATFORM',source)
        self.assertIn('bf4br.daily_persona_worker',source)