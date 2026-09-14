# SPDX-License-Identifier: GPL-3.0-only
"""GTK-Einstellungen für Sprachpakete aus der festen GitHub-Quelle."""
from concurrent.futures import ThreadPoolExecutor
import logging
from gi.repository import Gtk, GLib
from .constants import DATA_ROOT, LANGUAGE_SERVER, DOWNLOAD_ROOT
from .language_packs import fetch_manifest, install_online_pair, PackError


def add_installer(window, dialog, box, refresh):
    t = window.tr
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='language-download')
    alive = [True]
    busy = [False]
    caption = Gtk.Label(label=t('packs.title'), xalign=0)
    caption.add_css_class('heading'); box.append(caption)
    hint = Gtk.Label(label=t('packs.hint'), xalign=0, wrap=True, max_width_chars=64)
    box.append(hint)
    box.append(Gtk.Label(label=t('packs.download_hint', directory=str(DOWNLOAD_ROOT)), xalign=0, wrap=True, max_width_chars=64))
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
        for widget in (search, install): widget.set_sensitive(False)
        # Der Dialog bleibt bis zum Abschluss offen; die Hardwareanzeige läuft weiter.
        dialog.set_response_sensitive(Gtk.ResponseType.OK, False)
        dialog.set_response_sensitive(Gtk.ResponseType.CANCEL, False)
        status.set_text(t('packs.busy'))
        future = executor.submit(operation)
        def complete():
            if not alive[0]: return False
            busy[0] = False
            search.set_sensitive(True)
            install.set_sensitive(bool(choices.get_active_id()))
            dialog.set_response_sensitive(Gtk.ResponseType.OK, True)
            dialog.set_response_sensitive(Gtk.ResponseType.CANCEL, True)
            try: finished(future.result())
            except Exception as exc:
                code = exc.code if isinstance(exc, PackError) else 'HM504'
                logging.getLogger('monitor').warning('%s: language installation (%s)', code, type(exc).__name__)
                if code == 'HM506': refresh()
                status.set_text(t('packs.error.' + code))
            return False
        future.add_done_callback(lambda _: GLib.idle_add(complete))

    def installed(code):
        refresh()
        status.set_text(t('packs.success', code=code))

    def found(entries):
        for code, entry in sorted(entries.items(), key=lambda item: item[1]['name'].casefold()):
            state = t('packs.installed') if code in t.catalogs else t('packs.available')
            choices.append(code, f"{entry['name']} ({code}) · v{entry['version']} / {entry['help']['version']} · {state}")
        choices.set_active(0)
        install.set_sensitive(bool(entries))
        status.set_text(t('packs.found', count=len(entries)))

    def search_clicked(*_):
        choices.remove_all()
        run(lambda: fetch_manifest(LANGUAGE_SERVER), found)

    def install_clicked(*_):
        code = choices.get_active_id()
        if code: run(lambda: install_online_pair(LANGUAGE_SERVER, code, t.directory, DATA_ROOT/'help', DOWNLOAD_ROOT), installed)

    choices.connect('changed', lambda *_: install.set_sensitive(bool(choices.get_active_id()) and not busy[0]))
    search.connect('clicked', search_clicked)
    install.connect('clicked', install_clicked)
