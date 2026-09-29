# Chimera — Installer

Entwurf. Noch nicht implementiert.

Der Installer ist kein Beiwerk, sondern trägt die Last der Plattformfrage.
Er ist der Ort, an dem die Radxa-/DietPi-Treiberfrage gelöst wird — nicht
eine Anleitung im Wiki, die der Nutzer abtippt.

---

## 1. Grundregeln

### I1 — Idempotent

Jeder Lauf führt zum gleichen Zielzustand, egal wie oft er läuft und in
welchem Zustand er beginnt. Jedes Modul prüft zuerst, ob sein Ziel schon
erreicht ist, und tut dann nichts.

Das ist keine Kosmetik: Der Installer ist gleichzeitig das
Update-Werkzeug. `git pull` plus Installerlauf muss immer genügen
(Architekturregel 10 in `DESIGN.md`).

### I2 — Ein Versionssprung bricht keine Installation

Was ein neues Release an bestehenden Installationen ändert, gehört in eine
Migrationsfunktion des Installers, nie in eine Release-Notiz „bitte neu
installieren".

### I3 — Systemdateien atomar schreiben

Nie direkt in die Zieldatei schreiben. Sidecar-Datei **neben** dem Ziel
anlegen (gleiches Dateisystem), dann per `mv` umbenennen.

**Und `mktemp` immer prüfen.** Zeigt `TMPDIR` ins Leere oder ist die
RAM-Disk voll, liefert `mktemp` einen leeren Pfad; `cat > ""` scheitert,
und ein nachfolgendes `install` bekommt eine leere Quelle — die Zieldatei
wird geleert. Bei `/boot/…`-Dateien bootet das Gerät danach nicht mehr.
Teuer gelernt, gilt hier unverändert.

### I4 — Nichts ungeprüft aufrufen

Ein Rückgabewert von 0 heißt nicht, dass das Programm existierte. Vor dem
Aufruf prüfen, nach dem Aufruf das Ergebnis prüfen — nicht nur den
Exitcode.

### I5 — Fremde Distributionspakete nie über `/` entpacken

Siehe §3.3. Dieser Punkt hat einen eigenen Abschnitt, weil er ein Gerät
unbrauchbar machen kann.

### I6 — Jeder Schritt einzeln aufrufbar

    chimera-install                 # alles
    chimera-install --only audio    # nur ein Modul
    chimera-install --dry-run       # nur berichten, nichts ändern
    chimera-install --check         # Zustand prüfen, Exitcode sprechend

`--dry-run` ist bei Kernelmodulen und Bootdateien keine Bequemlichkeit,
sondern Selbstschutz.

---

## 2. Modulaufbau

| # | Modul | Aufgabe |
|---|---|---|
| 10 | `preflight` | Board und Betriebssystem erkennen, Whisplay-Revision, Speicher, Platz |
| 20 | `packages` | Systempakete |
| 30 | `kernel-headers` | Header beschaffen — **der schwierige Teil** (§3) |
| 40 | `wm8960` | Codec-Modul prüfen, notfalls bauen (§4) |
| 50 | `whisplay-driver` | Whisplay-Soundkarte bauen und einhängen |
| 60 | `overlay` | Gerätebaum-Overlay, kollidierende abschalten (§5) |
| 70 | `alsa` | Audio-Konfiguration |
| 80 | `python` | Umgebung und Abhängigkeiten |
| 90 | `models` | sherpa-onnx-Modelle laden und prüfen |
| 95 | `config` | `.env` aus Vorlage, Ollama-Adresse erfragen |
| 98 | `service` | systemd-Unit |
| 99 | `migrate` | Übergänge von älteren Installationen |

Nummerierung mit Lücken, damit sich später etwas dazwischen schiebt, ohne
alles umzubenennen.

---

## 2a. Boarderkennung (Modul 10)

Chimera soll auf **Pi Zero 2 W und Radxa Zero 3W** laufen, und der
Installer soll das Board selbst erkennen. Ein Nutzer, der ein Flag setzen
muss, ist ein Nutzer, der es falsch setzen kann.

### Quellen, in dieser Reihenfolge

| Quelle | Aussage |
|---|---|
| `/proc/device-tree/model` | Klartextname des Boards |
| `/proc/device-tree/compatible` | Herstellerkennungen, zuverlässiger als der Name |
| `/etc/os-release` | Distribution — **entscheidet über die Bootmethode** |
| `uname -r` | Kernelversion, Vendor-Suffix |
| `/boot/config-<kver>` | vorhanden? (nötig für Header-Stufe 3) |

