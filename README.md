# pcMonitor 1.6.0

Lokaler pcMonitor für Linux Mint mit GTK 4. Links stehen von Linux erkannte Anschlüsse mit farbigen, nach Anschlussart gestalteten Symbolen; rechts erscheinen Systemübersicht oder Details zur Auswahl. Deutsch und Englisch sind standardmäßig enthalten. Spanisch, Französisch, Portugiesisch, Chinesisch (vereinfacht), Hindi, Arabisch, Russisch und Türkisch lassen sich mit passender HTML-Hilfe installieren.

## Voraussetzungen und Start

Python ab 3.10, PyGObject und GTK ab 4.8. Auf Linux Mint: `python3`, `python3-gi` und `gir1.2-gtk-4.0`. Optional liefert `pactl` aus `pulseaudio-utils` Audio-Steckerinformationen. Der Adminmodus benötigt `pkexec` und einen laufenden grafischen PolicyKit-Authentifizierungsagenten.

Im Programmordner:

```bash
python3 -m monitor
python3 -m monitor --help
python3 -m monitor --version
python3 -m monitor --check
python3 -m monitor --scan
python3 -m monitor --admin
```

`--scan` gibt eine einmalige lesende Bestandsaufnahme als JSON aus. `--admin --scan` nutzt den Administrator-Lesehelfer und meldet bei fehlender Freigabe einen Fehlerstatus. `--check` prüft die mitgelieferten Ressourcen. Exitcode 0 bedeutet Erfolg; 1 bedeutet eine fehlgeschlagene Prüfung beziehungsweise nicht verfügbare angeforderte Administratorfreigabe. Die Scan-Ausgabe kann Hardwarekennungen und Netzwerkadressen enthalten und sollte entsprechend behandelt werden.

## Bedienung

- Links: Anschlussgruppen, Suche und Schalter „Alle Anschlüsse“.
- Standardmäßig werden nur sicher als unbelegt erkannte Anschlüsse ausgeblendet. Unbekannte Zustände und Abfragefehler bleiben sichtbar.
- Ein Anschlussklick zeigt rechts Gerät, Zustand und verfügbare technische Daten. Die Übersichtstaste links oben wechselt zur Systemübersicht.
- Die Hardware wird alle drei Sekunden gelesen. Das Intervall lässt sich in den Einstellungen auf 2, 3, 5 oder 10 Sekunden setzen.
- Datei → Beenden; Bearbeiten → Einstellungen; Hilfe → Erhalten, Über und Info.
- Einstellungen und der Schalterzustand werden atomar in `config/settings.json` gespeichert. Fehler stehen in `logs/monitor.log`, mit Rotation auf drei ältere Dateien.

Die Oberfläche verwendet standardmäßig Cairo-Software-Rendering ohne OpenGL/Vulkan und benötigt keinen DRI3-Grafikzugriff. Sie übernimmt weiterhin Systemthema und Systemschrift. Die farbigen Anschlussbilder kennzeichnen Anschlussarten; Zustandssymbole und Texte unterscheiden Verbunden, Unbelegt, Unbekannt und Abfragefehler.

## Erkennung und Grenzen

USB-Hubports, DRM-Bildschirmanschlüsse, gerätegebundene Netzwerkschnittstellen, Audioports, SATA-Ports, erkannte Laufwerke, PCIe-Slots, Type-C/Thunderbolt und serielle Schnittstellen werden soweit verfügbar aus Linux gelesen. Das Programm verändert keine Hardwareeinstellungen, montiert keine Laufwerke und installiert keine Treiber.

Eine vollständige physische Buchsenliste ist nicht auf jedem Mainboard verfügbar: USB-2/USB-3-Begleiter können dieselbe Buchse darstellen, interne Anschlüsse sind enthalten, Adapter und Laufwerke können in mehreren technischen Ansichten erscheinen. In virtuellen Maschinen sind nur Gastgeräte und durchgereichte Hardware sichtbar. „Verbunden“ bei Netzwerk bedeutet Linksignal, nicht Internetzugang. Serielle und Audioanschlüsse können ihre Belegung häufig nicht melden; sie bleiben dann „Status unbekannt“. Ein Temperaturwert von null ist ein gültiger Messwert.

