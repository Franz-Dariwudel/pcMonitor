# SPDX-License-Identifier: GPL-3.0-only
"""GTK-Einstellungen für lokale und online angebotene Sprachpakete."""
from concurrent.futures import ThreadPoolExecutor
import logging
from gi.repository import Gtk, GLib
from .constants import ROOT
from .language_packs import fetch_manifest, install_local_pair, install_online_pair, PackError


def add_installer(window, dialog, box, refresh):
    t = window.tr
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='language-download')
    alive = [True]
    busy = [False]
    source = ['']
    caption = Gtk.Label(label=t('packs.title'), xalign=0)
    caption.add_css_class('heading'); box.append(caption)
    hint = Gtk.Label(label=t('packs.hint'), xalign=0, wrap=True, max_width_chars=64)
    box.append(hint)
    local = Gtk.Button(label=t('packs.local'), halign=Gtk.Align.START)
    box.append(local)
    box.append(Gtk.Label(label=t('packs.server'), xalign=0))
    server = Gtk.Entry(text=window.settings.get('language_server', ''), hexpand=True)
    server.set_placeholder_text('https://github.com/Benutzer/pcMonitor')
    box.append(server)
    search = Gtk.Button(label=t('packs.search'), halign=Gtk.Align.START)
    box.append(search)
    choices = Gtk.ComboBoxText(); box.append(choices)
    install = Gtk.Button(label=t('packs.install'), halign=Gtk.Align.START, sensitive=False)
    box.append(install)
    status = Gtk.Label(xalign=0, wrap=True, max_width_chars=64); box.append(status)

    def closed(*_):
        alive[0] = False
        executor.shutdown(wait=False, cancel_futures=True)
    dialog.connect('destroy', closed)
    dialog.connect('close-request', lambda *_: busy[0])

    def run(operation, finished):
        busy[0] = True
        for widget in (local, search, install, server): widget.set_sensitive(False)
        # Der Dialog bleibt bis zum Abschluss offen; die Hardwareanzeige läuft weiter.
        dialog.set_response_sensitive(Gtk.ResponseType.OK, False)
        dialog.set_response_sensitive(Gtk.ResponseType.CANCEL, False)
        status.set_text(t('packs.busy'))
        future = executor.submit(operation)
        def complete():
            if not alive[0]: return False
            busy[0] = False
            for widget in (local, search, server): widget.set_sensitive(True)
            install.set_sensitive(bool(choices.get_active_id()))
            dialog.set_response_sensitive(Gtk.ResponseType.OK, True)
            dialog.set_response_sensitive(Gtk.ResponseType.CANCEL, True)
            try: finished(future.result())
            except Exception as exc:
                code = exc.code if isinstance(exc, PackError) else 'HM504'
                logging.getLogger('monitor').warning('%s: language installation (%s)', code, type(exc).__name__)
                status.set_text(t('packs.error.' + code))
            return False
        future.add_done_callback(lambda _: GLib.idle_add(complete))

    def installed(code):
        refresh()
        status.set_text(t('packs.success', code=code))

    def choose(*_):
        chooser = Gtk.FileChooserNative.new(t('packs.local'), dialog, Gtk.FileChooserAction.OPEN,
                                             t('packs.install'), t('cancel'))
        file_filter = Gtk.FileFilter(); file_filter.set_name('JSON'); file_filter.add_pattern('*.json')
        chooser.add_filter(file_filter)
        dialog._language_chooser = chooser
        def selected(c, response):
            file = c.get_file() if response == Gtk.ResponseType.ACCEPT else None
            path = file.get_path() if file else None
            c.destroy()
            if path and alive[0]:
                run(lambda: install_local_pair(path, t.directory, ROOT/'help'), installed)
        chooser.connect('response', selected); chooser.show()

    def found(entries):
        for code, entry in sorted(entries.items(), key=lambda item: item[1]['name'].casefold()):
            state = t('packs.installed') if code in t.catalogs else t('packs.available')
            choices.append(code, f"{entry['name']} ({code}) · v{entry['version']} / {entry['help']['version']} · {state}")
        choices.set_active(0)
        install.set_sensitive(bool(entries))
        status.set_text(t('packs.found', count=len(entries)))

    def search_clicked(*_):
        source[0] = server.get_text().strip()
        choices.remove_all()
        run(lambda: fetch_manifest(source[0]), found)

    def install_clicked(*_):
        code = choices.get_active_id()
        if code: run(lambda: install_online_pair(source[0], code, t.directory, ROOT/'help'), installed)

    def changed(*_):
        choices.remove_all(); install.set_sensitive(False); status.set_text('')

    server.connect('changed', changed)
    choices.connect('changed', lambda *_: install.set_sensitive(bool(choices.get_active_id()) and not busy[0]))
    local.connect('clicked', choose)
    search.connect('clicked', search_clicked)
    install.connect('clicked', install_clicked)
    return server
