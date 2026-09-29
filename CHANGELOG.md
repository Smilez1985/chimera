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
- 31 Tests für Erkennung und atomares Schreiben, jeder Regressionstest mit
  Gegenprobe. Laufen ohne Zielhardware, weil alle Systemabfragen über
  `CHIMERA_ROOT` gehen.