## Administratorzugriff

Nur der lesende Scanner läuft nach PolicyKit-Freigabe mit erhöhten Rechten. Fenster, Audiozugriff und Konfiguration bleiben in der normalen Benutzersitzung. `admin_worker.py` akzeptiert über private Prozess-Pipes ausschließlich `scan`, `refresh` und `quit`, keine beliebigen Shellbefehle oder Pfade. Der Helfer endet beim Schließen der Verbindung. Bei abgebrochener Freigabe zeigt die Oberfläche HM203 und verwendet normale Erkennung; ein erneuter Versuch erfolgt erst nach Neustart des Adminmodus. Kein Passwort wird gespeichert.

Die Programmdateien des Adminhelfers müssen aus einer vertrauenswürdigen Quelle stammen. Der Adminmodus ist optional; die normale Anzeige benötigt keine Administratorrechte.

## Dateien, Sprachen und Hilfe

`monitor/` enthält den Quellcode, `resources/` die SVG-/PNG-Symbole, `config/` Einstellungen, `logs/` Fehlerprotokolle, `languages/` Sprachdateien, `help/` HTML-Hilfen, `tests/` Tests, `work/` lokale Zwischenstände und `dist/` bereinigte Auslieferungen.

Sprachformat: UTF-8-JSON-Objekt mit Textschlüsseln und Textwerten. `language.name` gibt den sichtbaren Sprachnamen an. Eine Datei `languages/fr.json` wird ohne Programmänderung beim nächsten Öffnen der Einstellungen erkannt. Fehlende Schlüssel fallen auf Englisch zurück. Genau eine gültige Sprache wird automatisch verwendet, ohne Sprachauswahl. Zehn Sprachen werden unterstützt und getestet. Hilfe-Dateien `help/<code>.html` werden unabhängig erkannt; die Hilfe öffnet ausschließlich in der eingestellten Programmsprache, ohne zusätzlichen Auswahldialog. Ungültige Dateien erzeugen einen Fehlerhinweis.

## Tests und Auslieferung

```bash
python3 -m unittest discover -s tests
python3 build.py
```

Tests verwenden temporäre Kernel-Fixtures und Einstellungen. GUI-Tests benötigen eine grafische Sitzung. Der Adminhelfer wird ohne tatsächliche Privilegien auf sein Leseprotokoll geprüft; die lokale PolicyKit-Passwortabfrage wird nicht automatisiert.

`build.py` erstellt unter `dist/` ein vollständiges Quellcode-ZIP und eine installierbare CPython-Bytecode-Ausgabe als TAR.GZ. Beide enthalten Standardsprachen und Hilfe, aber keine Benutzereinstellungen, Logs, Scanprotokolle oder privaten Startdateien. Die kompilierte Ausgabe benötigt dieselbe Python-Haupt-/Nebenversion wie beim Build sowie GTK/PyGObject; sie ist kein selbstständiges natives Programm. Nach dem Entpacken installiert `python3 install.py --directory /absoluter/zielordner` in einen neuen oder leeren Ordner. Bestehende Dateien werden nicht überschrieben.

## Lizenz und Autor

GNU GPL Version 3, ausschließlich (`GPL-3.0-only`), vollständiger Text in LICENSE. Autor: Josef Lehner. Website: https://dogtruck.eu. Python, GTK, PyGObject, Linux und PulseAudio/PipeWire bleiben Komponenten ihrer jeweiligen Entwickler unter ihren eigenen Lizenzen.

## Hardwareinventar ab 1.5.0

