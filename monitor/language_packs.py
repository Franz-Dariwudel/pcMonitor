# SPDX-License-Identifier: GPL-3.0-only
"""Sprachpakete als reine UTF-8-Daten prüfen und atomar installieren.

Serverformat: manifest.json mit version=1 und languages={code:
{name, version, file, sha256}} und help={code: {version, file, sha256}}. file ist ein relativer JSON-Pfad.
Es werden keine Programme geladen. Netzwerkzugriffe gehören in einen Worker.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import uuid
from .constants import ROOT, DOWNLOAD_ROOT
from urllib.parse import urlsplit, urljoin
from urllib.request import build_opener, HTTPRedirectHandler, Request

LIMIT = 2 * 1024 * 1024
CODE = re.compile(r'[a-z]{2,3}(?:-[A-Za-z0-9]{2,8})*\Z')


class PackError(ValueError):
    """Fehlercode für verständliche, übersetzte Oberflächenmeldungen."""
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def catalog(data):
    try:
        if len(data) > LIMIT:
            raise ValueError()
        result = json.loads(data.decode('utf-8'))
        if (not isinstance(result, dict) or not result or
                not all(isinstance(k, str) and isinstance(v, str) for k, v in result.items()) or
                not result.get('language.name', '').strip()):
            raise ValueError()
        return result
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise PackError('HM501') from exc


def server_url(value):
    try:
        parts = urlsplit(value.strip())
    except ValueError as exc:
        raise PackError('HM502') from exc
    if (parts.scheme != 'https' or not parts.hostname or parts.username or
            parts.password or parts.query or parts.fragment):
        raise PackError('HM502')
    # GitHub-Repositorylinks verwenden main; andere Branches über /tree/<branch>
    # oder eine explizite raw.githubusercontent.com-Adresse angeben.
    if parts.hostname == 'github.com':
        segments = parts.path.strip('/').split('/')
        if len(segments) == 2 and all(segments):
            return f'https://raw.githubusercontent.com/{segments[0]}/{segments[1]}/main/'
        if len(segments) >= 4 and segments[2] == 'tree':
            return 'https://raw.githubusercontent.com/' + '/'.join(segments[:2] + segments[3:]) + '/'
        raise PackError('HM502')
    return value.strip().rstrip('/') + '/'


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise PackError('HM502')


def download(url):
    try:
        request = Request(url, headers={'User-Agent': 'pcMonitor-language-installer', 'Cache-Control': 'no-cache'})
        with build_opener(NoRedirect).open(request, timeout=10) as response:
            data = response.read(LIMIT + 1)
        if len(data) > LIMIT:
            raise ValueError('size')
        return data
    except PackError:
        raise
    except Exception as exc:
        raise PackError('HM502') from exc


def fetch_manifest(server):
    base = server_url(server)
    try:
        raw = json.loads(download(base + 'manifest.json?pcmonitor=' + uuid.uuid4().hex).decode('utf-8'))
        if not isinstance(raw, dict) or type(raw.get('version')) is not int or raw['version'] != 1:
            raise ValueError()
        entries = raw['languages']
        if not isinstance(entries, dict) or not entries or len(entries) > 200:
            raise ValueError()
        for code, entry in entries.items():
            if not CODE.fullmatch(code) or not isinstance(entry, dict):
                raise ValueError()
            path = entry['file']
            if (not isinstance(path, str) or not re.fullmatch(r'[A-Za-z0-9_./-]+\.json', path) or
                    path.startswith('/') or any(p in ('', '.', '..') for p in path.split('/'))):
                raise ValueError()
            if (not isinstance(entry['name'], str) or not entry['name'].strip() or
                    type(entry['version']) is not int or entry['version'] < 1 or
                    not isinstance(entry['sha256'], str) or
                    not re.fullmatch(r'[0-9a-fA-F]{64}', entry['sha256'])):
                raise ValueError()
            if not isinstance(raw.get('help'), dict): raise ValueError('help required')
            help_entry = raw['help'].get(code)
            if not isinstance(help_entry, dict): raise ValueError('matching help required')
            help_path = help_entry.get('file')
            if (not isinstance(help_path, str) or
                    not re.fullmatch(r'[A-Za-z0-9_./-]+\.html', help_path) or
                    help_path.startswith('/') or
                    any(part in ('', '.', '..') for part in help_path.split('/')) or
                    type(help_entry.get('version')) is not int or help_entry['version'] < 1 or
                    not isinstance(help_entry.get('sha256'), str) or
                    not re.fullmatch(r'[0-9a-fA-F]{64}', help_entry['sha256'])):
                raise ValueError('invalid help descriptor')
            entry['help'] = help_entry
        return entries
    except PackError:
        raise
    except (ValueError, KeyError, TypeError, UnicodeError, RecursionError) as exc:
        raise PackError('HM502') from exc


def help_document(data):
    """Nur passive HTML-Hilfe zulassen, ohne Skripte oder nachgeladene Inhalte."""
    from html.parser import HTMLParser
    class PassiveHTML(HTMLParser):
        tags = {'html','head','title','meta','style','body','main','section','article',
                'header','footer','nav','div','span','h1','h2','h3','h4','h5','h6','p',
                'br','hr','strong','b','em','i','u','small','code','pre','kbd','samp',
                'ul','ol','li','dl','dt','dd','table','thead','tbody','tfoot','tr','th',
                'td','caption','a','blockquote','details','summary','figure','figcaption'}
        def __init__(self):
            super().__init__(); self.html = False; self.body = False
        def handle_starttag(self, tag, attrs):
            if tag not in self.tags: raise ValueError('active HTML')
            self.html |= tag == 'html'; self.body |= tag == 'body'
            for key, value in attrs:
                if key.lower() not in {'lang','dir','charset','name','content','id','class',
                                       'style','href','title','colspan','rowspan','scope','open'}:
                    raise ValueError('HTML attribute')
                if key == 'href':
                    parsed = urlsplit(value or '')
                    if parsed.scheme not in ('', 'https', 'http') or parsed.netloc and not parsed.scheme:
                        raise ValueError('unsafe link')
                if key == 'name' and tag == 'meta' and value != 'viewport':
                    raise ValueError('metadata')
    try:
        if len(data) > LIMIT: raise ValueError('size')
        text = data.decode('utf-8')
        # CSS darf keine externen Ressourcen einbinden; Backslash-Escapes ebenfalls sperren.
        if re.search(r'url\s*\(|@import|expression\s*\(|\\', text, re.I):
            raise ValueError('external CSS')
        parser = PassiveHTML(); parser.feed(text); parser.close()
        if not parser.html or not parser.body: raise ValueError('HTML document required')
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise PackError('HM505') from exc


def install_pair(language_data, help_data, code, directory, help_directory):
    """Beide Dateien zuerst prüfen und vorbereiten; Fehler beim Austausch zurückrollen.

    Ein Stromausfall zwischen zwei Dateiumbenennungen ist kein atomarer Mehrdatei-
    Vorgang. Bei einem Rückrollfehler bleiben die .pack-backup-Dateien zur Rettung.
    """
    import shutil
    if not CODE.fullmatch(code): raise PackError('HM501')
    parsed = catalog(language_data)
    help_document(help_data)
    language_target = Path(directory) / (code + '.json')
    if code == 'en' and language_target.is_file():
        try:
            old = json.loads(language_target.read_text(encoding='utf-8'))
            if isinstance(old, dict) and not set(old).issubset(parsed): raise ValueError()
        except (OSError, ValueError, UnicodeError) as exc:
            raise PackError('HM501') from exc
    prepared = []
    replaced = []
    keep_backups = False
    try:
        for target, data in ((language_target, language_data),
                             (Path(help_directory)/(code+'.html'), help_data)):
            target.parent.mkdir(parents=True, exist_ok=True)
            fd, name = tempfile.mkstemp(prefix='.pack-new-', dir=target.parent)
            prepared.append([target, Path(name), None])
            with os.fdopen(fd, 'wb') as stream:
                stream.write(data); stream.flush(); os.fsync(stream.fileno())
            if target.exists():
                fd, backup = tempfile.mkstemp(prefix='.pack-backup-', dir=target.parent)
                os.close(fd)
                prepared[-1][2] = Path(backup)
                shutil.copy2(target, backup)
        for target, new, backup in prepared:
            os.replace(new, target)
            replaced.append((target, backup))
    except OSError as exc:
        for target, backup in reversed(replaced):
            try:
                if backup: os.replace(backup, target)
                else: target.unlink()
            except OSError:
                keep_backups = True
        raise PackError('HM504') from exc
    finally:
        for _, new, backup in prepared:
            for path in (new, None if keep_backups else backup):
                if path:
                    try: path.unlink(missing_ok=True)
                    except OSError: pass
    return code


def install_local_pair(path, directory, help_directory, expected_hashes=None):
    path = Path(path)
    if path.suffix != '.json': raise PackError('HM501')
    # Unterstützt Einzelpaare fr.json/fr.html und Paketordner languages/ + help/.
    sibling = path.with_suffix('.html')
    html = sibling if sibling.is_file() else path.parent.parent/'help'/(path.stem+'.html')
    try:
        with path.open('rb') as stream: data = stream.read(LIMIT + 1)
    except OSError as exc:
        raise PackError('HM501') from exc
    try:
        with html.open('rb') as stream: help_data = stream.read(LIMIT + 1)
    except OSError as exc:
        raise PackError('HM505') from exc
    if expected_hashes is not None:
        # Die tatsächlich von download/ gelesenen Bytes vor der Installation prüfen.
        for content, expected in zip((data, help_data), expected_hashes):
            if hashlib.sha256(content).hexdigest().lower() != expected.lower():
                raise PackError('HM503')
    return install_pair(data, help_data, path.stem, directory, help_directory)


def install_online_pair(server, code, directory, help_directory, download_directory=None):
    entries = fetch_manifest(server)
    if code not in entries: raise PackError('HM502')
    entry = entries[code]
    data = download(urljoin(server_url(server), entry['file']) + '?sha256=' + entry['sha256'])
    html = download(urljoin(server_url(server), entry['help']['file']) + '?sha256=' + entry['help']['sha256'])
    for content, descriptor in ((data, entry), (html, entry['help'])):
        if hashlib.sha256(content).hexdigest().lower() != descriptor['sha256'].lower():
            raise PackError('HM503')
    # Nur das aktuelle Downloadpaar nach erfolgreicher Installation entfernen.
    downloads=Path(download_directory) if download_directory is not None else DOWNLOAD_ROOT
    install_pair(data, html, code, downloads/'languages', downloads/'help')
    result = install_local_pair(downloads/'languages'/(code+'.json'), directory, help_directory,
                                (entry['sha256'], entry['help']['sha256']))
    for folder, suffix, digest, active in (
            ('languages', '.json', entry['sha256'], Path(directory)),
            ('help', '.html', entry['help']['sha256'], Path(help_directory))):
        source=downloads/folder/(code+suffix)
        # Bei identischem Ziel niemals installierte Dateien löschen.
        if source.resolve() == (active/(code+suffix)).resolve(): continue
        try:
            if source.is_symlink() or hashlib.sha256(source.read_bytes()).hexdigest().lower()!=digest.lower():
                raise OSError('Downloaded file changed before cleanup')
            source.unlink()
        except OSError as exc:
            raise PackError('HM506') from exc
    return result
