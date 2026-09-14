"""GTK-Dialog und Installation als Hintergrundaufgabe mit isolierten Dateien."""
from pathlib import Path
from tempfile import TemporaryDirectory
import time
import unittest
from unittest.mock import patch
from monitor.app import Gtk, GLib, MonitorWindow
from monitor.config import Translator
from monitor.language_dialog import add_installer
from test_language_packs import DATA, HTML


def children(widget):
    child=widget.get_first_child()
    while child:
        yield child
        yield from children(child)
        child=child.get_next_sibling()

class LanguageDialogTests(unittest.TestCase):
    def test_settings_dialog_opens_and_closes(self):
        if not Gtk.init_check():self.skipTest('No display')
        with TemporaryDirectory() as d:
            window=MonitorWindow(autostart=False,config_path=Path(d)/'settings.json')
            try:
                window.show_settings()
                dialogs=[w for w in Gtk.Window.get_toplevels() if isinstance(w,Gtk.Dialog) and w.get_transient_for()==window]
                self.assertEqual(len(dialogs),1)
                self.assertFalse(any(isinstance(w,Gtk.Entry) for w in children(dialogs[0])))
                labels=[w.get_label() for w in children(dialogs[0]) if isinstance(w,Gtk.Button)]
                self.assertIn(window.tr('packs.search'),labels)
                dialogs[0].response(Gtk.ResponseType.CANCEL)
            finally:window._closing();window.destroy()

    def test_online_pair_install_refreshes_languages(self):
        if not Gtk.init_check():self.skipTest('No display')
        with TemporaryDirectory() as d:
            root=Path(d);lang=root/'languages';lang.mkdir();help_dir=root/'help'
            from monitor.constants import ROOT
            for code in ('de','en'):(lang/f'{code}.json').write_bytes((ROOT/'languages'/f'{code}.json').read_bytes())
            window=MonitorWindow(autostart=False,config_path=root/'settings.json')
            window.tr=Translator(directory=lang)
            window.settings['language_server']='https://github.com/example/repo'
            dialog=Gtk.Dialog(transient_for=window)
            dialog.add_button('Save',Gtk.ResponseType.OK);dialog.add_button('Cancel',Gtk.ResponseType.CANCEL)
            box=dialog.get_content_area();refreshed=[]
            entries={'fr':{'name':'Français','version':1,'help':{'version':1}}}
            def wait_until(predicate):
                deadline=time.monotonic()+3
                while not predicate() and time.monotonic()<deadline:
                    while GLib.MainContext.default().pending():GLib.MainContext.default().iteration(False)
                    time.sleep(.01)
                self.assertTrue(predicate())
            from monitor.language_packs import install_pair
            def install(server,code,directory,help_directory,download_directory):
                from monitor.constants import LANGUAGE_SERVER
                self.assertEqual(server,LANGUAGE_SERVER)
                self.assertEqual(download_directory,root/'Downloads')
                self.assertEqual(help_directory,help_dir)
                return install_pair(DATA,HTML,code,directory,help_directory)
            try:
                with patch('monitor.language_dialog.fetch_manifest',return_value=entries),patch('monitor.language_dialog.DATA_ROOT',root),patch('monitor.language_dialog.DOWNLOAD_ROOT',root/'Downloads'),patch('monitor.language_dialog.install_online_pair',side_effect=install):
                    add_installer(window,dialog,box,lambda:(window.tr.reload(),refreshed.append(True)))
                    buttons={w.get_label():w for w in children(box) if isinstance(w,Gtk.Button)}
                    self.assertNotIn(window.tr('packs.local'),buttons)
                    buttons[window.tr('packs.search')].emit('clicked')
                    install_button=buttons[window.tr('packs.install')]
                    wait_until(install_button.get_sensitive)
                    install_button.emit('clicked');wait_until(lambda:bool(refreshed))
                    self.assertIn('fr',window.tr.catalogs)
                    self.assertEqual((help_dir/'fr.html').read_bytes(),HTML)
            finally:dialog.destroy();window._closing();window.destroy()