Die Trennung ist wichtig: **Board und Betriebssystem sind zwei
unabhängige Achsen.** Radxa Zero 3W mit Radxa-Debian und Radxa Zero 3W mit
DietPi sind derselbe Chip, aber zwei verschiedene Installationsfälle —
Overlay-Ablage und Bootkonfiguration unterscheiden sich (§5). Der
Installer ermittelt beides getrennt und entscheidet daraus.

    board = rpi_zero2w | radxa_zero3w | unknown
    os    = raspios | dietpi | radxa_debian | armbian | unknown
    boot  = config_txt | extlinux | uboot_script | unknown

### Die Schwäche im Hersteller-Verfahren

Der Whisplay-Installer erkennt den Radxa so:

    if [[ "$model" == *"Radxa"* ]]; then echo "radxa_zero3w"

Das trifft **jedes** Radxa-Board — auch eines, für das die
Gerätebaum-Beschreibung gar nicht passt. Chimera prüft stattdessen auf die
konkrete Kennung (`radxa,zero3w` bzw. das entsprechende
`compatible`-Feld) und meldet bei einem unbekannten Radxa ehrlich
`unknown`, statt einen falschen Pfad zu nehmen.

Ebenso beim Pi: nicht nur `model`, sondern auch `compatible` und das
Vorhandensein von `/boot/firmware/overlays` bzw. `/boot/overlays`.

### Architekturregel — Unbekanntes Board bricht ab, ohne zu raten

`unknown` ⇒ Abbruch mit Auskunft: was erkannt wurde, was erwartet wird,
welche Kombinationen bekannt sind. Ein Erratungsversuch, der das falsche
Overlay in die Bootkonfiguration schreibt, kostet im schlimmsten Fall den
Ausbau der SD-Karte.

`--force-board <name>` existiert für Entwicklung und für neue Boards, ist
aber nie der Vorschlag im Fehlertext.

### Whisplay-Revision

Der HAT hat ein EEPROM, das sich auslesen lässt:

    /proc/device-tree/hat/vendor      → "PiSugar"
    /proc/device-tree/hat/product_id  → "0x0001"

Damit ist die Platine erkennbar, ohne draufzuschauen. Ob sich daraus auch
**V1 gegen V2** unterscheiden lässt, ist noch offen — das gehört zu den
ersten Dingen, die Modul 10 auf echter Hardware beantworten muss. Bis
dahin bleibt die Warnung bestehen: V1 kann sich beim Tastendruck selbst
abschalten.

### Boardprofile

Alles Boardabhängige steht in **einer Tabelle**, nicht verstreut in
`if`-Zweigen: Header-Stufe, SPI-Bus und -Takt, Overlay-Quelle,
Overlay-Ziel, kollidierende Overlays, Bootmethode, ALSA-Vorlage.

Ein neues Board ist dann ein Tabelleneintrag. Das ist derselbe Gedanke wie
bei der Anbieter-Registry (Architekturregel 5a in `DESIGN.md`) und aus dem
gleichen Grund: Fallunterscheidungen, die über viele Funktionen verteilt
sind, driften auseinander.

### Warum das die Portierung billig macht

Die Reihenfolge — erst Pi fertigstellen, dann Radxa — funktioniert nur,
wenn boardabhängige Entscheidungen von Anfang an **an einer Stelle**
stehen. Sonst bedeutet „portieren" ein Durchsuchen aller Module.

Konkret heißt das: Modul 10 und die Profiltabelle entstehen in Phase 8a/8b
**mit beiden Boards im Blick**, auch wenn zunächst nur der Pi-Eintrag
ausgefüllt wird. Der Radxa-Eintrag bleibt vorhanden und meldet „noch nicht
unterstützt" — nicht als Platzhalter im Code, sondern als bewusster
Zustand.

Das lässt sich **ohne Hardware testen**: erfundene
`/proc/device-tree/model`- und `os-release`-Inhalte in ein temporäres
Wurzelverzeichnis legen und prüfen, dass die Erkennung das richtige Profil
wählt. Inklusive Gegenprobe.

---

## 3. Modul 30 — Kernel-Headers

Der Kern der Sache. Der Whisplay-Audiotreiber ist ein **Out-of-Tree-Modul**
(`obj-m := snd-soc-whisplay-soundcard.o`), gebaut gegen
`/lib/modules/$(uname -r)/build`. „Fehlt im Kernel" heißt also nicht
„unmöglich", sondern „Header beschaffen".

### 3.1 Stufen, von einfach nach aufwendig

    Stufe 0  /lib/modules/$(uname -r)/build existiert und ist brauchbar
             → fertig, nichts tun

    Stufe 1  Distributionspaket: linux-headers-$(uname -r)
             bzw. raspberrypi-kernel-headers  (Pi: hier endet es normalerweise)

    Stufe 2  Passendes Headers-Paket von außen (z. B. Armbian-Pool),
             in ein PRIVATES Verzeichnis entpacken           ← DietPi/Radxa

    Stufe 3  Header-Verzeichnis aufbereiten: fehlende generierte
             Eingaben erzeugen, Hostwerkzeuge bauen, gegen die
             Bootkonfiguration des Boards synchronisieren

