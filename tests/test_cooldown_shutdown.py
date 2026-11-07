import unittest
from unittest.mock import patch, MagicMock
from bf4br import daily_persona_worker, detail_worker, persona_worker

class CooldownShutdownTests(unittest.TestCase):
    def test_daily_shutdown_during_cooldown_releases_lease(self):
        conn=MagicMock()
        conn.cursor.return_value.__enter__.return_value.fetchone.return_value=(100,)
        with patch.object(daily_persona_worker,"STOP",True), patch.object(daily_persona_worker,"renew",return_value=True), patch.object(daily_persona_worker,"guarded_request",side_effect=lambda *a,**k:k["on_wait"]()), patch.object(daily_persona_worker,"release") as release:
            daily_persona_worker.process_one(conn,"2026-11-06",64,123,"token")
            release.assert_called_once()
    def test_historical_fallback_shutdown_during_cooldown(self):
        conn=MagicMock()
        conn.cursor.return_value.__enter__.return_value.fetchone.return_value=(100,100)
        with patch.object(persona_worker,"STOP",False), patch.object(persona_worker,"renew",return_value=True), patch.object(persona_worker,"guarded_request",side_effect=lambda *a,**k:k["on_wait"]()), patch.object(persona_worker,"release") as release:
            persona_worker.process_one(conn,(64,123),"token",stop_requested=lambda: True)
            release.assert_called_once()
    def test_detail_shutdown_during_cooldown_requeues(self):
        with patch.object(detail_worker,"STOP",True), patch.object(detail_worker,"renew_player",return_value=True), patch.object(detail_worker,"guarded_request",side_effect=lambda *a,**k:k["on_wait"]()), patch.object(detail_worker,"retry_player") as retry:
            self.assertEqual(detail_worker.process_one(object(),(1,2,3),"token"),"drained")
            retry.assert_called_once()
