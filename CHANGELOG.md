# Changelog

Alle nennenswerten Änderungen an diesem Projekt werden hier festgehalten.

Das Format folgt [Keep a Changelog](https://keepachangelog.com/de/1.1.0/),
die Versionierung [Semantic Versioning](https://semver.org/lang/de/) — mit
einer bewussten Abweichung: **ein Versionssprung bricht keine laufende
Installation.** Was ein Release an bestehenden Installationen ändert,
erledigt der Installer, nicht der Nutzer (siehe `docs/DESIGN.md` §10).

## [0.1.0] — unveröffentlicht

**Nicht getaggt.** Pre-Alpha bleibt ungetaggt, bis eine Fassung auf echter
Hardware gelaufen ist. Die Versionsnummer markiert den Stand, nicht ein
Release.

Erste Fassung mit lauffähigem Agenten. Alles hier Genannte ist verdrahtet
und geprüft; was noch offen ist, steht unter „Bekannte Einschränkungen"
oder in der Roadmap.

### Hinzugefügt

**Ausdruck**
- Mood-Vokabular, Validator und Registry (`chimera.mood`). Schema für das
  Sprachmodell und Prüfung entstehen aus **einer** Tabelle.
- Freie Zeichenformen: elf Grundformen mit relativen Koordinaten, Ebene
  und Bewegung. Benannte Bausteine sind Vorschläge — ein unbekannter Name
  wird übernommen und über eigene Formen dargestellt.
- Mischen und Variieren ohne Sprachmodell; Farben über den Farbton, damit
  Rot und Blau über Violett laufen statt über Grau.
- Übergänge über alle Felder, weich und hart. `fast_track` schaltet
  sofort, damit ein Schreck nicht einblendet.
- 41 Moods aus Noisy als Startbestand, ohne die Audio-Kopplung.

**Anzeige**
- Renderer aus Noisy übernommen und auflösungsrelativ gemacht: Bildgröße
  kommt vom Panel, Ausgabe über ein beliebiges `Panel`, Zustand statt
  Orchestrator.
- Bildausgabe in den Panelspeicher über SPI. Die Umrechnung nach RGB565
  läuft über `numpy` und ist rund 25-mal schneller als bildpunktweise
  (2,5 ms gegen 62,9 ms je Bild).

**Sprachmodelle**
- Anbieter-Registry mit Aufgaben und Gruppen. Der Rückfall geht **über
  Anbietergrenzen**: Ist Ollama weg, hilft ein zweites Ollama-Modell nicht.
- Ollama mit Platzhalter-Erkennung und Netzsuche; Claude getrennt nach Abo
  und API-Schlüssel, jede Antwort trägt ihre Herkunft.
- Client-Kennung für den Abo-Weg wird zur Laufzeit ermittelt (OpenMinis
  PR #407), mit Rückfallwert wenn die CLI fehlt.
- Ersteinrichtung sucht, schlägt vor und übernimmt — jede Zeile änderbar.

**Agent**
- Werkzeugschleife mit fünf Werkzeugen: Befehl ausführen, Datei lesen und
  schreiben, Verzeichnis auflisten, Gesicht setzen.
- Sicherheitsschranke aus openclawgotchi übernommen: keine Shell, keine
  Verkettung, keine Ersetzung, keine verschachtelten Interpreter, `sudo`
  gesperrt. Ergänzt um Netzsperre und Pfadschutz gegen `..` und Symlinks.
- Vorprüfung und JSON-Reparatur: abgebrochene Argumentangaben werden
  gerettet statt verworfen.
- Schleifenerkennung, die **vor** der Ausführung greift und dem Modell
  sagt, dass es feststeckt. Wechselnde Ergebnisse gelten nicht als Kreis.
- Kontextschwellen, gestaffelt nach Fenstergröße und geprüft gegen das
  Modell, das die Anfrage **tatsächlich bedient**.
- Der Agentzustand ist am Gesicht ablesbar: denkt, arbeitet, spricht,
  verwirrt.

**Installer**
- `chimera-install` mit Modulen, `--only`, `--list`, `--dry-run`, `--check`.
- Modul 10 `preflight`: erkennt Board, Betriebssystem und Bootmethode
  getrennt, liest das Whisplay-EEPROM, meldet die Bauvoraussetzungen.
- Boardprofile für Pi Zero 2 W und Radxa ZERO 3W samt Tabelle bekannter
  Kombinationen. Unbekanntes führt zum Abbruch mit Auskunft, nicht zum
  Rateversuch.
- Protokoll je Lauf, auch bei Erfolg; die jüngsten 20 bleiben erhalten.
- Atomares Schreiben mit geprüftem `mktemp`; leere Eingaben werden
  abgelehnt.

### Bekannte Einschränkungen

- **Keine Sprachein- oder -ausgabe.** Sprache, Wake-Word und
  Umgebungshören sind entworfen, aber nicht gebaut.
- **Kein Telegram.** Der Agent läuft nur programmgesteuert.
- **Die Abo-Marke wird nicht aufgefrischt.** Läuft sie ab, greift der
  Rückfall auf das nächste Ziel. Koordinator fehlt.
- **Werkzeugaufrufe werden aus dem Text gelesen** (`TOOL: name {...}`),
  nicht über die Werkzeug-Schnittstelle der Anbieter. Funktioniert mit
  jedem Modell, ist aber nicht die saubere Lösung.
- **`Action.OFFLOAD` wird erkannt, aber nicht ausgeführt** — verdichtet
  wird erst an der nächsten Schwelle.
- **`backup_file` im Installer hat keinen Aufrufer.** Modul 60, das es
  braucht, existiert noch nicht.
- **Nur ein Panel ist gebaut** (Whisplay). E-Paper und ST7789 sind
  entworfen (`docs/DISPLAYS.md`), nicht umgesetzt.
- **Nichts davon lief auf der Zielhardware.** Alle Messwerte stammen aus
  der Entwicklungsumgebung oder von einem Ollama-Server im Netz.

### Geprüft

267 Tests, alle grün (64 Agent, 68 Mood, 41 Anbieter, 21 Übergänge,
16 Renderer, 11 Anzeige, 46 Installer). Jeder Regressionstest hat eine Gegenprobe. Die
Anbieterschicht und die Agent-Schleife wurden zusätzlich gegen einen
echten Ollama-Server geprüft.

## [Unreleased]

Noch keine Änderungen seit 0.1.0.
