"""Dateischutz und Online-Installation ohne externe Netzwerkabhängigkeit prüfen."""
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from monitor.language_packs import (PackError, fetch_manifest, install_local_pair,
                                    install_online_pair, install_pair, help_document, server_url, LIMIT)
from monitor.config import Translator, load_settings, save_settings

DATA = json.dumps({'language.name': 'Français', 'ports': 'Ports'}).encode()

HTML = b'<!doctype html><html><head><title>Help</title></head><body><h1>Help</h1></body></html>'


def install_local(path, directory):
    path.with_suffix('.html').write_bytes(HTML)
    return install_local_pair(path,directory,Path(directory).parent/'installed-help')


def install_online(server, code, directory):
    return install_online_pair(server,code,directory,Path(directory)/'help',Path(directory)/'download')


def manifest(path='languages/fr.json', digest=None):
    return json.dumps({'version': 1, 'languages': {'fr': {
        'name': 'Français', 'version': 1, 'file': path,
        'sha256': digest or hashlib.sha256(DATA).hexdigest()}},
        'help':{'fr':{'version':1,'file':'help/fr.html','sha256':hashlib.sha256(HTML).hexdigest()}}}).encode()

class PackTests(unittest.TestCase):
    def test_github_and_https_sources(self):
        self.assertEqual(server_url('https://github.com/person/project'),
                         'https://raw.githubusercontent.com/person/project/main/')
        self.assertEqual(server_url('https://github.com/person/project/tree/stable/packs'),
                         'https://raw.githubusercontent.com/person/project/stable/packs/')
        for value in ('http://example.org', 'https://user:pass@example.org', 'https://github.com/login', 'file:///tmp', 'https://['):
            with self.subTest(value=value), self.assertRaises(PackError): server_url(value)

    def test_local_install_becomes_available_without_restart(self):
        with TemporaryDirectory() as d:
            root=Path(d);folder=root/'languages';folder.mkdir()
            tr=Translator(directory=folder)
            source=root/'fr.json';source.write_bytes(DATA)
            install_local(source,folder);tr.reload()
            self.assertEqual(tr.language,'fr');self.assertEqual(tr('ports'),'Ports')

    def test_bad_files_leave_installed_language_unchanged(self):
        with TemporaryDirectory() as d:
            root=Path(d);folder=root/'languages';folder.mkdir()
            target=folder/'fr.json';target.write_bytes(DATA)
            source=root/'fr.json'
            for bad in (b'[]',b'{}',b'\xff',b'{"language.name":false}',b' '*(LIMIT+1)):
                source.write_bytes(bad)
                with self.assertRaises(PackError):install_local(source,folder)
                self.assertEqual(target.read_bytes(),DATA)
            source.write_bytes(DATA)
            with patch('monitor.language_packs.os.replace',side_effect=PermissionError()):
                with self.assertRaisesRegex(PackError,'HM504'):install_local(source,folder)
            self.assertEqual(target.read_bytes(),DATA)
            self.assertEqual(list(folder.iterdir()),[target])

    def test_online_checksum_and_path_protection(self):
        with TemporaryDirectory() as d:
            target=Path(d)/'fr.json';target.write_bytes(b'old')
            with patch('monitor.language_packs.download',side_effect=[manifest(digest='0'*64),DATA,HTML]):
                with self.assertRaisesRegex(PackError,'HM503'):install_online('https://example.org','fr',d)
            self.assertEqual(target.read_bytes(),b'old')
            for path in ('../fr.json','/fr.json','https://other.org/fr.json','lang/../../fr.json','lang/fr.py','lang//fr.json'):
                with patch('monitor.language_packs.download',return_value=manifest(path)):
                    with self.assertRaises(PackError):fetch_manifest('https://example.org')
            with patch('monitor.language_packs.download',side_effect=[manifest(),DATA,HTML]):
                install_online('https://github.com/person/project','fr',d)
            self.assertEqual(target.read_bytes(),DATA)

    def test_english_fallback_cannot_lose_keys(self):
        with TemporaryDirectory() as d:
            root=Path(d);folder=root/'languages';folder.mkdir()
            target=folder/'en.json';target.write_text('{"language.name":"English","close":"Close"}')
            source=root/'en.json';source.write_text('{"language.name":"English"}')
            with self.assertRaises(PackError):install_local(source,folder)
            self.assertIn('close',json.loads(target.read_text()))

    def test_server_setting_persists(self):
        with TemporaryDirectory() as d:
            p=Path(d)/'settings.json';settings=load_settings(p)[0]
            settings['language_server']='https://github.com/person/project'
            save_settings(settings,p)
            self.assertEqual(load_settings(p)[0],settings)

    def test_missing_or_active_help_preserves_both_files(self):
        with TemporaryDirectory() as d:
            root=Path(d);language=root/'languages';help_dir=root/'installed-help'
            language.mkdir();help_dir.mkdir()
            (language/'fr.json').write_bytes(DATA);(help_dir/'fr.html').write_bytes(HTML)
            source=root/'fr.json';source.write_bytes(DATA)
            with self.assertRaisesRegex(PackError,'HM505'):
                install_local_pair(source,language,help_dir)
            for unsafe in (b'<html><body><script>alert(1)</script></body></html>',
                           b'<html><body onload="alert(1)">Help</body></html>',
                           b'<html><body><a href="javascript:alert(1)">Help</a></body></html>'):
                source.with_suffix('.html').write_bytes(unsafe)
                with self.assertRaisesRegex(PackError,'HM505'):
                    install_local_pair(source,language,help_dir)
                self.assertEqual((language/'fr.json').read_bytes(),DATA)
                self.assertEqual((help_dir/'fr.html').read_bytes(),HTML)

    def test_second_replace_failure_rolls_back_first_file(self):
        import os
        with TemporaryDirectory() as d:
            root=Path(d);language=root/'languages';help_dir=root/'help'
            language.mkdir();help_dir.mkdir()
            (language/'fr.json').write_bytes(DATA);(help_dir/'fr.html').write_bytes(HTML)
            real_replace=os.replace
            def fail_second(source,target):
                if str(source).split('/')[-1].startswith('.pack-new-') and str(target).endswith('.html'):
                    raise PermissionError()
                real_replace(source,target)
            with patch('monitor.language_packs.os.replace',side_effect=fail_second):
                with self.assertRaisesRegex(PackError,'HM504'):
                    install_pair(b'{"language.name":"Updated"}',HTML,'fr',language,help_dir)
            self.assertEqual((language/'fr.json').read_bytes(),DATA)
            self.assertEqual((help_dir/'fr.html').read_bytes(),HTML)
            self.assertEqual(len(list(root.rglob('.*'))),0)

    def test_shipped_help_is_installable(self):
        from monitor.constants import ROOT
        for code in ('de','en'):
            help_document((ROOT/'help'/f'{code}.html').read_bytes())

    def test_fresh_manifest_and_downloads_saved_before_install(self):
        from monitor.language_packs import install_online_pair,fetch_manifest
        with TemporaryDirectory() as d:
            root=Path(d)
            with patch('monitor.language_packs.download',side_effect=[manifest(),manifest(),manifest(),DATA,HTML]) as fetch:
                fetch_manifest('https://example.org')
                fetch_manifest('https://example.org')
                first,second=[call.args[0] for call in fetch.call_args_list]
                self.assertNotEqual(first,second)
                self.assertTrue(first.startswith('https://example.org/manifest.json?pcmonitor='))
                install_online_pair('https://example.org','fr',root/'languages',root/'help',root/'download')
                self.assertIn('?sha256=',fetch.call_args_list[-1].args[0])
            for folder,ext,expected in (('languages','.json',DATA),('help','.html',HTML)):
                self.assertFalse((root/'download'/folder/('fr'+ext)).exists())
                self.assertEqual((root/folder/('fr'+ext)).read_bytes(),expected)

    def test_unwritable_download_does_not_change_active_pair(self):
        from monitor.language_packs import install_online_pair
        with TemporaryDirectory() as d:
            root=Path(d);(root/'languages').mkdir();(root/'help').mkdir()
            (root/'languages/fr.json').write_bytes(DATA);(root/'help/fr.html').write_bytes(HTML)
            blocked=root/'download';blocked.write_text('not a directory')
            with patch('monitor.language_packs.download',side_effect=[manifest(),DATA,HTML]):
                with self.assertRaisesRegex(PackError,'HM504'):
                    install_online_pair('https://example.org','fr',root/'languages',root/'help',blocked)
            self.assertEqual((root/'languages/fr.json').read_bytes(),DATA)
            self.assertEqual((root/'help/fr.html').read_bytes(),HTML)

    def test_saved_download_hashes_are_rechecked(self):
        from monitor.language_packs import install_local_pair
        with TemporaryDirectory() as d:
            root=Path(d);(root/'fr.json').write_bytes(DATA);(root/'fr.html').write_bytes(HTML)
            with self.assertRaisesRegex(PackError,'HM503'):
                install_local_pair(root/'fr.json',root/'languages',root/'help',('0'*64,hashlib.sha256(HTML).hexdigest()))
            self.assertFalse((root/'languages').exists())

    def test_default_download_location_and_unrelated_files_preserved(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp);downloads=root/'Downloads'
            (downloads/'languages').mkdir(parents=True)
            other=downloads/'languages/other.json';other.write_text('keep')
            actual_install=install_local_pair
            def inspect(path,directory,help_directory,expected_hashes):
                self.assertEqual(path,downloads/'languages/fr.json')
                self.assertEqual(path.read_bytes(),DATA)
                self.assertEqual((downloads/'help/fr.html').read_bytes(),HTML)
                return actual_install(path,directory,help_directory,expected_hashes)
            with patch('monitor.language_packs.DOWNLOAD_ROOT',downloads),patch('monitor.language_packs.download',side_effect=[manifest(),DATA,HTML]),patch('monitor.language_packs.install_local_pair',side_effect=inspect):
                install_online_pair('https://example.org','fr',root/'active/languages',root/'active/help')
            self.assertFalse((downloads/'languages/fr.json').exists())
            self.assertFalse((downloads/'help/fr.html').exists())
            self.assertEqual(other.read_text(),'keep')
            self.assertEqual((root/'active/languages/fr.json').read_bytes(),DATA)

    def test_failed_install_keeps_download_pair(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp)
            with patch('monitor.language_packs.download',side_effect=[manifest(),DATA,HTML]),patch('monitor.language_packs.install_local_pair',side_effect=PackError('HM504')):
                with self.assertRaisesRegex(PackError,'HM504'):
                    install_online_pair('https://example.org','fr',root/'active/languages',root/'active/help',root/'Downloads')
            self.assertEqual((root/'Downloads/languages/fr.json').read_bytes(),DATA)
            self.assertEqual((root/'Downloads/help/fr.html').read_bytes(),HTML)

    def test_cleanup_failure_reports_successful_install_and_keeps_files(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp);unlink=Path.unlink
            def refuse(path,*args,**kwargs):
                if path==root/'Downloads/languages/fr.json':raise PermissionError('denied')
                return unlink(path,*args,**kwargs)
            with patch('monitor.language_packs.download',side_effect=[manifest(),DATA,HTML]),patch.object(Path,'unlink',refuse):
                with self.assertRaisesRegex(PackError,'HM506'):
                    install_online_pair('https://example.org','fr',root/'active/languages',root/'active/help',root/'Downloads')
            self.assertEqual((root/'active/languages/fr.json').read_bytes(),DATA)
            self.assertEqual((root/'active/help/fr.html').read_bytes(),HTML)
            self.assertTrue((root/'Downloads/languages/fr.json').exists())

    def test_cleanup_never_deletes_installed_files_if_paths_coincide(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp)
            with patch('monitor.language_packs.download',side_effect=[manifest(),DATA,HTML]):
                install_online_pair('https://example.org','fr',root/'languages',root/'help',root)
            self.assertEqual((root/'languages/fr.json').read_bytes(),DATA)
            self.assertEqual((root/'help/fr.html').read_bytes(),HTML)
