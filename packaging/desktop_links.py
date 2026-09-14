#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-only
"""DEB-Desktopstarter erfassen und mit den Rechten ihres Besitzers verwalten.

Die Paketverwaltung entfernt die Systemdateien. Dieses Hilfsprogramm verwaltet
nur die zwei zusätzlich in vorhandenen Benutzer-Desktops angelegten Symlinks.
Das Journal wird vor dem Anlegen geschrieben; wiederholte Aufrufe sind möglich.
Benutzerkonfiguration wird niemals als Shellcode ausgeführt.
"""
import json
import os
from pathlib import Path
import pwd
import re
import subprocess
import sys

STATE = Path('/var/lib/pcmonitor/desktops.json')
SOURCES = {name: '/usr/share/applications/' + name for name in
           ('pcmonitor.desktop', 'pcmonitor-admin.desktop')}


def desktop(home):
    """XDG-Desktop lesen, ohne Shellauswertung; abgeschaltete Desktops auslassen."""
    home = Path(home)
    config = home / '.config/user-dirs.dirs'
    if config.is_file():
        for line in config.read_text(encoding='utf-8').splitlines():
            match = re.fullmatch(r'\s*XDG_DESKTOP_DIR="([^"\n]*)"\s*', line)
            if match:
                raw = match[1]
                if raw == '$HOME': return None
                if raw.startswith('$HOME/'): raw = str(home) + raw[5:]
                path = Path(raw)
                if path.is_absolute() and path != home and path.is_dir(): return path
                return None
    for name in ('Schreibtisch', 'Desktop'):
        path = home / name
        if path.is_dir(): return path
    return None


def manage(paths, action):
    """Nur eigene Symlinks bearbeiten; Zielrechte stammen aus dem DEB-Paket."""
    for raw in paths:
        path = Path(raw)
        source = SOURCES[path.name]
        if action == 'install':
            if path.is_symlink() and os.readlink(path) == source: continue
            if path.exists() or path.is_symlink():
                raise FileExistsError('Desktop-Datei bereits vorhanden: ' + str(path))
            path.symlink_to(source)
        elif path.is_symlink() and os.readlink(path) == source:
            path.unlink()
        elif path.exists() or path.is_symlink():
            print('Fremde/ersetzte Desktop-Datei bleibt erhalten: ' + str(path), file=sys.stderr)


def as_user(account, action, paths=()):
    """Alle Zugriffe im Home mit Benutzerrechten, auch bei manipulierten Pfaden."""
    def drop():
        os.setgroups([])
        os.setgid(account.pw_gid)
        os.setuid(account.pw_uid)
    result = subprocess.run(
        ['/usr/bin/python3', '-B', str(Path(__file__).resolve()), '--user', action,
         account.pw_dir, json.dumps(list(paths))],
        env={'HOME': account.pw_dir, 'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8'},
        cwd='/', preexec_fn=drop, check=True, text=True, stdout=subprocess.PIPE)
    return json.loads(result.stdout)


def save(records):
    STATE.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
    temporary = STATE.with_suffix('.tmp')
    temporary.write_text(json.dumps(records, indent=2) + '\n', encoding='utf-8')
    temporary.replace(STATE)


def main(action):
    if os.geteuid() != 0: raise PermissionError('Paketverwaltung benötigt root')
    records = json.loads(STATE.read_text()) if STATE.exists() else []
    if action == 'install':
        for account in pwd.getpwall():
            if not 1000 <= account.pw_uid < 65534 or not Path(account.pw_dir).is_dir(): continue
            paths = as_user(account, 'plan')
            if not paths: continue
            record = {'uid': account.pw_uid, 'paths': paths}
            if record not in records:
                records.append(record)
                save(records)
            as_user(account, 'install', paths)
    elif action == 'remove':
        for record in records[:]:
            try: account = pwd.getpwuid(record['uid'])
            except KeyError:
                raise RuntimeError('Benutzer fehlt; Desktop-Dateien prüfen: ' + repr(record['paths']))
            as_user(account, 'remove', record['paths'])
            records.remove(record)
            save(records)
        STATE.unlink(missing_ok=True)
        if STATE.parent.exists(): STATE.parent.rmdir()
    else: raise ValueError(action)


if __name__ == '__main__':
    try:
        if sys.argv[1] == '--user':
            action, home, serialized = sys.argv[2:]
            if action == 'plan':
                folder = desktop(home)
                result = [str(folder / name) for name in SOURCES] if folder else []
            else:
                manage(json.loads(serialized), action)
                result = []
            print(json.dumps(result))
        else: main(sys.argv[1])
    except Exception as exc:
        print('pcMonitor Desktop: ' + str(exc), file=sys.stderr)
        raise SystemExit(1)
