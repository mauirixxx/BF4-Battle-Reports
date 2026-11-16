import unittest
from bf4br.manual_report import parse_report_url

class ManualReportURLTests(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(parse_report_url('https://battlelog.battlefield.com/bf4/battlereport/show/1/2122278437916058688/236753552/'), (1,2122278437916058688,236753552))
    def test_rejects(self):
        for url in ('http://battlelog.battlefield.com/bf4/battlereport/show/1/123/45/', 'https://evil.example/bf4/battlereport/show/1/123/45/', 'https://battlelog.battlefield.com/bf4/battlereport/show/2/123/45/', 'https://battlelog.battlefield.com/bf4/battlereport/show/1/9999999999999999999/45/', 'https://battlelog.battlefield.com/bf4/battlereport/show/1/123/45/?x=1'):
            with self.subTest(url=url), self.assertRaises(ValueError):parse_report_url(url)
