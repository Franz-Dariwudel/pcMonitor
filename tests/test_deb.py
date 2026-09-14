"""Benutzerressourcen und rückstandsfreie Verwaltung der Desktopstarter prüfen."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from monitor.config import Translator
from monitor import constants

spec = importlib.util.spec_from_file_location('desktop_links', Path(__file__).resolve().parent.parent/'packaging/desktop_links.py')
links = importlib.util.module_from_spec(spec)
spec.loader.exec_module(links)


class DebTests(unittest.TestCase):
    def test_user_language_overrides_bundled_and_removal_restores_it(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/'system';user=Path(d)/'user'
            (root/'languages').mkdir(parents=True);(user/'languages').mkdir(parents=True)
            (root/'languages/de.json').write_text('{"hello":"Hallo"}')
            (root/'languages/en.json').write_text('{"fallback":"English"}')
            (user/'languages/de.json').write_text('{"hello":"Neu"}')
            with patch('monitor.config.ROOT',root),patch('monitor.config.DATA_ROOT',user):
                t=Translator();self.assertEqual(t('hello'),'Neu');self.assertEqual(t('fallback'),'English')
                (user/'languages/de.json').unlink();t.reload();self.assertEqual(t('hello'),'Hallo')
                (user/'languages/fr.json').write_text('{"hello":"Bonjour"}')
                t.reload();self.assertIn('fr',t.catalogs)
                self.assertEqual(t.directory,user/'languages')

    def test_help_uses_same_language_user_then_bundle(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/'system';user=Path(d)/'user'
            (root/'help').mkdir(parents=True);(user/'help').mkdir(parents=True)
            (root/'help/de.html').write_text('<html>Bundled</html>')
            custom=user/'help/de.html';custom.write_text('<html>User</html>')
            with patch.object(constants,'ROOT',root),patch.object(constants,'DATA_ROOT',user):
                self.assertEqual(constants.help_path('de'),custom)
                custom.unlink();self.assertEqual(constants.help_path('de'),root/'help/de.html')
                self.assertFalse(constants.help_path('fr').exists())

    def test_desktop_roundtrip_and_repeated_upgrade(self):
        with tempfile.TemporaryDirectory() as d:
            home=Path(d);desk=home/'Mein Desktop';desk.mkdir();(home/'.config').mkdir()
            (home/'.config/user-dirs.dirs').write_text('XDG_DESKTOP_DIR="$HOME/Mein Desktop"\n')
            self.assertEqual(links.desktop(home),desk)
            unrelated=desk/'notes.txt';unrelated.write_text('Keep')
            paths=[str(desk/name) for name in links.SOURCES]
            links.manage(paths,'install');links.manage(paths,'install')
            self.assertTrue(all(Path(p).is_symlink() for p in paths))
            links.manage(paths,'remove');links.manage(paths,'remove')
            self.assertEqual(list(desk.iterdir()),[unrelated]);self.assertEqual(unrelated.read_text(),'Keep')

    def test_foreign_desktop_file_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'pcmonitor.desktop';p.write_text('Personal')
            with self.assertRaises(FileExistsError):links.manage([str(p)],'install')
            links.manage([str(p)],'remove');self.assertEqual(p.read_text(),'Personal')

    def test_replaced_link_target_is_not_deleted(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'pcmonitor.desktop';target=Path(d)/'personal';target.write_text('Keep')
            p.symlink_to(target)
            links.manage([str(p)],'remove');self.assertTrue(p.is_symlink());self.assertTrue(target.is_file())

    def test_disabled_desktop_and_no_shell_expansion(self):
        with tempfile.TemporaryDirectory() as d:
            home=Path(d);(home/'.config').mkdir();(home/'Desktop').mkdir()
            cfg=home/'.config/user-dirs.dirs'
            for value in ('$HOME','$(touch injected)'):
                cfg.write_text(f'XDG_DESKTOP_DIR="{value}"\n')
                self.assertIsNone(links.desktop(home))

    def test_journal_removed_only_after_successful_cleanup(self):
        with tempfile.TemporaryDirectory() as d:
            state=Path(d)/'state/desktops.json';state.parent.mkdir()
            records=[{'uid':1000,'paths':['/example/pcmonitor.desktop']}]
            state.write_text(json.dumps(records))
            with patch.object(links,'STATE',state),patch.object(links.os,'geteuid',return_value=0),patch.object(links.pwd,'getpwuid',return_value=object()):
                with patch.object(links,'as_user',side_effect=PermissionError('denied')):
                    with self.assertRaises(PermissionError):links.main('remove')
                self.assertEqual(json.loads(state.read_text()),records)
                with patch.object(links,'as_user',return_value=[]):links.main('remove')
                self.assertFalse(state.parent.exists())
