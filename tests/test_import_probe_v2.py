import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

spec=importlib.util.spec_from_file_location('probe_import_v2','/var/tmp/bf4br-probe-import-v2.py')
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

class ProbeImportTests(unittest.TestCase):
    def test_valid_probe_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'1_123'/'player_456.json';p.parent.mkdir()
            payload={'id':123,'platform':1,'players':{'456':{}},'playerReport':{'personaId':456,'stats':{}}}
            p.write_text(json.dumps(payload))
            self.assertEqual(mod.load_validated(p),( (1,123,456),payload))

    def test_mismatched_persona_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'1_123'/'player_456.json';p.parent.mkdir()
            p.write_text(json.dumps({'id':123,'platform':1,'players':{'456':{}},'playerReport':{'personaId':999,'stats':{}}}))
            with self.assertRaises(ValueError):mod.load_validated(p)

    def test_invalid_platform_rejected(self):
        with self.assertRaises(ValueError):mod.identity(Path('/tmp/2_123/player_456.json'))

    def test_null_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'1_123'/'player_456.json';p.parent.mkdir();p.write_text('null')
            with self.assertRaises(ValueError):mod.load_validated(p)

if __name__=='__main__':unittest.main()