Die feste Bereichsauswahl enthält CPU, RAM einschließlich einzelner bestückter Module, Mainboard, BIOS/UEFI, Grafikkarten, NVMe/SSD/HDD, Netzwerk, USB, Monitore, PCIe-Geräte, Temperaturen und Seriennummern. Bunte 3D-Icons kennzeichnen die Gruppen. Links steht genau ein Eintrag mit 3D-Icon pro Hardwarebereich. Die Suche berücksichtigt übersetzte Gruppennamen und filtert die Geräte rechts. Zusätzliche Anschlussansichten bleiben verfügbar.

CPU-Daten stammen aus procfs und `lscpu`, Hersteller-/Modellnamen von PCI-Geräten aus `lspci`. Der Adminhelfer ergänzt mit `dmidecode` RAM-Module und liest mit `smartctl` SMART-Zustand, Rohattribute, Betriebsstunden und Temperatur. Optionale Werkzeuge unter Linux Mint:

```bash
sudo apt install pciutils dmidecode smartmontools
```

Nicht verfügbare Felder werden ausdrücklich gekennzeichnet. Dedizierter VRAM wird aus Treiberdaten gelesen; bei NVIDIA zusätzlich über ein bereits installiertes `nvidia-smi`. Gemeinsam genutzter RAM wird nicht als dedizierter VRAM ausgegeben. Seriennummern werden nur angezeigt, wenn Firmware oder Gerät sie liefern. Die Seriennummernübersicht enthält zusätzlich Hardware-UUID und Gehäusenummer. RAM-Gesamtgröße bezeichnet den vom Betriebssystem nutzbaren Speicher; Modulgrößen stammen aus SMBIOS und können in Summe davon abweichen.

Monitordaten stammen aus einem auf Header und Prüfsumme geprüften EDID-Basisblock. Der bevorzugte EDID-Bildmodus ist **nicht** die aktuell eingestellte Auflösung. Die Rohdaten bleiben einsehbar. EDID kann durch Adapter oder virtuelle Geräte ersetzt werden.

SMART-Abfragen starten keine Tests und ändern keine Einstellungen. `--nocheck=standby` überspringt unterstützte schlafende Laufwerke; die Unterstützung hängt vom Gerät/Controller ab. Externe Abfragen haben je höchstens zwei Sekunden und gemeinsam sechs Sekunden Zeit pro Scan. Werkzeugabfragen werden 60 Sekunden, RAM-Moduldaten fünf Minuten und NVIDIA-Werte 30 Sekunden zwischengespeichert. Nach Ablauf des Budgets werden weitere Werte im nächsten Scan angefragt. HM204 bezeichnet eine fehlgeschlagene ergänzende Hardwareabfrage; die grundlegenden Anschlussdaten bleiben erhalten.