Stufe 3 ist der Weg, den PiSugar für den Orange Pi Zero 3W geht. Für
DietPi auf dem Radxa ist er das Vorbild.

### 3.2 Was Stufe 3 konkret tut

Nachvollzogen aus dem Hersteller-Installer:

1. Headers-Paket herunterladen, **Prüfsumme verifizieren**
2. Mit `dpkg-deb -x` in ein temporäres Verzeichnis entpacken
   (**nicht** `dpkg -i`, siehe §3.3)
3. Das Header-Verzeichnis nach `/usr/src/linux-headers-<kver>-chimera`
   kopieren
4. Versionskennung in `include/config/kernel.release` und
   `include/generated/utsrelease.h` auf die laufende Version anpassen —
   sonst lädt das Modul später nicht
5. Fehlende ARM64-Generatoreingaben ergänzen und `cpucaps.h` sowie
   `sysreg-defs.h` erzeugen
6. `fixdep` und `modpost` selbst kompilieren (Headers-Pakete enthalten
   keine gebauten Hostwerkzeuge)
7. `/boot/config-<kver>` als `.config` übernehmen, dann `olddefconfig`
   und `syncconfig` — **damit die Modul-ABI exakt zum laufenden Kernel
   passt**
8. `/lib/modules/<kver>/build` als Symlink darauf setzen

Schritt 7 ist der, den man gern vergisst. Ohne ihn baut das Modul und
lädt trotzdem nicht.

Bemerkenswert im Vorbild: `modules_prepare` wird **absichtlich nicht**
aufgerufen — bei Vendor-Kerneln läuft es endlos durch BSP-Unterverzeichnisse.
Nur erzeugen, was externe Module brauchen.

### 3.3 I5 — Warum nicht über `/` entpacken

Der Hersteller schreibt dazu eine Warnung in den Code, und sie ist es wert,
hier zu stehen:

> Orange Pi OS nutzt merged-`/usr` (`/lib` ist ein Symlink auf
> `usr/lib`), das Armbian-Paket enthält ein echtes `lib/`-Verzeichnis.
> Beim Entpacken nach `/` würde der Symlink durch ein Verzeichnis ersetzt —
> und **dynamisch gelinkte Programme funktionieren danach nicht mehr.**

Das ist kein theoretisches Risiko, das ist ein zerstörtes System.
Deshalb: immer `dpkg-deb -x` in ein temporäres Verzeichnis, dann gezielt
das kopieren, was gebraucht wird.

### 3.4 Versionsbindung — und ihre Kehrseite

Der Hersteller bindet Stufe 2/3 an **genau eine** Kernelversion
(`6.6.98-sun60iw2`) und bricht bei jeder anderen ab. Das ist ehrlich, aber
unbequem: Ein Kernelupdate auf dem Zielgerät macht die Installation
unbaubar.

Chimeras Umgang damit:

- Eine **Tabelle** bekannter Kombinationen (Board, Kernelversion,
  Headers-Quelle, Prüfsumme) statt eines einzelnen fest verdrahteten Falls.
- Passt die laufende Version zu keinem Eintrag: **abbrechen mit klarer
  Auskunft** — welche Version läuft, welche bekannt sind, was zu tun ist.
  Kein Erraten, kein „probieren wir mal die nächstbeste".
- Modul 10 warnt, wenn ungeteilte Kernelupdates aktiviert sind, weil das
  die Installation beim nächsten `apt upgrade` zerlegen kann.

### 3.5 Vor dem Bauen erfassen

Modul 10 sammelt und protokolliert:

    uname -r
    ls -l /lib/modules/$(uname -r)/build
    modinfo snd-soc-wm8960
    ls /boot/config-$(uname -r)
    cat /etc/os-release
    cat /proc/device-tree/model
    free -m

Diese Werte gehören in eine Protokolldatei. Beim nächsten Problem ist das
die erste Frage, und niemand mag sie zweimal beantworten.

---

## 4. Modul 40 — WM8960-Codec

Das Whisplay-Modul **setzt den WM8960-Codec-Treiber voraus** und ergänzt
ihn nur. Fehlt er im Kernel, fehlt die Grundlage.

Ablauf:

1. `snd-soc-wm8960.ko*` unter `/lib/modules/$(uname -r)` suchen
2. Gefunden? `depmod -a`, dann `modprobe` **versuchen** — nicht bloß die
   Existenz prüfen. Ein vorhandenes Modul kann ABI-inkompatibel sein und
   lädt trotzdem nicht. (Genau diese Unterscheidung macht der
   Hersteller-Code, und sie ist der Grund, warum I4 als Regel dasteht.)
