import unittest
from unittest.mock import patch, MagicMock
import psycopg
from bf4br import scheduler

class SchedulerReconnectTests(unittest.TestCase):
    def tearDown(self):
        scheduler.STOP=False

    def test_reconnects_after_connection_failure_without_publishing(self):
        conn=MagicMock()
        conn.closed=False
        attempts=[]
        def connect(*args,**kwargs):
            attempts.append(1)
            if len(attempts)==1:
                raise psycopg.OperationalError('simulated connection outage')
            return conn
        def sleep(_):
            if len(attempts)>=2:
                scheduler.STOP=True
        scheduler.STOP=False
        with patch.dict('os.environ',{'BF4BR_DSN':'mock'},clear=True), \
             patch.object(scheduler.psycopg,'connect',side_effect=connect), \
             patch.object(scheduler,'plan_once',return_value=[] ) as publish, \
             patch.object(scheduler.time,'sleep',side_effect=sleep), \
             patch.object(scheduler.signal,'signal'):
            scheduler.main(['--publish'])
        self.assertEqual(len(attempts),2)
        publish.assert_called_once()
        conn.close.assert_called_once()
