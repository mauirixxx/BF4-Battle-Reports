import unittest
from datetime import datetime, timezone, timedelta
from bf4br.daily_window import previous_utc_day, session_overlaps, platform_code

UTC = timezone.utc

class DailyWindowTests(unittest.TestCase):
    def test_utc_midnight(self):
        self.assertEqual(previous_utc_day(datetime(2026,11,3,0,0,tzinfo=UTC)),
                         (datetime(2026,11,2,tzinfo=UTC),datetime(2026,11,3,tzinfo=UTC)))
    def test_timezone_conversion(self):
        hawaii=timezone(timedelta(hours=-10))
        self.assertEqual(previous_utc_day(datetime(2026,11,2,15,tzinfo=hawaii))[0].day,2)
    def test_cross_midnight(self):
        start,end=previous_utc_day(datetime(2026,11,3,tzinfo=UTC))
        self.assertTrue(session_overlaps(datetime(2026,11,1,23,tzinfo=UTC),
                         datetime(2026,11,3,1,tzinfo=UTC),None,start,end))
        self.assertFalse(session_overlaps(datetime(2026,11,3,tzinfo=UTC),
                          datetime(2026,11,3,1,tzinfo=UTC),None,start,end))
    def test_platforms(self):
        self.assertEqual([platform_code(x) for x in ('PC','PS4/5','XBox')],[1,32,64])
        self.assertIsNone(platform_code('Unknown'))
    def test_naive_rejected(self):
        with self.assertRaises(ValueError): previous_utc_day(datetime(2026,11,3))

if __name__=='__main__': unittest.main()
