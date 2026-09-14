#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Saubere Quellcode- und Bytecode-Ausgabe mit Standardsprachen erstellen.

Persönliche Einstellungen, Protokolle, Scan-Daten und private Startdateien
werden nicht kopiert. Alle temporären Dateien entstehen unter work/.
"""
import hashlib
import json
from pathlib import Path
import py_compile
import shutil
import sys
import tarfile
import tempfile
import zipfile
from monitor.constants import ROOT,VERSION


def main():
    (ROOT/'dist').mkdir(exist_ok=True);(ROOT/'work').mkdir(exist_ok=True)
    # Öffentlicher Sprachserver enthält ausschließlich die zwei Standardpakete.
    packs=ROOT/'dist/pcMonitor-sprachpakete';packs.mkdir(exist_ok=True)
    manifest={'version':1,'languages':{},'help':{}}
    for code in ('de','en'):
        for folder,suffix,key in (('languages','.json','languages'),('help','.html','help')):
            source=ROOT/folder/(code+suffix)
            (packs/folder).mkdir(exist_ok=True)
            shutil.copy2(source,packs/folder/source.name)
            entry={'version':int(VERSION.replace('.','')),'file':folder+'/'+source.name,
                   'sha256':hashlib.sha256(source.read_bytes()).hexdigest()}
            if key=='languages':entry['name']=json.loads(source.read_text())['language.name']
            manifest[key][code]=entry
    (packs/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    print(packs)
    with tempfile.TemporaryDirectory(dir=ROOT/'work',prefix='build-') as d:
        stage=Path(d)/f'pcMonitor-{VERSION}';stage.mkdir()
        for name in ('monitor','resources','tests'):
            shutil.copytree(ROOT/name,stage/name,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
        for name in ('languages','help'):
            shutil.copytree(packs/name,stage/name)
        shutil.copy2(packs/'manifest.json',stage/'manifest.json')
        for name in ('README.md','CHANGELOG.md','LICENSE','build.py','install.py','admin_worker.py','launcher.py','pyproject.toml'):
            shutil.copy2(ROOT/name,stage/name)
        info={'version':VERSION,'kind':'source','python':f'{sys.version_info.major}.{sys.version_info.minor}',
              'gtk':'>=4.8','languages':['de','en'],'personal_data':False}
        (stage/'build-info.json').write_text(json.dumps(info,indent=2))
        for p in stage.rglob('*'):p.chmod(0o755 if p.is_dir() else 0o644)
        archive=ROOT/'dist'/f'pcMonitor-{VERSION}-quellcode.zip'
        with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED) as z:
            for p in sorted(stage.rglob('*')):
                if p.is_file():z.write(p,p.relative_to(stage.parent))
        print(archive)
        for p in [*(stage/'monitor').glob('*.py'),stage/'admin_worker.py']:
            py_compile.compile(str(p),cfile=str(p.with_suffix('.pyc')),dfile=str(p.relative_to(stage)),doraise=True)
            p.unlink()
        shutil.rmtree(stage/'tests');(stage/'build.py').unlink()
        info['kind']='bytecode';(stage/'build-info.json').write_text(json.dumps(info,indent=2))
        archive=ROOT/'dist'/f"pcMonitor-{VERSION}-python{info['python']}-kompiliert.tar.gz"
        with tarfile.open(archive,'w:gz') as t:t.add(stage,arcname=stage.name)
        print(archive)

if __name__=='__main__':main()
