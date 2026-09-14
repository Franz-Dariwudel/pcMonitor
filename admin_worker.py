# SPDX-License-Identifier: GPL-3.0-only
"""Privilegierter, ausschließlich lesender Helfer über private stdin/stdout-Pipes.

Es werden nur die festen Befehle scan, refresh und quit akzeptiert. Keine Shell,
keine beliebigen Pfade, keine Gerätesteuerung und keine Schreiboperationen.
Bei Ende der Benutzersitzung/geschlossener Pipe endet der Helfer automatisch.
"""
from dataclasses import asdict
import json
import sys
from monitor.scanner import Scanner

scanner=Scanner(audio_runner=lambda: [])
for line in sys.stdin:
    command=line.strip()
    if command=='quit':break
    if command not in ('scan','refresh'):
        print(json.dumps({'error':'HM203'}),flush=True)
        continue
    if command=='refresh':scanner.reset_access_cache()
    try:print(json.dumps(asdict(scanner.scan()),ensure_ascii=False),flush=True)
    except Exception as exc:print(json.dumps({'error':'HM203','type':type(exc).__name__}),flush=True)
