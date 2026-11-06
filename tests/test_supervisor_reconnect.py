"""Fault-inject a dropped supervisor connection without touching production."""
import os
import unittest
from unittest.mock import MagicMock, patch
import psycopg
from bf4br import supervisor

class SupervisorReconnectTests(unittest.TestCase):
    def tearDown(self):
        supervisor.STOP=False

    def test_supervisor_reconnects_after_control_query_disconnect(self):
        first=MagicMock()
        second=MagicMock()
        for conn in (first,second):
            conn.closed=False
            cursor=conn.cursor.return_value.__enter__.return_value
            cursor.fetchone.return_value=(0,0,False,10,180)
            cursor.fetchall.return_value=[]
        # First connection works for one pass, then fails during the next.
        first.transaction.side_effect=[MagicMock(),psycopg.OperationalError('simulated dropped socket')]
        connections=[first,second]
        attempts=[]
        def connect(*args,**kwargs):
            attempts.append(1)
            return connections.pop(0)
        sleeps=[]
        def sleep(_):
            sleeps.append(1)
            if len(sleeps)==3:
                supervisor.STOP=True
        supervisor.STOP=False
        with patch.dict(os.environ,{'BF4BR_DSN':'mock','BF4BR_NODE':'reconnect-test'},clear=True), \
             patch.object(supervisor.psycopg,'connect',side_effect=connect), \
             patch.object(supervisor.time,'sleep',side_effect=sleep), \
             patch.object(supervisor.signal,'signal'):
            supervisor.main()
        self.assertEqual(len(attempts),2)
        first.close.assert_called()
        second.close.assert_called()
        self.assertGreaterEqual(second.cursor.call_count,2)
