"""Regression coverage for missing Battlelog persona metadata."""
import unittest
from bf4br.report_import import validate

GUID = "00000000-0000-0000-0000-000000000001"

def report(players):
    return {"id": 987, "platform": 1, "createdAt": 1900,
            "gameServer": {"guid": GUID, "name": "test"}, "players": players}

class NullPersonaRegression(unittest.TestCase):
    def test_null_persona_is_skipped_but_valid_players_survive(self):
        payload = report({"a": {"personaId": 123, "persona": None},
                          "b": {"personaId": 456, "persona": {"personaName": "soldier"}}})
        server, people = validate(payload, 1, 987)
        self.assertEqual(server["guid"], GUID)
        self.assertEqual(people, [(456, "soldier")])

    def test_all_null_personas_are_rejected_not_silently_imported(self):
        with self.assertRaisesRegex(ValueError, "no importable player identities"):
            validate(report({"a": {"personaId": 123, "persona": None}}), 1, 987)

    def test_invalid_non_null_persona_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "invalid persona object"):
            validate(report({"a": {"personaId": 123, "persona": "bad"}}), 1, 987)

    def test_duplicate_valid_persona_ids_rejected(self):
        with self.assertRaisesRegex(ValueError, "duplicate persona IDs"):
            validate(report({"a": {"personaId": 123, "persona": {"personaName": "one"}},
                             "b": {"personaId": 123, "persona": {"personaName": "two"}}}), 1, 987)

if __name__ == "__main__":
    unittest.main()
