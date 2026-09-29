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

### Bekannte Einschränkungen

- `backup_file` hat **noch keinen Aufrufer**. Es wird von Modul 60
  (Overlay und Bootkonfiguration) gebraucht, das noch nicht existiert.
  Getestet ist es bereits.
- Die Erkennung des Rettungswegs (zweiter Datenträger) ist heuristisch und
  auf echter Hardware noch nicht überprüft.