3. Nicht ladbar oder nicht vorhanden: aus Quelle bauen. Die passende
   `wm8960.c`/`.h` zur Kernel-Serie, Prüfsumme verifizieren, mit einem
   dreizeiligen Makefile gegen die Header bauen, nach
   `kernel/sound/soc/codecs/` installieren, `depmod -a`

Die Quelle ist GPL-2.0 (Linux). Wird sie mitgeliefert statt geladen,
gehört der Lizenzhinweis dazu und ein Vermerk in `THIRD_PARTY.md`.

---

## 5. Modul 60 — Overlay und Bootkonfiguration

Hier liegt der zweite DietPi-spezifische Stolperstein. Der
Hersteller-Installer erwartet Radxas eigene Struktur:

- Overlay nach `/boot/dtbo/` kompilieren (`dtc -I dts -O dtb -@`)
- Kollidierende Overlays abschalten: `rk3568-i2s3-m0.dtbo` und
  `wm8960-radxa-zero3.dtbo` (beide belegen denselben I2S-Pfad)
- `snd-soc-wm8960` und `snd-soc-whisplay-soundcard` in `/etc/modules`
- `u-boot-update` schreibt `/boot/extlinux/extlinux.conf`

**DietPi legt Bootkonfiguration anders ab.** Modul 60 muss daher die
Bootmethode erkennen (extlinux, u-boot-Skript, `config.txt`) und den
passenden Pfad wählen, statt `u-boot-update` vorauszusetzen.

Nach I3: Bootdateien über Sidecar und `mv`. Vorher eine Kopie mit
Zeitstempel ablegen — eine kaputte Bootkonfiguration auf einem Gerät ohne
Bildschirm bedeutet im besten Fall SD-Karte ausbauen.

**Im schlechteren Fall gar nichts.** Läuft das System vom eMMC (beim
Radxa der Normalfall), gibt es keinen Datenträger zum Ausbauen; die
Rettung führt über Maskrom-Modus und `rkdeveloptool` an einem PC. Modul 10
stellt deshalb fest, ob ein wechselbarer Rettungsweg existiert, und Modul
60 verlangt auf eMMC-Systemen eine ausdrückliche Bestätigung, bevor es
Bootdateien anfasst (`docs/HARDWARE.md` §3a).

Abschalten heißt **umbenennen**, nicht löschen (`.disabled`-Suffix), damit
die Deinstallation den Ausgangszustand wiederherstellen kann.

---

## 6. Deinstallation

Gleichwertig zum Aufbau, nicht nachträglich angeflanscht:

- Eigene Module entfernen, `depmod -a`
- `.disabled`-Overlays zurückbenennen
- Einträge aus `/etc/modules` entfernen
- Bootkonfiguration aus der Sicherung wiederherstellen
- Nutzerdaten (Mood-Bibliothek, Gedächtnis) **nur auf ausdrückliche
  Anforderung** löschen

---

## 7. Tests

Nach Architekturregel 9: Jeder Regressionstest braucht die Gegenprobe —
alten Zustand wiederherstellen und prüfen, ob der Test rot wird.

Ohne Zielhardware prüfbar:

- Idempotenz: zweiter Lauf ändert nichts (`--dry-run` liefert leere Liste)
- Board-Erkennung gegen erfundene `/proc/device-tree/model`-Inhalte
- Atomares Schreiben: Ziel bleibt unverändert, wenn der Schreibvorgang
  mittendrin abbricht
- `mktemp`-Fehlschlag: mit unbrauchbarem `TMPDIR` aufrufen und prüfen, dass
  **keine** Zieldatei geleert wird
- Headers-Tabelle: unbekannte Kernelversion ⇒ Abbruch mit Auskunft,
  kein Rateversuch
- Deinstallation stellt den Ausgangszustand her

Nur auf Hardware prüfbar: der eigentliche Modulbau, `modprobe`, Aufnahme
und Wiedergabe.

---

## 8. Reihenfolge

1. Gerüst: Modulaufbau, `--dry-run`, `--check`, Protokoll, atomares Schreiben
2. Modul 10 `preflight` — erfasst die Werte aus §3.5. Liefert sofort
   Nutzen: klärt die offenen Fragen zum Zielgerät
3. Module 20–70 für den Pi Zero 2 W (der einfache Fall, Stufe 1)
4. Module 80–99, damit Chimera startet
5. **Dann** Stufe 2/3 für Radxa unter DietPi — als eigenes Modul, gegen
   ein Gerät, das schon läuft

Punkt 5 zuletzt, nicht weil es unwichtig ist, sondern weil man es sonst
gegen eine Baustelle debuggt. Erst ein funktionierendes Chimera auf dem
Zero 2 W, dann der Boardwechsel.
