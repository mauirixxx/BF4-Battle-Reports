"""v2 detail fetch and validation tests. No live Battlelog requests."""
import unittest
from unittest.mock import patch, MagicMock

from bf4br.detail_fetch import fetch_detail
from bf4br.detail_queue import save_player


class DetailFetchTests(unittest.TestCase):
    def test_invalid_identity_rejected_without_network(self):
        for values in ((0,1,1),(1,0,1),(1,1,0),(2,1,1)):
            with self.subTest(values=values):
                with patch('bf4br.detail_fetch.subprocess.run') as run:
                    with self.assertRaises(ValueError):
                        fetch_detail(*values)
                    run.assert_not_called()

    def test_url_contains_persona_not_generic_zero(self):
        proc=MagicMock(returncode=0,stdout='{"id":123,"platform":1}\n200')
        with patch('bf4br.detail_fetch.subprocess.run',return_value=proc) as run:
            code,payload,error,hint=fetch_detail(1,123,456)
        self.assertEqual((code,payload,error,hint),(200,{'id':123,'platform':1},None,None))
        args=run.call_args.args[0]
        self.assertIn('/123/1/456/',args[-1])

    def test_identity_validation_before_database_write(self):
        class NoDatabase:
            def transaction(self):
                raise AssertionError('must reject before opening transaction')
        valid={'id':123,'platform':1,'players':{'456':{}},'playerReport':{'stats':{},'personaId':456}}
        bad=[
            {**valid,'id':124},
            {**valid,'platform':32},
            {**valid,'players':[]},
            {**valid,'players':{'999':{}}},
            {**valid,'playerReport':{}},
            {**valid,'playerReport':{'stats':{},'personaId':999}},
        ]
        for payload in bad:
            with self.subTest(payload=payload):
                with self.assertRaises(ValueError):
                    save_player(NoDatabase(),(1,123,456),'token',payload)


if __name__=='__main__':
    unittest.main()
