#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Installiere die entpackte Ausgabe in einen leeren Benutzerordner."""
import argparse
import json
from pathlib import Path
import shutil
import sys


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory',type=Path,required=True)
    args=parser.parse_args()
    source=Path(__file__).resolve().parent
    target=args.directory.expanduser()
    if not target.is_absolute():parser.error('Absoluter Zielordner erforderlich / absolute directory required')
    target=target.resolve()
    if target==source or target.is_relative_to(source):parser.error('Ziel muss außerhalb des Pakets liegen / target must be outside package')
    if target.exists() and (not target.is_dir() or any(target.iterdir())):parser.error('Ziel ist nicht leer / target is not empty')
    info_path=source/'build-info.json'
    if info_path.exists():
        info=json.loads(info_path.read_text())
        if info['kind']=='bytecode' and info['python']!=f'{sys.version_info.major}.{sys.version_info.minor}':
            parser.error('Python '+info['python']+' erforderlich / required')
    target.mkdir(parents=True,exist_ok=True)
    for p in source.iterdir():
        if p.name in ('install.py','__pycache__'):continue
        if p.is_dir():shutil.copytree(p,target/p.name)
        else:shutil.copy2(p,target/p.name)
    for name in ('config','logs','cache'):(target/name).mkdir(exist_ok=True)
    print('Installiert / installed: '+str(target))
    print('Im Zielordner starten / run in target: python3 -m monitor')
    return 0

if __name__=='__main__':raise SystemExit(main())
