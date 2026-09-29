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

### Bekannte Einschränkungen

- Es gibt noch **keinen Renderer**, der die Formen zeichnet. Die Ausgabe
  steht bereit, das Vokabular ist geprüft — dazwischen fehlt das Zeichnen.
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
