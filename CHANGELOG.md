# 1.6.0

- Anwendung, Hilfe, Exportnamen und Auslieferung heißen pcMonitor.
- Einstellungen: JSON-Sprachdateien installieren und GitHub-/HTTPS-Sprachkatalog durchsuchen.
- Online-Dateien vor Installation mit SHA256 prüfen; begrenzte Downloads, geprüfte relative Pfade und atomarer Austausch.
- Installierte Sprachen sofort ohne Neustart auswählen; englischen Rückfallkatalog erhalten.
- GitHub-Repository https://github.com/Franz-Dariwudel/pcMonitor als konfigurierbare Standardquelle; Deutsch und Englisch bleiben offline verfügbar.

# 1.5.0

- NVIDIA-Detailwerte einschließlich Treiber, VBIOS, Auslastung, Leistung, Takt und PCIe in Anzeige, CSV und Druck.
- IP-Adressen, Gateways, Ethernet-Linkmodi, WLAN, Bluetooth, NVMe-Controller und Gesundheitszähler.
- SMT, Secure Boot, TPM sowie Lüfter- und Spannungssensoren aus sysfs.
- Hilfsprogramme nur bei passender Hardware empfehlen; keine automatischen Systemänderungen.

# 1.4.0

- Diagnosehinweise für fehlende Hilfsprogramme mit konkreten Mint-Paketnamen.
- Fehlende Treiberbindung bei PCI-Endgeräten und USB-Schnittstellen von fehlenden Rechten und nicht bereitgestellten Daten unterschieden.
- Keine pauschale Installationsaufforderung bei unbekanntem Status; eingebaute Treiber werden nicht als fehlende Module gewertet.
- Hinweise in Bereichsansichten, Übersicht, CSV und Druck; deutsch/englisch.

# 1.3.4

- Beschriftung am Anschlussfilter: links „Belegte Anschlüsse anzeigen“, rechts „Alle Anschlüsse“.
- Filterfunktion und gespeicherte Einstellung unverändert.

# 1.3.3

- CSV-Speicherdialog bleibt bis zur Benutzerantwort referenziert; verhindert den GTK-Fehler „Der Ordnerinhalt konnte nicht angezeigt werden / Vorgang wurde abgebrochen“.
- Dialog startet im vorhandenen Projektordner. Wiederholtes Anklicken öffnet keinen zweiten Dialog.
- Speichern, Abbrechen und Schließen des Hauptfensters geben den Dialog kontrolliert frei.

# 1.3.2

- Hilfe öffnet direkt in der eingestellten Programmsprache; keine separate Sprachauswahl und kein Sprachwechsel bei fehlender Hilfe.
- Eigenes 3D-PC-Symbol für Programm und Desktop, zusätzlich in der zentralen Sammlung gespeichert.
- Info kennzeichnet nvidia-smi ohne erkannte NVIDIA-Grafikkarte als nicht benötigt.

# 1.3.1

- Leerfläche unter einzelnen Menüeinträgen behoben: Unsichtbare vertikale Menüscrollbalken erzwingen keine Mindesthöhe mehr.
- Native GTK-Menüs, Systemfarben und Scrollbarkeit langer Menüs bleiben erhalten.
- Regressionstest misst die tatsächlich geöffneten Menüs Datei und Bearbeiten.

# 1.3.0

- Native GTK-Menüleiste mit direkter Hardware-Bereichsauswahl; Menü-Stacks ohne übergroße Leerflächen.
- Automatische Aktualisierung abschaltbar; Erstscan und manuelles Aktualisieren bleiben verfügbar.
- Stabile Erkennungshinweise und zwischengespeicherte Leserechtsfehler für DMI-Kennungen.
- Themenabhängiger Rahmen mit räumlichem Effekt um die Datenausgabe.
- Entwicklungsreste und überholte Pakete aus dem Arbeitsordner entfernt.

# 1.2.0

- Kompakte Menüs ohne leere Zeilen: Datei nur Beenden, Bearbeiten nur Einstellungen.
- Linke Spalte mit inhaltsabhängiger Mindestbreite und vollständig lesbaren Bereichsnamen.
- CSV-Export und mehrseitiger Druck für den ausgewählten Bereich oder den gesamten Scan.
- CSV-Formelschutz, eingefrorene Ausgabe und dokumentierte Fehler HM301/HM302.

# 1.1.2

- Verbleibende eigene 2D-Grafiken durch 3D-Infowolke und 3D-Übersichtssymbol ersetzt.
- Alte SVG-Grafiken aus den aktiven Ressourcen entfernt; Grafikprüfung verwendet nur benötigte PNGs.
- Wiederverwendbare 3D-Grafiken zusätzlich in der persönlichen zentralen Sammlung katalogisiert.

# 1.1.1

- Links ein fester Eintrag mit 3D-Icon pro Hardwarebereich, ohne Aufklappen oder Unterpunkte.
- Rechts alle zugehörigen Geräte und Daten; Suche und Filter für leere Anschlüsse bleiben wirksam.
- Bereichsauswahl bleibt bei Aktualisierung und Abziehen eines Geräts erhalten.

# 1.1.0

- Hardwareinventar für CPU, RAM-Module, Mainboard, BIOS, GPU, Laufwerke, PCIe und Seriennummern.
- Optionaler lesender Zugriff auf SMBIOS, SMART und NVIDIA-Werte mit Zeitbegrenzung und Cache.
- EDID-Prüfung, Speicherdaten und fehlende Werte mit deutschen/englischen Beschriftungen.
- Farbige 3D-Auswahlicons und aufklappbare Hardwaregruppen.

# Änderungen

## 1.0.1 – 13.09.2026

- Cairo-Software-Rendering als Standard; OpenGL/Vulkan werden dafür vor dem GTK-Import deaktiviert. Kein DRI3-Zugriff für die Fensterdarstellung notwendig.
- Start über System-Python, damit die Systeminstallation von PyGObject gefunden wird.
- Frühe Startfehler, Interpreterpfad, Renderingmodus und Exitcode werden protokolliert.
- Startfehler erscheinen bei Desktopstarts nach Möglichkeit als sichtbarer Dialog.

## 1.0.0 – 13.09.2026

- GTK-4-Oberfläche mit linker Anschlussliste und rechter Detailansicht.
- Farbige SVG-Anschlusssymbole und eigenes SVG-/PNG-Programmsymbol.
- Lesende Erkennung über sysfs, procfs und optional pactl.
- Ausblendbare unbelegte Ports; unbekannte Zustände bleiben sichtbar.
- Automatische Aktualisierung im Hintergrund, Suche und Systemübersicht.
- Dynamisch erkannte Sprachen und Hilfen; Deutsch und Englisch enthalten.
- Projektlokale Einstellungen und Fehlerprotokolle.
- Optionaler Administrator-Lesehelfer mit PolicyKit-Freigabe.
- Quellcode- und kompilierte CPython-Auslieferung samt Installer.
