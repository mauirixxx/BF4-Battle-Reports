"""Verify SIGTERM-style draining releases a live persona lease after its page."""
import unittest
from unittest.mock import patch, MagicMock
from bf4br import persona_worker

class PersonaDrainTests(unittest.TestCase):
    def tearDown(self):
        persona_worker.STOP=False

    def test_signal_during_fetch_persists_page_then_releases_lease(self):
        conn=MagicMock()
        conn.cursor.return_value.__enter__.return_value.fetchone.return_value=(123456,None)
        token='lease-token'
        def fetched(*args,**kwargs):
            persona_worker.stop(None,None)
            return 200,{'data':{'gameReports':[]}},None
        persona_worker.STOP=False
        with patch.object(persona_worker,'renew',return_value=True), \
             patch.object(persona_worker,'get_page',side_effect=fetched), \
             patch.object(persona_worker,'persist_page',return_value={'saved':0,'finished':False,'next_cursor':123455}) as persist, \
             patch.object(persona_worker,'release',return_value=True) as release, \
             patch.object(persona_worker.time,'sleep'):
            persona_worker.process_one(conn,(32,456),token)
        persist.assert_called_once()
        release.assert_called_once_with(conn,'persona',32,456,token,delay_seconds=0)

    def test_no_new_page_when_already_draining(self):
        conn=MagicMock()
        conn.cursor.return_value.__enter__.return_value.fetchone.return_value=(123456,None)
        persona_worker.STOP=True
        with patch.object(persona_worker,'get_page') as fetch, \
             patch.object(persona_worker,'release',return_value=True) as release:
            persona_worker.process_one(conn,(1,456),'token')
        fetch.assert_not_called()
        release.assert_called_once()
