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
