#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""DEB für Linux Mint mit zwei Desktopstartern aus einer sauberen Ausgabe bauen.

Aufruf: python3 build.py, danach python3 build_deb.py.
Die DEB-Ausgabe enthält portablen Python-Quellcode und nutzt System-Python/GTK.
Keine persönlichen Daten, kein privates Startskript, keine Build-Caches.
"""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import zipfile
from monitor.constants import ROOT, VERSION


def write(root, name, text, executable=False):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')
    path.chmod(0o755 if executable else 0o644)


def main():
    archive = ROOT / 'dist' / f'pcMonitor-{VERSION}-quellcode.zip'
    if not archive.is_file(): raise FileNotFoundError('Zuerst python3 build.py ausführen')
    with tempfile.TemporaryDirectory(dir=ROOT/'work', prefix='deb-') as temporary:
        base = Path(temporary)
        with zipfile.ZipFile(archive) as z: z.extractall(base/'source')
        source = base/'source'/f'pcMonitor-{VERSION}'
        package = base/'package'
        app = package/'usr/lib/pcmonitor'
        app.mkdir(parents=True)
        for name in ('monitor', 'resources'):
            shutil.copytree(source/name, app/name)
        for name in ('launcher.py', 'admin_worker.py'):
            shutil.copy2(source/name, app/name)
        for folder in ('languages', 'help'):
            (app/folder).mkdir()
            for code in ('de', 'en'):
                suffix = '.json' if folder == 'languages' else '.html'
                shutil.copy2(source/folder/(code+suffix), app/folder/(code+suffix))
        write(package, 'usr/lib/pcmonitor/deb-install.json', json.dumps({'version': VERSION})+'\n')
        write(package, 'usr/bin/pcmonitor', '#!/bin/sh\nexec /usr/bin/python3 -B /usr/lib/pcmonitor/launcher.py "$@"\n', True)
        shutil.copy2(ROOT/'packaging/desktop_links.py', app/'desktop_links.py')
        for admin in (False, True):
            stem = 'pcmonitor-admin' if admin else 'pcmonitor'
            title = 'pcMonitor (Admin)' if admin else 'pcMonitor'
            icon = 'pc-hardware-monitor-3d.png'
            write(package, f'usr/share/applications/{stem}.desktop',
                  '[Desktop Entry]\nType=Application\nVersion=1.0\n'
                  f'Name={title}\nComment=Linux hardware information\n'
                  'Comment[de]=Hardwareinformationen unter Linux\n'
                  f'Exec=/usr/bin/pcmonitor{" --admin" if admin else ""}\n'
                  f'Icon=/usr/lib/pcmonitor/resources/{icon}\n'
                  'Terminal=false\nCategories=System;Monitor;\nStartupNotify=true\n', True)
        doc = package/'usr/share/doc/pcmonitor';doc.mkdir(parents=True)
        for name in ('README.md', 'CHANGELOG.md'):
            shutil.copy2(source/name, doc/name)
        shutil.copy2(source/'LICENSE', doc/'copyright')
        write(package, 'DEBIAN/postinst', '#!/bin/sh\nset -e\ncase "$1" in\n configure) python3 -B /usr/lib/pcmonitor/desktop_links.py install ;;\nesac\n', True)
        write(package, 'DEBIAN/prerm', '#!/bin/sh\nset -e\ncase "$1" in\n remove|deconfigure) python3 -B /usr/lib/pcmonitor/desktop_links.py remove ;;\nesac\n', True)
        size = sum(p.stat().st_size for p in package.rglob('*') if p.is_file())//1024+1
        write(package, 'DEBIAN/control',
              f'Package: pcmonitor\nVersion: {VERSION}\nArchitecture: all\n'
              'Section: utils\nPriority: optional\nMaintainer: Josef Lehner <office@dogtruck.eu>\n'
              f'Installed-Size: {size}\nDepends: python3 (>= 3.10), python3-gi, gir1.2-gtk-4.0 (>= 4.8), pkexec\n'
              'Recommends: pciutils, usbutils, dmidecode, smartmontools, nvme-cli, lm-sensors, ethtool, iproute2, util-linux, pulseaudio-utils\n'
              'Homepage: https://github.com/Franz-Dariwudel/pcMonitor\n'
              'Description: GTK 4 hardware monitor for Linux Mint\n'
              ' Read-only hardware information, German and English, downloadable language\n'
              ' and HTML help packages, normal and administrator desktop launchers.\n')
        files = sorted(p for p in (package/'usr').rglob('*') if p.is_file())
        write(package, 'DEBIAN/md5sums', ''.join(hashlib.md5(p.read_bytes()).hexdigest()+'  '+str(p.relative_to(package))+'\n' for p in files))
        target = ROOT/'dist'/f'pcmonitor_{VERSION}_all.deb'
        subprocess.run(['dpkg-deb', '--root-owner-group', '--build', str(package), str(target)], check=True)
        print(target)


if __name__ == '__main__': main()
