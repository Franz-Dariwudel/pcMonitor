#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Sichtbare Startfehler und vollständiges Startprotokoll, ohne GTK-Abhängigkeit.

Der Starter läuft unter dem System-Python, prüft Voraussetzungen und meldet
auch Importfehler oder einen Grafikabsturz des Kindprozesses sichtbar. Keine
Pakete werden ungefragt installiert und keine Daten zurückgesetzt.
"""
from datetime import datetime
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parent


def show_error(message):
    """Bei Desktopstarts bleibt eine verständliche Fehlermeldung sichtbar."""
    text=message+'\n\nProtokoll / Log: '+str(ROOT/'logs/start.log')
    print(text,file=sys.stderr)
    if sys.stderr.isatty() or not (os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY')):
        return
    for command in (
        ['zenity','--error','--title=pcMonitor – Startfehler','--width=620','--text='+text],
        ['xmessage','-center','-title','pcMonitor – Startfehler',text],
    ):
        if shutil.which(command[0]):
            try:subprocess.run(command,check=False)
            except OSError:continue
            return


def preflight(root=ROOT):
    if sys.version_info<(3,10):return 'HM001: Python 3.10 oder neuer erforderlich / Python 3.10+ required.'
    for name in ('__main__','app','scanner','config','constants'):
        if not any((root/'monitor'/(name+ext)).is_file() for ext in ('.py','.pyc')):
            return 'HM003: Programmdatei fehlt / Missing program file: monitor/'+name
    from monitor import configure_rendering
    configure_rendering()
    probe=subprocess.run([sys.executable,'-c',
        'import gi; gi.require_version("Gtk","4.0"); from gi.repository import Gtk; '
        'print("GTK %s.%s.%s" % (Gtk.get_major_version(),Gtk.get_minor_version(),Gtk.get_micro_version())); '
        'raise SystemExit(0 if (Gtk.get_major_version(),Gtk.get_minor_version()) >= (4,8) else 4)'],
        capture_output=True,text=True)
    if probe.returncode:
        detail=probe.stderr.strip() or probe.stdout.strip()
        return ('HM002: GTK 4.8+ und PyGObject fehlen oder passen nicht zum Python.\n'
                'Systempakete: python3-gi und gir1.2-gtk-4.0.\n'
                'GTK 4.8+ and PyGObject are required.\n'+detail)
    return None


def main(argv=None):
    arguments=list(sys.argv[1:] if argv is None else argv)
    try:
        (ROOT/'logs').mkdir(exist_ok=True)
        logfile=(ROOT/'logs/start.log').open('a',encoding='utf-8')
    except OSError as exc:
        show_error('HM101: logs/ ist nicht beschreibbar / not writable: '+str(exc));return 1
    with logfile:
        def record(text):
            logfile.write(text.rstrip()+'\n');logfile.flush()
        record('\n=== '+datetime.now().isoformat(timespec='seconds')+' ===')
        record('Ordner: '+str(ROOT))
        record('Python: '+sys.executable+' '+sys.version.split()[0])
        try:
            error=preflight()
            if error:
                record(error);show_error(error);return 1
            environment=os.environ.copy()
            environment['PYTHONDONTWRITEBYTECODE']='1'
            environment['XDG_CACHE_HOME']=str(ROOT/'cache')
            if '--software-rendering' in arguments:
                arguments.remove('--software-rendering')
                environment['GSK_RENDERER']='cairo'
            from monitor import configure_rendering
            configure_rendering(environment)
            record('Rendering: '+environment.get('GSK_RENDERER','default'))
            child=subprocess.Popen([sys.executable,'-m','monitor',*arguments],cwd=ROOT,
                                    env=environment,stderr=subprocess.PIPE,text=True,errors='replace')
            recent=[]
            for line in child.stderr:
                record(line);print(line,end='',file=sys.stderr)
                recent.append(line.rstrip());recent=recent[-12:]
            code=child.wait()
            record('Exitcode: '+str(code))
            if code:
                show_error('HM199: pcMonitor wurde mit Fehler beendet / exited with an error.\n'
                           +'\n'.join(recent[-8:]))
            return code if code>=0 else 1
        except OSError as exc:
            message='HM003: Start fehlgeschlagen / launch failed: '+str(exc)
            record(message);show_error(message);return 1


if __name__=='__main__':raise SystemExit(main())
