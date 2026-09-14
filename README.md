# pcMonitor 1.7.4

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

## DEB-Paket für Linux Mint

`pcmonitor_1.7.4_all.deb` installieren (im Downloadordner):

```bash
sudo apt install ./pcmonitor_1.7.4_all.deb
```

Das Paket legt für vorhandene Benutzer mit eingerichteter Desktopfläche zwei
Verknüpfungen an: **pcMonitor** (normal) und **pcMonitor (Admin)** (lesender
Adminhelfer mit Passwortabfrage). Beide stehen auch im Anwendungsmenü. Falls
Linux Mint beim ersten Öffnen eine Vertrauensbestätigung verlangt, den Starter
als vertrauenswürdig bestätigen. Vorhandene gleichnamige fremde Starter werden
nicht überschrieben; eine Kollision wird bei der Installation gemeldet.

Programmdateien liegen unter `/usr/lib/pcmonitor`, der Befehl heißt `pcmonitor`.
Fenster und Downloads bleiben auch beim Admin-Starter beim angemeldeten
Benutzer. Schreibbare Daten liegen unter `~/.local/share/pcMonitor/`: `config/`,
`logs/`, `cache/`, zusätzliche `languages/` und `help/`. Benutzerpakete haben
Vorrang vor mitgelieferten Dateien derselben Sprache. Downloads werden weiterhin
unter `~/Downloads/languages/` und `~/Downloads/help/` geprüft und nach einer
erfolgreichen Sprachinstallation gelöscht.

Deinstallation:

```bash
sudo apt remove pcmonitor
```

Die Paketverwaltung entfernt Programmdateien, Menüeinträge und Icons. Das
Installationsjournal unter `/var/lib/pcmonitor/` ermöglicht das Entfernen der
angelegten Desktop-Verknüpfungen und wird ebenfalls gelöscht. Bei einem Update
bleiben die Verknüpfungen erhalten. Erst während der Nutzung angelegte persönliche
Einstellungen, Protokolle und Sprachpakete bleiben erhalten; die DEB-Installation
legt selbst keine solchen Benutzerdateien an. Fremde Desktopdateien bleiben
unberührt. Entfernte oder ersetzte Benutzerkonten und Zugriffsfehler werden gemeldet.

DEB aus dem vollständigen Quellcodepaket selbst bauen:

```bash
python3 build.py
python3 build_deb.py
```

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

Fehlende Angaben und ihre Ursachen stehen direkt beim Gerät in roter Schrift, ohne separate Diagnoseübersicht. Intern wird unterschieden: HM401 fehlendes Hilfsprogramm (mit bekanntem Mint-Paket und Installationsbefehl), HM402 keine Treiberbindung, HM403 fehlende Leserechte, HM404 nicht bereitgestellte Daten, HM405 Abfrage prüfen trotz vorhandenem Werkzeug. Hinweise werden auch in CSV und Druck übernommen.

PCI-Treiberzuordnung wird bei Speicher-, Netzwerk-, Grafik-, Audio- und USB-Controllern geprüft, USB bei einzelnen Interfaces. Ein fehlender Eintrag bedeutet nicht automatisch ein fehlendes Paket: auch reservierte Geräte und Userspace-Treiber sind möglich. Ein vorhandener Treiber gilt auch ohne ladbares Modul als gebunden. Eine vollständige Treiber- oder Modulkompatibilitätsprüfung ist damit nicht verbunden. NVIDIA-Pakete werden nur über die passende Treiberverwaltung empfohlen, nicht mit einer geratenen Versionsnummer. Das Programm installiert keine Pakete und lädt keine Module automatisch.

## Zusätzliche Messwerte 1.5.0

NVIDIA über `nvidia-smi -q`, IP/Gateway über `ip -j`, Linkmodi über `ethtool`, WLAN über `iw`, Bluetooth über `bluetoothctl`/sysfs, NVMe über `nvme-cli`, Secure Boot über EFI/mokutil, TPM und SMT über sysfs. Lüfter und Spannungen direkt über hwmon, daher keine Pflichtabhängigkeit von lm-sensors oder tpm2-tools. Alle Werte erscheinen auch in CSV und Druck. Keine Systemänderungen.

