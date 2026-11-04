import unittest
from datetime import date
from unittest.mock import patch
from bf4br import daily_persona_worker as worker

class DailyPersonaWorkerTests(unittest.TestCase):
    def test_module_has_daily_entrypoint(self):
        self.assertTrue(callable(worker.main))
        self.assertTrue(callable(worker.save_page))
    def test_empty_page_requires_object(self):
        with self.assertRaises(ValueError):
            worker.save_page(None,date(2026,11,2),1,123,'token',123,{})
    def test_retry_delay_is_available(self):
        self.assertTrue(callable(worker.retry_delay))