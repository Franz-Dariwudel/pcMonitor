from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest
from unittest.mock import patch
from monitor.config import Translator,load_settings,save_settings
from monitor.constants import LANGUAGE_SERVER

class ConfigTests(unittest.TestCase):
    def test_wrong_types_and_broken_json(self):
        with TemporaryDirectory() as d:
            p=Path(d)/'settings.json'
            p.write_text('{"language":[],"show_empty":"false","interval":true}')
            settings,issues=load_settings(p)
            self.assertEqual(settings,{'language':'de','show_empty':False,'interval':3,'language_server':LANGUAGE_SERVER})
            p.write_text('[]');self.assertEqual(load_settings(p)[1],['HM102'])
    def test_roundtrip_and_failed_write_preserves_previous_file(self):
        with TemporaryDirectory() as d:
            p=Path(d)/'config.json';expected={'language':'en','show_empty':True,'interval':0,'language_server':LANGUAGE_SERVER}
            save_settings(expected,p);self.assertEqual(load_settings(p)[0],expected)
            original=p.read_bytes()
            with patch('monitor.config.os.replace',side_effect=OSError('readonly')):
                with self.assertRaises(OSError):save_settings({},p)
            self.assertEqual(p.read_bytes(),original)
            self.assertEqual(list(Path(d).iterdir()),[p])
    def test_ten_languages_and_runtime_add_remove(self):
        with TemporaryDirectory() as d:
            folder=Path(d)
            for code in ('de','en','es','fr','pt','zh','hi','ar','ru','tr'):
                (folder/(code+'.json')).write_text(json.dumps({'hello':code}))
            tr=Translator('de',folder);self.assertEqual(len(tr.catalogs),10)
            (folder/'de.json').unlink();tr.reload();self.assertEqual(tr.language,'en')
            (folder/'de.json').write_text('{"hello":"Hallo"}');tr.reload();self.assertIn('de',tr.catalogs)
    def test_single_language_and_english_fallback(self):
        with TemporaryDirectory() as d:
            folder=Path(d);(folder/'fr.json').write_text('{"hello":"Bonjour"}')
            tr=Translator('de',folder);self.assertEqual(tr.language,'fr')
            (folder/'en.json').write_text('{"fallback":"English"}')
            tr.reload();self.assertEqual(tr('fallback'),'English')
            (folder/'broken.json').write_text('[]');tr.reload();self.assertTrue(tr.problems)
    def test_shipped_languages_have_same_keys(self):
        t=Translator();self.assertEqual(set(t.catalogs['de']),set(t.catalogs['en']))