Formatreferenzen: https://docs.nvidia.com/deploy/nvidia-smi/ und https://docs.kernel.org/hwmon/sysfs-interface.html


## Sprache und Hilfe installieren (1.6.0)

Unter Bearbeiten → Einstellungen zuerst „Verfügbare Sprachen suchen“, dann eine Sprache auswählen und installieren. Sprachdatei und passende HTML-Hilfe werden gemeinsam von GitHub geladen. Anschließend die gewünschte Oberflächensprache auswählen und speichern. Die Installation bleibt auch bei Abbrechen des Einstellungsdialogs erhalten. Es gibt keinen Button für lokale Sprachpakete mehr.

Die feste Sprachquelle ist [Franz-Dariwudel/pcMonitor](https://github.com/Franz-Dariwudel/pcMonitor). Es gibt kein Adressfeld mehr. „Verfügbare Sprachen suchen“ fordert bei jedem Klick einen frischen Katalog an; dadurch bleibt keine veraltete Liste mit nur zwei Sprachen im Cache. Dateien werden mit ihrer SHA256-Kennung abgerufen.

Sprache und HTML-Hilfe werden zuerst unter `~/Downloads/languages/` und `~/Downloads/help/` gespeichert und geprüft. Nach erfolgreicher Installation werden nur die heruntergeladenen Dateien des aktuellen Pakets gelöscht. Bei Installationsfehlern bleiben sie erhalten. HM506 bedeutet: Installation erfolgreich, aber Löschung nicht vollständig möglich; Downloads prüfen und bei Bedarf manuell löschen. Installierte Dateien bleiben erhalten.

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

Acht zusätzliche vollständige Kataloge mit vollständigen Anwendungstexten und übersetzter HTML-Hilfe. Die arabische Hilfe verwendet Rechts-nach-links-Leserichtung. Fachbegriffe, Dateipfade und Platzhalter bleiben technisch kompatibel. Verfügbare Sprachen über Einstellungen → Verfügbare Sprachen suchen laden; jede Installation enthält immer Sprache und Hilfe. Programmversion 1.6.0 bleibt kompatibel; es ist kein Programmupdate für die neuen Sprachen erforderlich.

Fehlende Hardwareangaben und nicht verfügbare Abfragen erscheinen direkt beim betroffenen Gerät in roter Schrift. Die separate Diagnoseübersicht entfällt.

Bei aktivem Administrator-Lesezugriff entfallen allgemeine Aufforderungen zum Adminstart. Fehlende Freigaben und weiterhin bestehende Zugriffsbeschränkungen werden passend zum tatsächlichen Status angezeigt.

## Erweiterte Linux-Inventur ab 1.7.2

Die fünf zusätzlichen Bereiche Linux-System, Partitionen und Dateisysteme,
lauschende Netzwerkdienste, Kernel und Speicherverwaltung sowie Sicherheit
erscheinen links und im Hardwaremenü. CSV und Druck enthalten alle dort erfassten
Felder. Bestehende Hardwarebereiche erhalten zusätzliche Detailwerte.

- Linux: Distribution, Kernel, Hostname, Architektur, Bootzeit in UTC, Laufzeit,
  Maschinen-ID und Boot-ID.
- CPU: Frequenzen/Governor je logischer CPU, Microcode, vollständige Flags, NUMA
  und Auslastung zwischen zwei Messungen. Bei ausgeschalteter Aktualisierung
  zweimal manuell aktualisieren. `cpuinfo_cur_freq` stammt vom Hardwaretreiber;
  `scaling_cur_freq` ist dessen gemeldeter Skalierungswert und kann abweichen.
- RAM: SMBIOS-Modulhersteller, Teilenummer, Seriennummer, Größe, Steckplatz, Typ,
  Geschwindigkeit und Spannungen. Fehlerkorrektur des Speicherarrays und
  EDAC-Laufzeitdaten werden getrennt angegeben. DDR5-On-Die-ECC und Modulbreite
  beweisen keine aktive systemweite ECC-Korrektur.
- Laufwerke: SMART-Gesamtstatus, ATA-Rohattribute, NVMe-Warnbits, Reserven,
  Verschleiß, Lese-/Schreibzähler, Betriebsstunden, Einschaltvorgänge, unsichere
  Abschaltungen, Medienfehler, Fehlerprotokollzähler und Namespace-IDs.
- Dateisysteme: Blockgerätebaum, Partitionen, Typ, Label, UUID/PARTUUID,
  Einhängepunkte, Größen in Bytes, Mount-Optionen und Discard/TRIM-Grenze.
  Die Verschlüsselungsanzeige bezieht sich auf den sichtbaren Blockgerätepfad;
  dateibasierte Verschlüsselung wird dadurch nicht ausgeschlossen. Nicht
  eingehängte Dateisysteme liefern häufig keine Belegungswerte. Lokale Mounts
  ohne Blockgerät erhalten Größenwerte über df; Netzwerk-Dateisysteme werden
  dafür nicht kontaktiert.
- Netzwerk: MTU, DNS-Suchdomains, Lease-Optionen und Konfigurationsmethode,
  Routingtabellen je Schnittstelle, Nachbartabelle, Fehler/Drops und andere
  Kernelzähler, permanente MAC und Wake-on-LAN. `ipv6.method=auto` allein beweist
  keinen DHCPv6-Lease. WLAN liest nur bekannte Access Points, ohne neuen Scan.
- Bluetooth: Adaptereigenschaften sowie pro Adapter zugeordnete gekoppelte und
  verbundene Geräte aus BlueZ. Kein Einschalten, Pairing oder Verbindungsaufbau.
- Dienste: lokale lauschende TCP-/UDP-Sockets, Adressen, Prozessname und PID.
  Das ist keine Prüfung ihrer Erreichbarkeit durch eine Firewall. Ohne Leserechte
  können Prozessangaben fehlen; es wird keine Adminfreigabe automatisch angefragt.
- Kernel: Swap/ZRAM, Module, Bootparameter, Taint-Bitmaske, Interrupts und IOMMU-
  Gerätegruppen. Keine gemeldeten Gruppen beweisen nicht, dass IOMMU deaktiviert ist.
- Sicherheit: Secure Boot, Lockdown und TPM2-Hersteller/Firmware, PCR-Bänke und
  Algorithmen über lesendes `tpm2_getcap`. Eigenschaften bleiben in ihrer
  technischen Originalnotation erhalten; TPM-Hersteller können numerisch sein.
- GPU und Sensoren: AMD-Auslastung, VRAM und aktuelle DPM-Takte über sysfs,
  vorhandene Treibersensoren sowie NVIDIA-Encoder/Decoder und unterstützte
  Zusatztemperaturen. Sensorbezeichnungen werden nicht als Pumpen/VRM/RAM-
  Sensoren erraten. Ohne bereitgestellte Werte bleibt die Angabe unbekannt.

Optionale Programme: `util-linux` (lsblk, lscpu), `iproute2` (ip, ss),
`network-manager` (nmcli), `ethtool`, `iw`, `dmidecode`, `smartmontools`,
`nvme-cli`, `mokutil`, `tpm2-tools`, BlueZ und gegebenenfalls der vorhandene
NVIDIA-Treiber mit nvidia-smi. pcMonitor installiert nichts und schreibt weder
Hardwareeinstellungen noch TPM-Daten. Fehlende Werkzeuge werden über HM401,
fehlende Daten weiterhin direkt in roter Schrift gekennzeichnet.

Die Abfragen sind zeitlich begrenzt. Ein Scan kann bei langsamen Werkzeugen
unvollständig sein; ein weiterer Scan nutzt gecachte Daten. CPU und Kernelwerte
stammen aus procfs/sysfs. Netzwerk- und Dateisystemabfragen werden bis zu fünf
Sekunden, statische Controllerdaten länger zwischengespeichert.

Quellen zur Interpretation: [Linux CPUFreq](https://www.kernel.org/doc/html/latest/admin-guide/pm/cpufreq.html),
[lsblk](https://man7.org/linux/man-pages/man8/lsblk.8.html),
[NetworkManager-Einstellungen](https://networkmanager.pages.freedesktop.org/NetworkManager/NetworkManager/nm-settings-nmcli.html).

## Bereichssymbole ab 1.7.2

Alle Bereiche besitzen passende 3D-Bilder. Bluetooth steht als eigener Bereich links und im Hardwaremenü; Suche, CSV und Druck verwenden dieselbe Zuordnung. Der serielle Bereich zeigt einen RS-232-Anschluss.
