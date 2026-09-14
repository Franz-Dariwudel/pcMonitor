# SPDX-License-Identifier: GPL-3.0-only
"""Administrator-Lesehelfer; grafische Sitzung und Audio bleiben unprivilegiert."""
import json
import os
from pathlib import Path
import selectors
import time
import shutil
import subprocess
from .constants import ROOT
from .scanner import Scanner,Snapshot,Port


class AdminScanner:
    def __init__(self):
        self.normal=Scanner()
        self.process=None
        self.failed=False
        self.active=False
        self.closed=False
        self.refresh_pending=False

    def _connect(self):
        if not shutil.which('pkexec'):raise FileNotFoundError('pkexec')
        helper=ROOT/'admin_worker.py'
        if not helper.exists():helper=ROOT/'admin_worker.pyc'
        if not helper.exists():raise FileNotFoundError(str(helper))
        self.process=subprocess.Popen(['pkexec','--disable-internal-agent','/usr/bin/python3','-B',str(helper)],
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,bufsize=1)

    def scan(self):
        if self.closed:
            return Snapshot([],{},['HM203'],0)
        if self.failed:
            snapshot=self.normal.scan();snapshot.issues.append('HM203');snapshot.system['admin']=False
            return snapshot
        try:
            if self.process is None:self._connect()
            process=self.process
            process.stdin.write('refresh\n' if self.refresh_pending else 'scan\n');process.stdin.flush()
            self.refresh_pending=False
            with selectors.DefaultSelector() as selector:
                selector.register(process.stdout,selectors.EVENT_READ)
                deadline=time.monotonic()+(120 if not self.active else 10)
                while not selector.select(0.2):
                    if self.closed:return Snapshot([],{},[],time.time())
                    if time.monotonic()>=deadline:raise TimeoutError('Administrator authentication or scan')
            payload=json.loads(process.stdout.readline())
            if payload.get('error'):raise RuntimeError('HM203')
            snapshot=Snapshot([Port(**p) for p in payload['ports']],payload['system'],payload['issues'],payload['timestamp'])
            self.normal.issues=[]
            snapshot.ports=[p for p in snapshot.ports if p.group!='audio']+self.normal.audio()
            snapshot.issues.extend(self.normal.issues)
            from .diagnostics import Diagnostics
            snapshot.ports=Diagnostics(self.normal,privileged=True).annotate(snapshot.ports,snapshot.system,snapshot.issues)
            snapshot.system['admin']=True
            self.active=True
            return snapshot
        except (OSError,ValueError,RuntimeError,KeyError,TypeError) as exc:
            self.failed=True
            self._stop_helper()
            snapshot=self.normal.scan()
            snapshot.issues.append('HM203')
            snapshot.system['admin']=False
            return snapshot

    def _stop_helper(self):
        process=self.process
        if process:
            try:process.stdin.close()
            except (OSError,ValueError):pass
            # Nur den eigenen, noch nicht freigegebenen Authentifizierungsprozess abbrechen.
            if not self.active and process.poll() is None:
                try:process.terminate()
                except OSError:pass
            # Ein bereits freigegebener Helfer endet lesend bei EOF.
        self.process=None

    def reset_access_cache(self):
        self.normal.reset_access_cache()
        self.refresh_pending=True

    def close(self):
        self.closed=True
        self._stop_helper()
