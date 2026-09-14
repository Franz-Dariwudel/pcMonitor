# SPDX-License-Identifier: GPL-3.0-only
"""Programmidentität, Programmressourcen und benutzerspezifische Speicherorte."""
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
VERSION = '1.7.4'
APP_ID = 'eu.dogtruck.HardwareMonitor'
APP_NAME = 'pcMonitor'
AUTHOR = 'Josef Lehner'
WEBSITE = 'https://dogtruck.eu'

LANGUAGE_SERVER = 'https://github.com/Franz-Dariwudel/pcMonitor'

DOWNLOAD_ROOT = Path.home() / 'Downloads'

# Nur die DEB-Ausgabe trägt diesen Marker. Entpackte Ausgaben bleiben portabel.
SYSTEM_INSTALL = (ROOT / 'deb-install.json').is_file()
DATA_ROOT = Path.home() / '.local/share/pcMonitor' if SYSTEM_INSTALL else ROOT


def help_path(code):
    """Installierte Benutzerhilfe vor mitgelieferter gleichsprachiger Hilfe lesen."""
    candidate = DATA_ROOT / 'help' / f'{code}.html'
    return candidate if candidate.exists() else ROOT / 'help' / f'{code}.html'
