# Changelog

Alle nennenswerten Änderungen an diesem Projekt werden hier festgehalten.

Das Format folgt [Keep a Changelog](https://keepachangelog.com/de/1.1.0/),
die Versionierung [Semantic Versioning](https://semver.org/lang/de/) — mit
einer bewussten Abweichung: **ein Versionssprung bricht keine laufende
Installation.** Was ein Release an bestehenden Installationen ändert,
erledigt der Installer, nicht der Nutzer (siehe `docs/DESIGN.md` §10).

## [Unreleased]

### Hinzugefügt

- Installer-Modul 10 `preflight`: erkennt Board, Betriebssystem und
  Bootmethode getrennt voneinander, liest das Whisplay-EEPROM und berichtet
  die Bauvoraussetzungen (Kernel-Headers, `snd-soc-wm8960`,
  `/boot/config-*`, Speicher). Ändert nichts am System.
- Boardprofile für Raspberry Pi Zero 2 W und Radxa ZERO 3W, dazu eine
  Tabelle bekannter Kombinationen aus Board, Betriebssystem und
  Kernelversion. Eine unbekannte Kombination führt zum Abbruch mit
  Auskunft statt zu einem Rateversuch.
- `write_atomic`: schreibt Systemdateien über eine Sidecar-Datei neben dem
  Ziel und benennt sie atomar um. Prüft `mktemp` und lehnt leere Eingaben
  ab.
- `chimera-install` als Einstiegspunkt: ruft die Module der Nummer nach
  auf, kennt `--only`, `--list`, `--dry-run`, `--check` und `--log-dir`.
- Protokollierung: jeder Lauf schreibt eine Datei, **auch ein
  erfolgreicher**. Lässt sich kein Protokoll anlegen, wird das gemeldet.
- 38 Tests für Erkennung, atomares Schreiben, Sicherung und Protokoll,
  jeder Regressionstest mit Gegenprobe. Laufen ohne Zielhardware, weil
  alle Systemabfragen über `CHIMERA_ROOT` gehen.

- `--dry-run` und `--check` werden jetzt ausgewertet: `do_change` führt
  im Trockenlauf nichts aus, sondern kündigt an.
- Protokolle werden aufgeräumt; die jüngsten 20 bleiben
  (`CHIMERA_LOG_KEEP`).

- Mood-Schicht (`src/chimera/mood/`): Vokabular, Validator, Registry sowie
  Mischen und Variieren. Schema und Validator entstehen aus **einer**
  Tabelle, damit sie nicht auseinanderdriften.
- **Freie Zeichenformen**: elf Grundformen mit relativen Koordinaten,
  Ebene und Bewegung. Benannte Bausteine sind Vorschläge — ein Name, den
  der Renderer nicht kennt, wird übernommen und über eigene Formen
  dargestellt.
- Noisys 41 Moods als Startbestand, ohne die Audio-Kopplung
  (`tools/import-noisy-moods.py`).
- 68 Tests für die Mood-Schicht, mit Gegenproben.

- Bildausgabe (`src/chimera/display/panel.py`): Pillow-Bild → RGB565 →
  Panelspeicher über SPI, wie bei Noisy. Die Umrechnung läuft über `numpy`
  und ist damit rund 25-mal schneller als die bildpunktweise Fassung aus
  dem Herstellerbeispiel (2,5 ms gegen 62,9 ms je Bild). Ohne `numpy`
  greift der langsame Weg und meldet sich.
- `NullPanel` für Entwicklung und Messung ohne Gerät.
- 11 Tests für die Bildausgabe, inklusive Abgleich gegen die
  bildpunktweise Fassung.

- Renderer (`src/chimera/render/avatar.py`), übernommen aus Noisy (MIT)
  und angepasst: Bildgröße kommt vom Panel statt aus einer Konstanten,
  Ausgabe über ein beliebiges `Panel`, Zustand statt Orchestrator,
  Mood als Dict statt Nummer in einer globalen Registry.
- Freie Formen werden gezeichnet — elf Grundformen mit Ebene und Bewegung,
  `audio` folgt der eigenen Sprachausgabe.
- `tools/contact-sheet.py`: alle Moods und Mischungen nebeneinander.
- 16 Tests für den Renderer, mit Gegenprobe für die freien Formen.

- Mood-Übergänge (`src/chimera/mood/transition.py`): blenden über alle
  Felder, nicht nur über die Farbe. `fast_track` wechselt hart, damit ein
  Reflex nicht einblendet. Die Dauer ist eine Zeitangabe, der Fortschritt
  hängt an der Uhr.
- Farben sind ab jetzt garantiert Tupel — JSON liefert Listen, PIL nimmt
  nur Tupel, und der Fehler fiele sonst erst im Renderer auf.
- 21 Tests für Übergänge, mit gestellter Uhr und Gegenproben.

- `docs/HERKUNFT.md`: Bauteil-für-Bauteil-Analyse von openclawgotchi
  (Upstream und Fork) und OpenMinis — übernehmen, anpassen, weglassen.
- `docs/HYBRID-PLAN.md`: Aufbau und Reihenfolge in acht Stufen.

- `docs/DISPLAYS.md`: mehrere Anzeigen statt einer. Panel-Profile,
  Darstellungsarten (animiert bis 1-Bit-reduziert), Erkennung bei jedem
  Start. Der E-Paper-Treiber bleibt und kommt aus dem eigenen Fork.
- `docs/PROVIDER.md`: Anbieterschicht als Hybrid — Gotchis Werkzeugschleife
  mit OpenMinis' Anbietermuster. Modelle werden **je Aufgabe** zugeordnet,
  jede Aufgabe zeigt auf eine Gruppe mit Rückfall; kein Anbieter wird
  vorausgesetzt. Dazu MCP und der eigene Audio-Prozess.

- Anbieterschicht (`src/chimera/provider/`): Registry mit Aufgaben und
  Gruppen, Rückfall **über Anbietergrenzen hinweg**. Ollama mit
  Platzhalter-Erkennung und Netzsuche; Claude getrennt nach Abo und
  API-Schlüssel, jede Antwort trägt ihre Herkunft.
- Client-Kennung für den Abo-Weg wird zur Laufzeit ermittelt (PR #407),
  mit gepflegtem Rückfallwert, wenn die CLI fehlt.
- Ersteinrichtung sucht, schlägt vor und übernimmt — jede Zeile änderbar.
- 36 Tests für die Anbieterschicht, mit Gegenproben.

### Bekannte Einschränkungen

- Die Abo-Marke wird **nicht aufgefrischt**. Läuft sie ab, greift der
  Rückfall auf das nächste Ziel. Koordinator und Auffrischung fehlen noch.
- Die Werkzeugschleife ist noch nicht angeschlossen; die Anbieter können
  bisher nur antworten, nicht handeln.

- Noisys Reset-Überlagerung wurde entfernt; Chimera wird über Telegram
  und Sprache bedient.
- Die Messwerte zur Umrechnung stammen aus der Entwicklungsumgebung
  (aarch64), nicht vom Zielgerät.
- `MAX_SHAPES` (40) ist geschätzt, nicht gemessen.

- Ob der Renderer 15 Bilder je Sekunde hält, **während** gesprochen wird,
  ist auf echter Hardware ungeprüft. Ausweichwege stehen in
  `docs/DESIGN.md` §4.1.

- `backup_file` hat **noch keinen Aufrufer**. Es wird von Modul 60
  (Overlay und Bootkonfiguration) gebraucht, das noch nicht existiert.
  Getestet ist es bereits.
- Die Erkennung des Rettungswegs (zweiter Datenträger) ist heuristisch und
  auf echter Hardware noch nicht überprüft.