Technische Referenzen: [smartctl-Handbuch](https://github.com/smartmontools/smartmontools/blob/main/src/smartctl.8.in), [Linux-EDID-Dokumentation](https://www.kernel.org/doc/html/latest/admin-guide/edid.html). Die Erkennung ist ausschließlich lesend.

## Drucken und CSV (1.5.0)

Oberhalb der rechten Datenseite zwischen „Ausgewählter Bereich“ und „Alle Hardwaredaten“ wählen und „Drucken …“ oder „CSV speichern …“ anklicken. „Ausgewählter Bereich“ enthält alle Geräte dieses Bereichs; „Alle Hardwaredaten“ enthält den vollständigen aktuellen Scan. Beide Ausgaben enthalten auch durch Suche oder Leerschalter ausgeblendete Geräte sowie Erkennungshinweise. Die Ausgabe wird beim Anklicken eingefroren.

CSV: UTF-8 mit BOM, Semikolon, Spalten Bereich/Gerät/Zustand/Angabe/Wert; mehrzeilige Werte werden zitiert, potenzielle Tabellenformeln als Text neutralisiert. Größen werden in Bytes mit Einheit ausgegeben. Drucken öffnet den GTK-Druckdialog mit Druckerauswahl und mehrseitigem Bericht. Zusätzliche Druckabhängigkeiten auf Linux Mint: `python3-cairo` und `python3-gi-cairo`. Abbrechen erzeugt keinen Druckauftrag. HM301 bedeutet CSV-Schreibfehler (Ziel/Schreibrechte prüfen), HM302 Druckfehler (Drucker und Cairo-Pakete prüfen).

Datei enthält nur Beenden, Bearbeiten nur Einstellungen, ohne leere Menüeinträge. Die linke Spalte beginnt mit ihrer vom Inhalt benötigten Mindestbreite und bleibt bei größerem Fenster kompakt; der Trenner kann weiterhin verschoben werden.

## Bedienung ab 1.5.0

Die native Menüleiste enthält zusätzlich Hardware → Übersicht sowie alle Hardwarebereiche. Die linke Auswahl bleibt als zweite Zugriffsmöglichkeit erhalten. Unter Bearbeiten → Einstellungen lässt sich das Aktualisierungsintervall auf „Aus – nur manuell aktualisieren“ setzen. Beim Start wird einmal gelesen; danach nur per Aktualisieren. Eine bereits laufende Abfrage darf noch enden.

Erkennungshinweise stehen außerhalb der laufend erneuerten Ausgabe. Unveränderte Hinweise behalten ihren aufgeklappten Zustand. Fehlende Leserechte auf DMI-Kennungen sind keine Aktualisierungsfehler: Die Angabe bleibt nicht verfügbar und wird erst bei manueller Aktualisierung oder Neustart erneut versucht. Administratorzugriff kann die benötigten Rechte bereitstellen. Der Ausgaberahmen mit Schatten übernimmt die Farben des Systemthemas.

## Diagnosehinweise ab 1.5.0

Die Übersicht verweist auf Bereiche mit Diagnosehinweisen. Am Gerät wird unterschieden: HM401 fehlendes Hilfsprogramm (mit bekanntem Mint-Paket und Installationsbefehl), HM402 keine Treiberbindung, HM403 fehlende Leserechte, HM404 nicht bereitgestellte Daten, HM405 Abfrage prüfen trotz vorhandenem Werkzeug. Hinweise werden auch in CSV und Druck übernommen.

PCI-Treiberzuordnung wird bei Speicher-, Netzwerk-, Grafik-, Audio- und USB-Controllern geprüft, USB bei einzelnen Interfaces. Ein fehlender Eintrag bedeutet nicht automatisch ein fehlendes Paket: auch reservierte Geräte und Userspace-Treiber sind möglich. Ein vorhandener Treiber gilt auch ohne ladbares Modul als gebunden. Eine vollständige Treiber- oder Modulkompatibilitätsprüfung ist damit nicht verbunden. NVIDIA-Pakete werden nur über die passende Treiberverwaltung empfohlen, nicht mit einer geratenen Versionsnummer. Das Programm installiert keine Pakete und lädt keine Module automatisch.

## Zusätzliche Messwerte 1.5.0

NVIDIA über `nvidia-smi -q`, IP/Gateway über `ip -j`, Linkmodi über `ethtool`, WLAN über `iw`, Bluetooth über `bluetoothctl`/sysfs, NVMe über `nvme-cli`, Secure Boot über EFI/mokutil, TPM und SMT über sysfs. Lüfter und Spannungen direkt über hwmon, daher keine Pflichtabhängigkeit von lm-sensors oder tpm2-tools. Alle Werte erscheinen auch in CSV und Druck. Keine Systemänderungen.

Formatreferenzen: https://docs.nvidia.com/deploy/nvidia-smi/ und https://docs.kernel.org/hwmon/sysfs-interface.html


## Sprache und Hilfe installieren (1.6.0)

Unter Bearbeiten → Einstellungen lassen sich Sprachdatei und passende HTML-Hilfe gemeinsam installieren. Lokal die `<code>.json` auswählen; `<code>.html` muss daneben liegen oder als `help/<code>.html` neben dem Ordner `languages/` vorliegen. Beide Dateien werden sofort installiert. Danach die Sprache auswählen und speichern. Die Installation bleibt auch bei Abbrechen des Einstellungsdialogs erhalten.

Der Sprachserver ist auf [https://github.com/Franz-Dariwudel/pcMonitor](https://github.com/Franz-Dariwudel/pcMonitor) voreingestellt. Bei Bedarf einen anderen Repositorylink eintragen; ohne Branchangabe wird `main` verwendet. Andere Branches über einen `/tree/BRANCH`-Link oder die Raw-Adresse angeben. „Verfügbare Sprachen suchen“ liest `manifest.json`, „Installieren / aktualisieren“ prüft und installiert beide Dateien. Keine automatischen Hintergrundupdates und keine Internetpflicht.

`python3 build.py` erstellt zusätzlich `dist/pcMonitor-sprachpakete/` mit einem uploadfertigen `manifest.json`, `languages/` und `help/` für alle vorhandenen Sprach-/Hilfepaare. Diese drei Elemente in den Stammordner des öffentlichen GitHub-Repositorys hochladen. Keine Konfigurationen, Logs oder Caches hochladen. Das Programm führt keine GitHub-Anmeldung durch; private Repositorys werden nicht unterstützt. Das öffentliche Repository ist https://github.com/Franz-Dariwudel/pcMonitor.

Manifestformat (schematisch; SHA256 durch den tatsächlichen Hash ersetzen):

```json
{
  "version": 1,
  "languages": {
    "de": {"name": "Deutsch", "version": 1, "file": "languages/de.json", "sha256": "64 Hex-Zeichen"}
  },
  "help": {
    "de": {"version": 1, "file": "help/de.html", "sha256": "64 Hex-Zeichen"}
  }
}
```

Für jede angebotene Sprache wird gleichsprachige HTML-Hilfe benötigt. `language.name` und sämtliche JSON-Werte sind Texte. Codes de, en, es, fr, pt, zh, hi, ar, ru und tr sowie weitere übliche Sprachcodes sind möglich. Verfügbar sind alle zehn Sprachen de, en, es, fr, pt, zh, hi, ar, ru und tr. Die kompilierte Standardausgabe enthält de/en; der vollständige Quellcode und die Sprachpakete enthalten alle zehn. Für eine zusätzliche Sprache beide echten Übersetzungen und ihre SHA256-Einträge ergänzen. Die Sprache und Hilfe müssen nicht dieselbe Versionsnummer haben. Versionen werden angezeigt; ein erneutes Installieren ersetzt die lokale Fassung auch bei gleicher Versionsnummer.

Online-Dateien werden auf HTTPS, relative Dateipfade, Größe (je maximal 2 MiB), SHA256 und Inhalt geprüft. Die HTML-Hilfe darf keine Skripte, Formulare, externes CSS oder eingebettete Inhalte enthalten. Prüfsummen schützen vor Übertragungsfehlern, ersetzen jedoch keine unabhängige Signatur. Erst nach erfolgreicher Prüfung beider Dateien wird installiert; bei Schreibfehlern wird zurückgerollt. Die zwei Dateiumbenennungen sind bei Stromausfall nicht gemeinsam atomar. Bei fehlgeschlagener Rückrollung bleiben `.pack-backup-…` zur Wiederherstellung erhalten. HM501–HM505 sind in beiden HTML-Hilfen erklärt.

Der technische Python-Modulname `monitor` bleibt für bestehende Startaufrufe kompatibel; der sichtbare Programmname lautet pcMonitor.

## Sprachpakete vom 14. September 2026

Acht zusätzliche vollständige Kataloge mit je 293 Texten und übersetzter HTML-Hilfe. Die arabische Hilfe verwendet Rechts-nach-links-Leserichtung. Fachbegriffe, Dateipfade und Platzhalter bleiben technisch kompatibel. Verfügbare Sprachen über Einstellungen → Verfügbare Sprachen suchen laden; jede Installation enthält immer Sprache und Hilfe. Programmversion 1.6.0 bleibt kompatibel; es ist kein Programmupdate für die neuen Sprachen erforderlich.
