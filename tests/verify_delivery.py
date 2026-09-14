from pathlib import Path
import hashlib,subprocess,tempfile,tarfile,zipfile
from monitor.constants import ROOT,VERSION
code="""
from monitor.app import Application,GLib
app=Application()
def done():
    assert app.window.snapshot is not None, 'Kein Scanergebnis'
    assert not app.window._busy
    app.window.close()
    return False
GLib.timeout_add(1800,done)
raise SystemExit(app.run([]))
"""
# Ein normaler echter Scan und geordnetes Beenden; niemals Passwortdialog öffnen.
r=subprocess.run(['python3','-c',code],cwd=ROOT,text=True,capture_output=True,timeout=8,check=True)
assert 'Traceback' not in r.stderr,r.stderr
print('Echter GTK-Start, Hintergrundscan und Beenden: OK')
with tempfile.TemporaryDirectory(dir=ROOT/'work',prefix='delivery-check-') as d:
    d=Path(d)
    for kind in ('source','compiled'):
        dest=d/kind;dest.mkdir()
        if kind=='source':
            with zipfile.ZipFile(ROOT/'dist'/f'pcMonitor-{VERSION}-quellcode.zip') as z:
                assert not any(n.endswith(('settings.json','.log','scan.json','.sh')) for n in z.namelist())
                z.extractall(dest)
        else:
            with tarfile.open(ROOT/'dist'/f'pcMonitor-{VERSION}-python3.12-kompiliert.tar.gz') as t:
                assert not any(n.endswith(('settings.json','.log','scan.json','.sh')) for n in t.getnames())
                t.extractall(dest,filter='data')
        package=dest/f'pcMonitor-{VERSION}';target=d/(kind+'-installed')
        subprocess.run(['python3',str(package/'install.py'),'--directory',str(target)],check=True,capture_output=True)
        r=subprocess.run(['python3','-m','monitor','--check'],cwd=target,text=True,capture_output=True,check=True)
        r=subprocess.run(['python3','-c',code],cwd=target,text=True,capture_output=True,check=True,timeout=8)
        assert 'Traceback' not in r.stderr,r.stderr
        print(kind+': Installation, Selbsttest und Hintergrundscan OK')
paths=sorted(p for p in (ROOT/'dist').iterdir() if p.suffix in ('.zip','.gz'))
(ROOT/'dist/SHA256SUMS').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.name+'\n' for p in paths))
print('Pakete ohne Benutzerdaten; Prüfsummen geschrieben.')
