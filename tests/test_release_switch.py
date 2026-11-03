"""Release switcher safety tests without touching systemd or production."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from bf4br import release_switch as sw


class ReleaseSwitchSafety(unittest.TestCase):
    def test_semver_strict(self):
        self.assertTrue(sw.VERSION.fullmatch("v1.0.0"))
        self.assertTrue(sw.VERSION.fullmatch("v1.0.1"))
        self.assertFalse(sw.VERSION.fullmatch("main"))
        self.assertFalse(sw.VERSION.fullmatch("v1x0x0"))
        self.assertFalse(sw.VERSION.fullmatch("v1.0.0-rc1"))

    def test_staged_sha_must_match(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            version = root / "v1.0.0"
            version.mkdir()
            (version / ".bf4br-release-sha").write_text("a" * 40)
            with patch.object(sw, "RELEASES", root):
                with self.assertRaisesRegex(RuntimeError, "SHA mismatch"):
                    sw.assert_staged("v1.0.0", "b" * 40)

    def test_health_rejects_inactive_service(self):
        with patch.object(sw, "service_active", return_value=False):
            self.assertFalse(sw.healthy())

    def test_deployment_rejects_bad_sha_before_service_stop(self):
        with patch.object(sw, "RELEASES", Path("/nonexistent-release-test")):
            with patch.object(sw, "run") as runner:
                with self.assertRaises(RuntimeError):
                    sw.assert_staged("v1.0.0", "a" * 40)
                runner.assert_not_called()

    def test_failed_activation_restores_original_directory(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            releases = root / "releases"
            releases.mkdir()
            live = root / "bf4br"
            live.mkdir()
            (live / "old").write_text("original")
            target = releases / "v1.0.1"
            (target / ".venv/bin").mkdir(parents=True)
            (target / ".venv/bin/python").write_text("test")
            (target / ".bf4br-release-sha").write_text("a" * 40)
            actions = []
            def fake_run(*args, **kwargs):
                actions.append(args)
                if args[:2] == ("systemctl", "start"):
                    raise RuntimeError("injected activation failure")
                return None
            with patch.object(sw, "ROOT", root), patch.object(sw, "LIVE", live), patch.object(sw, "RELEASES", releases), patch.object(sw, "LOCK", root / "lock"), patch.object(sw, "STATE", root / "state"), patch.object(sw, "run", side_effect=fake_run), patch.object(sw, "service_active", side_effect=[True, False]), patch.object(sw, "healthy", return_value=True), patch.object(sw.os, "geteuid", return_value=0):
                with self.assertRaisesRegex(RuntimeError, "injected activation failure"):
                    sw.deploy("v1.0.1", "a" * 40)
            self.assertFalse(live.is_symlink())
            self.assertEqual((live / "old").read_text(), "original")
            self.assertFalse((root / "state").exists())
            self.assertIn(("systemctl", "restart", sw.SERVICE), actions)

    def test_failed_health_check_restores_previous_version_symlink(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            releases = root / "releases"
            old = releases / "v1.0.0"
            new = releases / "v1.0.1"
            for directory in (old, new):
                (directory / ".venv/bin").mkdir(parents=True)
                (directory / ".venv/bin/python").write_text("test")
            (new / ".bf4br-release-sha").write_text("a" * 40)
            live = root / "bf4br"
            live.symlink_to(old, target_is_directory=True)
            actions = []
            def fake_run(*args, **kwargs):
                actions.append(args)
                return None
            with patch.object(sw, "ROOT", root), patch.object(sw, "LIVE", live), patch.object(sw, "RELEASES", releases), patch.object(sw, "LOCK", root / "lock"), patch.object(sw, "STATE", root / "state"), patch.object(sw, "run", side_effect=fake_run), patch.object(sw, "service_active", side_effect=[True, False]), patch.object(sw, "healthy", side_effect=[False, True]), patch.object(sw.time, "sleep"), patch.object(sw.os, "geteuid", return_value=0):
                with self.assertRaisesRegex(RuntimeError, "health check"):
                    sw.deploy("v1.0.1", "a" * 40)
            self.assertTrue(live.is_symlink())
            self.assertEqual(live.resolve(), old)
            self.assertIn(("systemctl", "restart", sw.SERVICE), actions)
            self.assertFalse((root / "state").exists())

    def test_switch_restores_legacy_directory(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            live = root / "bf4br"
            releases = root / "releases"
            releases.mkdir()
            live.mkdir()
            (live / "original.txt").write_text("original")
            target = releases / "v1.0.0"
            target.mkdir()
            with patch.object(sw, "LIVE", live), patch.object(sw, "ROOT", root), patch.object(sw, "RELEASES", releases):
                sw.switch(target)
                self.assertEqual(live.resolve(), target)
                sw.restore(str(live))
                self.assertFalse(live.is_symlink())
                self.assertEqual((live / "original.txt").read_text(), "original")


if __name__ == "__main__":
    unittest.main()
