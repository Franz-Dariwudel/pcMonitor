"""Alle veröffentlichten Sprachen: Schlüssel, Platzhalter, Hilfe und Installation."""
import json
import re
import string
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from monitor.constants import ROOT
from monitor.config import Translator
from monitor.language_packs import catalog, help_document, install_local_pair

CODES=('de','en','es','fr','pt','zh','hi','ar','ru','tr')

class TranslationTests(unittest.TestCase):
    def test_complete_catalogs_and_matching_placeholders(self):
        source=catalog((ROOT/'languages/en.json').read_bytes())
        fields=lambda text: sorted(name for _,name,_,_ in string.Formatter().parse(text) if name is not None)
        for code in CODES:
            with self.subTest(code=code):
                target=catalog((ROOT/'languages'/f'{code}.json').read_bytes())
                self.assertEqual(set(target),set(source))
                for key,value in target.items():
                    self.assertTrue(value.strip(),(code,key))
                    self.assertEqual(fields(value),fields(source[key]),(code,key))
    def test_help_covers_error_codes_and_is_safe_to_install(self):
        required=set()
        for source in [* (ROOT/'monitor').glob('*.py'),ROOT/'launcher.py']:
            required.update(re.findall(r'HM\d{3}',source.read_text()))
        for code in CODES:
            with self.subTest(code=code):
                raw=(ROOT/'help'/f'{code}.html').read_bytes()
                help_document(raw)
                self.assertTrue(required.issubset(set(re.findall(r'HM\d{3}',raw.decode()))),code)
                self.assertIn(f'lang="{code}"',raw.decode())
                if code=='ar':self.assertIn('dir="rtl"',raw.decode())
    def test_each_pair_installs_and_reloads(self):
        with TemporaryDirectory() as d:
            root=Path(d);tr=Translator(directory=root/'languages')
            for code in CODES:
                install_local_pair(ROOT/'languages'/f'{code}.json',root/'languages',root/'help')
                tr.reload()
                self.assertIn(code,tr.catalogs)
                self.assertTrue((root/'help'/f'{code}.html').is_file())
            self.assertEqual(len(tr.catalogs),10)
