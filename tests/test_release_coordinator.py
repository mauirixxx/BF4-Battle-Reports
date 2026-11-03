"""Unit tests: release eligibility must not follow main or accept prereleases."""
import unittest
from unittest.mock import patch
from bf4br.release_coordinator import latest_release, tag_sha


class FakeResponse:
    def __init__(self, value):
        self.value = value

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


class ReleaseEligibility(unittest.TestCase):
    @patch("bf4br.release_coordinator.urllib.request.urlopen")
    def test_published_stable_release(self, get):
        get.return_value = FakeResponse(None)
        with patch("bf4br.release_coordinator.json.load", return_value={
            "tag_name": "v1.0.0", "published_at": "2026-11-03T08:03:29Z",
            "draft": False, "prerelease": False,
        }):
            self.assertEqual(latest_release()["tag_name"], "v1.0.0")

    @patch("bf4br.release_coordinator.urllib.request.urlopen")
    def test_prerelease_rejected(self, get):
        get.return_value = FakeResponse(None)
        with patch("bf4br.release_coordinator.json.load", return_value={
            "tag_name": "v1.0.1", "published_at": "2026-11-03T08:03:29Z",
            "prerelease": True,
        }):
            with self.assertRaises(ValueError):
                latest_release()

    @patch("bf4br.release_coordinator.urllib.request.urlopen")
    def test_draft_rejected(self, get):
        get.return_value = FakeResponse(None)
        with patch("bf4br.release_coordinator.json.load", return_value={
            "tag_name": "v1.0.1", "published_at": "2026-11-03T08:03:29Z",
            "draft": True,
        }):
            with self.assertRaises(ValueError):
                latest_release()

    @patch("bf4br.release_coordinator.urllib.request.urlopen")
    def test_invalid_tag_rejected(self, get):
        get.return_value = FakeResponse(None)
        with patch("bf4br.release_coordinator.json.load", return_value={
            "tag_name": "main", "published_at": "2026-11-03T08:03:29Z",
        }):
            with self.assertRaises(ValueError):
                latest_release()

    @patch("bf4br.release_coordinator.subprocess.run")
    def test_annotated_tag_uses_peeled_commit(self, run):
        run.return_value.stdout = (
            "a" * 40 + "\trefs/tags/v1.0.0\n" +
            "b" * 40 + "\trefs/tags/v1.0.0^{}\n"
        )
        self.assertEqual(tag_sha("v1.0.0"), "b" * 40)


if __name__ == "__main__":
    unittest.main()
