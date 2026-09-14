# SPDX-License-Identifier: GPL-3.0-only
"""Atomare Konfiguration und dynamische, unabhängig erkannte Sprachkataloge."""
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import tempfile
from .constants import ROOT, LANGUAGE_SERVER


def setup_logs():
    logger=logging.getLogger('monitor')
    if logger.handlers:return logger
    logger.setLevel(logging.INFO)
    try:
        (ROOT/'logs').mkdir(exist_ok=True)
        handler=RotatingFileHandler(ROOT/'logs/monitor.log',maxBytes=500000,backupCount=3,encoding='utf-8')
    except OSError:
        handler=logging.StreamHandler()
        print('HM101: logs/ ist nicht beschreibbar / log directory is not writable.')
    handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
    logger.addHandler(handler)
    return logger


def load_settings(path=None):
    path=path or ROOT/'config/settings.json'
    standard={'language':'de','show_empty':False,'interval':3,'language_server':LANGUAGE_SERVER}
    try:
        raw=json.loads(Path(path).read_text(encoding='utf-8'))
        if not isinstance(raw,dict):raise ValueError('JSON object required')
    except FileNotFoundError:return standard,[]
    except (OSError,ValueError,UnicodeError) as exc:
        logging.getLogger('monitor').warning('HM102: %s (%s)',path,type(exc).__name__)
        return standard,['HM102']
    if isinstance(raw.get('language'),str):standard['language']=raw['language']
    if isinstance(raw.get('show_empty'),bool):standard['show_empty']=raw['show_empty']
    if type(raw.get('interval')) is int and raw['interval'] in (0,2,3,5,10):standard['interval']=raw['interval']
    if isinstance(raw.get('language_server'),str):standard['language_server']=raw['language_server']
    return standard,[]


def save_settings(settings,path=None):
    target=Path(path or ROOT/'config/settings.json')
    target.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix='.settings-',dir=target.parent)
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as stream:
            json.dump(settings,stream,ensure_ascii=False,indent=2)
            stream.flush();os.fsync(stream.fileno())
        os.replace(tmp,target)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)


class Translator:
    """Alle gültigen *.json-Kataloge neu erkennen; Englisch ist der Fallback."""
    def __init__(self,language='de',directory=None):
        self.directory=Path(directory or ROOT/'languages')
        self.language=language
        self.catalogs={}
        self.problems=[]
        self.reload()

    def reload(self):
        self.problems=[]
        catalogs={}
        try:paths=sorted(self.directory.glob('*.json'))
        except OSError:paths=[]
        for p in paths:
            try:
                raw=json.loads(p.read_text(encoding='utf-8'))
                if not isinstance(raw,dict) or not raw or not all(isinstance(k,str) and isinstance(v,str) for k,v in raw.items()):raise ValueError('Invalid catalog')
                catalogs[p.stem]=raw
            except (OSError,ValueError,UnicodeError) as exc:
                self.problems.append(f'HM103: {p.name}')
                logging.getLogger('monitor').warning('HM103: %s (%s)',p,type(exc).__name__)
        self.catalogs=catalogs
        if not catalogs:self.problems.append('HM103: languages/')
        if len(catalogs)==1:self.language=next(iter(catalogs))
        elif self.language not in catalogs:
            self.language='de' if 'de' in catalogs else ('en' if 'en' in catalogs else next(iter(catalogs),'en'))

    def __call__(self,key,**values):
        text=self.catalogs.get(self.language,{}).get(key,self.catalogs.get('en',{}).get(key,key))
        try:return text.format(**values)
        except (KeyError,ValueError,IndexError):return text
