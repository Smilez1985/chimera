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
- Skills im `SKILL.md`-Format mit **Voraussetzungsprüfung**: Ein Skill,
  dessen Programme fehlen, wird gar nicht erst angeboten — genannt wird er
  trotzdem, mit Grund.
- Gedächtnis mit Rangordnung: dauerhafte Notizen sind für den Agenten nur
  lesbar, Tageslogs schreibt er selbst. Beim Einspeisen wird gesagt, dass
  es Hintergrund ist und nicht Auftrag.

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

302 Tests, alle grün: 64 Agent, 68 Mood, 46 Installer, 41 Anbieter,
35 Skills und Gedächtnis, 21 Übergänge, 16 Renderer, 11 Anzeige. Jeder Regressionstest hat eine Gegenprobe. Die
Anbieterschicht und die Agent-Schleife wurden zusätzlich gegen einen
echten Ollama-Server geprüft.

## [Unreleased]

### Hinzugefügt

**Bedienschnittstelle (H4)**
- **Sitzung und Kanal** (`chimera.agent.session`). Der Kern von Regel 5d:
  ein Agent, ein Verlauf, beliebig viele Türen. Eine Sperre serialisiert
  den Zugriff — der Agent ist nicht wiedereintrittsfähig, zwei
  gleichzeitige Läufe würden sich den Verlauf überschreiben. Ein Kanal
  beschreibt nur Ein- und Ausgabe und hält keinen eigenen Zustand
  (Regel 5i).
- **Telegram** (`chimera.bot.telegram`), ohne Fremdbibliothek — die
  Bot-API ist HTTPS mit JSON, das kann die Standardbibliothek. Auf 512 MB
  ist jede vermiedene Abhängigkeit eine gesparte. Positivliste erlaubter
  Absender ist Pflicht (Regel 5j): Ohne Liste startet der Bot nicht.
- **Der Zusammenbau** (`chimera.app`, `python3 -m chimera`). Den gab es
  vorher nicht — der Agent wurde nirgends instanziiert. Setzt nichts
  voraus: ohne Anbieter, ohne Panel, ohne Skills läuft es und sagt, was
  fehlt.

**Anzeige**
- **Der Renderer wird jetzt angeschlossen und gestartet.** Vorher setzte
  das Gesicht Ausdrücke auf einen Zustand, den niemand las — ein offenes
  Ende nach Regel 10h. `start_display()`/`stop_display()` führen ihn als
  Faden; das Panel wird durchgereicht statt weggeworfen (Regel 7b).
- **Die Bildrate gehört zum Panel** (Regel 7a). Ein LCD will 15 Bilder je
  Sekunde, E-Ink eines alle paar Sekunden; bei `fps = 0` zeichnet der
  Renderer nur auf Anstoß. Damit trägt derselbe Renderer beide
  Anzeigearten, ohne Sonderweg — ein neues Panel setzt eine Zahl.
- `tools/check-globals.py` — findet Namen, die eine Funktion als global
  liest, die es aber nicht gibt. Statisch, ohne Ausführung.

### Geändert

- **Unbekannte Boards brechen den Installer nicht mehr ab** (Regel 10k).
  Unbekannt heißt ungetestet, nicht unvereinbar: Wer Chimera auf einem
  Pi 4 versuchen will, darf das nach einer ehrlichen Warnung und einer
  bewussten Bestätigung. Was weiterhin **nicht** passiert, ist ein
  geratenes Overlay in der Bootkonfiguration — dieser eine Schritt kostet
  bei einem Gerät ohne Bildschirm den Ausbau der SD-Karte. Ohne Profil
  laufen die boardunabhängigen Module, die bootnahen melden sich ab.
  Exitcode 1 heißt jetzt „kein Profil, läuft weiter", 2 „niemand hat
  zugestimmt"; nicht-interaktiv braucht es `CHIMERA_ASSUME_YES=1`.
- Die CPU-Temperatur wird über eine Instanzeigenschaft gelesen, nicht über
  eine Modulkonstante — auf dem Radxa heißt die Zone anders als auf dem Pi
  (Regel 10c).
- **§13 verschärft und als Regel 13a gefasst:** Vor jedem Push läuft eine
  Prüfung auf Geheimnisse und Personenbezug, und sie belegt vorher, dass
  sie überhaupt etwas finden kann. Hinzugekommen in der Liste des
  Unerwünschten: private IP-Adressen, MAC-Adressen, Heimnetz-Hostnamen,
  private Mailadressen. Das Prüfwerkzeug selbst bleibt außerhalb des
  Repos — es nennt die Muster und damit die Form der geschützten Werte.

### Behoben

- **`NoisyRenderer.run()` stürzte in der zweiten Zeile ab.** Es las
  `TARGET_FPS` und `FRAME_TIME` als Modulglobale; die gab es nie, nur als
  Attribute. Unentdeckt, weil die Tests `render()` und `show()` aufriefen,
  nie `run()`.
- **`run()` hätte auch ohne diesen Fehler kein Bild ausgegeben** — es rief
  `render()`, das ein Bild zurückgibt, ohne es an das Panel zu schicken.
  Zwei Fehler auf demselben Weg, beide hinter demselben nie betretenen
  Zweig.
- **Die Temperaturkopplung war dauerhaft wirkungslos, und zwar lautlos.**
  `read_temperature()` las eine Konstante, die es nicht gab; der
  `NameError` fiel in ein `except Exception` und wurde zu `45,0 °C`. Die
  Müdigkeit des Avatars bei Hitze hat nie funktioniert. Genau die
  Fehlerklasse aus Regel 8a, gefunden mit dem neuen Werkzeug.
- **`app.py` öffnete ein Panel und warf es weg.** Auf echter Hardware wäre
  der SPI-Bus belegt und unbenutzt gewesen, während sich der Renderer ein
  eigenes Platzhalter-Panel baute.
- **Ein Fehler beim Anzeigen des Zustands verschwand in einer
  Debug-Zeile.** `Chimera.face` war ein namenloses `object`, die Methode
  wurde vermutet.
- `Registry.load()` konnte die mitgelieferte Mood-Bibliothek nie lesen —
  zwei unabhängig entstandene Dateiformate. Der Test daneben las die Datei
  selbst und rief `add()` auf, umging also genau die Funktion, um die es
  ging.
- `Channel.trim()` überschritt die Obergrenze, die es zusagt, um die Länge
  seines eigenen Abbruchzeichens.

### Geprüft

431 Tests, alle grün: 361 Python, 70 Installer. Neu darunter 27 für die
Gesichtskette (`test_display_wiring.py`) und 24 für Regel 10k. Jeder
Regressionstest hat eine Gegenprobe, und die Gegenproben wurden gegen den
jeweils alten Code **verifiziert** — jeder der sechs Befunde färbt den
Test rot, wenn man ihn wiederherstellt.

Die Prüfung des H4-Stands gegen die Blaupause steht in
`docs/PRUEFUNG-H4.md`.

### Bekannte Einschränkungen

- **Nichts davon lief auf der Zielhardware.** Insbesondere ist die
  Bildrate von 15 auf einem Pi Zero 2 W nicht gemessen, sondern von Noisy
  übernommen.
- Der Renderer läuft als Faden im Hauptprozess (Regel 7a). Dass die
  globale Sperre dabei nicht stört, ist begründet, aber auf dem Zero 2 W
  nicht gemessen.
