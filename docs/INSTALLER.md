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

**Das gilt auch fürs Anhängen.** Eine Zeile an eine Fremddatei hängen
(`>>`) sieht harmloser aus als ein Überschreiben, ist es aber nicht: Fällt
die Spannung mitten im Schreiben aus, bleibt die Datei halb geschrieben —
und in einer `config.txt` ist eine halbe Zeile so gut wie keine. Zeilen
werden deshalb ebenfalls über Sidecar und `mv` geschrieben: Inhalt lesen,
Zeile anfügen, in einem Zug ersetzen. `write_atomic` kann beides; das
Anhängen ist ein Sonderfall davon.

Neben den Rechten übernimmt das Verfahren auch **Besitzer und Gruppe** der
Zieldatei (`chown --reference`). Auf der FAT-Bootpartition ist das
bedeutungslos, auf einem ext4-System ohne `--reference` aber würde die
Datei nach jedem Installerlauf dem Aufrufer gehören.

### I4 — Nichts ungeprüft aufrufen

Ein Rückgabewert von 0 heißt nicht, dass das Programm existierte. Vor dem
Aufruf prüfen, nach dem Aufruf das Ergebnis prüfen — nicht nur den
Exitcode.

**Für fremden Code heißt das: auf einen Stand festgelegt.** Ein
Hersteller-Repo wird nicht auf dem Hauptzweig geholt und dann als root
ausgeführt — es wird auf **einen Commit** festgelegt, und der Installer,
der ausgeführt wird, wird **vor** dem Aufruf gegen eine hinterlegte
Prüfsumme geprüft. Weicht sie ab, bricht der Lauf benannt ab, statt den
geänderten Code zu starten. Ohne das ist `git pull` beim Hersteller
gleichbedeutend mit „führe aus, was heute dort steht".

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

### I7 — Der Exitcode eines Moduls sagt, wie es weitergeht

Ein Installer, der alles außer 0 als Abbruch behandelt, kommt bei einem
Neustart nie über die betroffene Stelle hinaus. Umgekehrt darf ein echter
Fehler nicht als Befund durchgewinkt werden. Deshalb vier Fälle:

| rc | Bedeutung | Was der Läufer tut |
|---|---|---|
| 0 | Ziel erreicht und nachgewiesen | weiter |
| 1 | Befund: nichts zu tun, oder Umgebung unvollständig | weiter, am Ende melden |
| 2 | Abbruch: Voraussetzung fehlt, oder niemand hat zugestimmt | Lauf endet hier |
| 3 | eingerichtet, aber **Neustart nötig** für den Nachweis | weiter, Neustart **einmal** am Ende |

**rc 3 bricht den Lauf nicht ab.** Genau darum geht es: Overlay und
Kernelmodul laden erst beim nächsten Start, und ein Lauf, der deshalb
endet, führt die folgenden Module nie aus — auf einer frischen
Installation also nie über den Anzeigeschritt hinaus. Der Läufer merkt
sich den Wunsch, führt alles Übrige aus und sagt am Ende **einmal**, dass
ein Neustart ansteht.

Der Rückgabewert des Gesamtlaufs bleibt sprechend: Kommt ein
Neustartwunsch und ist sonst alles in Ordnung, endet der Lauf mit 3 —
nicht mit 0, denn fertig ist er nicht. Ein echter Fehler (rc 1 oder 2)
schlägt den Neustartwunsch.

---

## 2. Modulaufbau

| # | Modul | Aufgabe |
|---|---|---|
| 00 | `source` | lokale SSOT-Kopie `source/`; der Läufer startet daraus neu (Baustein 2) |
| 10 | `check-system` | Board und Betriebssystem erkennen, Whisplay-Revision, Speicher, Platz |
| 20 | `install-packages` | Systempakete |
| 25 | `speicher` | zram (75 %) und Auslagerungsdatei, gestaffelt nach Kartengröße (§4b) |
| 30 | `install-headers` | Header beschaffen — **der schwierige Teil** (§3) |
| 40 | `install-display` | Anzeige erkennen und festhalten, neutrale Busse, Ton zur Laufzeit (§4) |
| 50 | `python` | venv, Abhängigkeiten **mit Versionsprüfung** (requirements + Anzeigemodul), Nachweis (§4b) |
| 60 | `overlay` *(geplant)* | Gerätebaum-Overlay, kollidierende abschalten (§5) |
| 70 | `alsa` *(geplant)* | Audio-Konfiguration |
| 80 | `models` *(geplant)* | sherpa-onnx-Modelle laden und prüfen |
| 95 | `config` *(geplant)* | `.env` aus Vorlage, Ollama-Adresse erfragen |
| 98 | `service` | systemd-Unit |
| 99 | `migrate` *(geplant)* | Übergänge von älteren Installationen |

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

### Unbekanntes Board (Regel 10k)

`unknown` ⇒ **Warnung, kein Abbruch.** Unbekannt heißt ungetestet, nicht
unvereinbar; wer es auf einem Pi 4 versuchen will, soll das dürfen. Die
Warnung nennt, was erkannt wurde, was erwartet wird, welche Profile es
gibt und was ohne Profil ungeprüft bleibt. Fortsetzen ist eine bewusste
Eingabe; nicht-interaktiv braucht es einen ausdrücklichen Schalter.

**Ohne Profil wird kein Profil geraten.** Module, die ohne Boardwissen
auskommen, laufen; die bootnahen Schritte (Overlay in die
Bootkonfiguration) werden übersprungen und benannt. Genau dieser eine
Schritt kostet bei einem Gerät ohne Bildschirm sonst den Ausbau der
SD-Karte — die Gefahr liegt im Eingriff, nicht in der Erkennung.

`--force-board <name>` wählt bewusst ein bekanntes Profil — für
Entwicklung und für neue Boards. Es wird nie in einer Warnung
vorgeschlagen, weil der Vorschlag die Wahl schon getroffen hätte.

Begründung und Wortlaut: `docs/DESIGN.md` Regel 10k.

### Whisplay-Revision

Der HAT hat ein EEPROM, das sich auslesen lässt:

    /proc/device-tree/hat/vendor      → "PiSugar"
    /proc/device-tree/hat/product_id  → "0x0001"

Damit ist die Platine erkennbar, ohne draufzuschauen. Ob sich daraus auch
**V1 gegen V2** unterscheiden lässt, ist noch offen — das gehört zu den
ersten Dingen, die Modul 10 auf echter Hardware beantworten muss. Bis
dahin bleibt die Warnung bestehen: V1 kann sich beim Tastendruck selbst
abschalten.

### Was sich am echten Gerät gezeigt hat

Messwerte, Fehlschläge und ihre Ursachen stehen in
`docs/HARDWARE-BEFUNDE.md` — getrennt von der Blaupause, weil es Befunde
sind und keine Entscheidungen. Wer dort eine Regel ableiten will, schlägt
sie vor; eingetragen wird sie in `DESIGN.md`.

Kurz, was den Installer betrifft:

- Der Hersteller-Installer setzt `make` und `gcc` in einem seiner beiden
  Pfade als vorhanden voraus. Auf DietPi sind sie es nicht — deshalb
  Modul 20 vor allem anderen.
- Ein Prüfbefehl, dessen Ergebnis von den Rechten des Aufrufers abhängt,
  misst nicht das System (`aplay -l` ohne `audio`-Gruppe).
- `/dev/i2c-*` belegt Userspace-Zugriff, nicht aktives I2C.

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

**Stand 11.10.2026 — was Modul 40 heute tut** (`docs/DISPLAYS.md` §4/§6,
DESIGN 6e-Ergänzung):

1. **Erkennen** über das Treiberpaket (`python3 -m chimera.displays
   erkennen --json`): Panel-Kennung per SPI (Pflicht), Codec per I2C
   (eindeutig), Spuren früherer Einrichtung (nur Beleg). Braucht freie
   Leitungen → läuft vor dem Dienst, als root. `CHIMERA_ANZEIGE` sticht.
   Ergebnis nach `state/anzeige`, Belege ins Protokoll.
2. **Busse** in der Bootkonfiguration: nur `spi` und `i2c_arm` aus
   `display.json` (`busse`). Sicherung nur, wenn wirklich eine Zeile
   fehlt. **Nie `i2s`** — der kollidiert auf den anderen Boards.
3. **Ton** (nur Profile mit `ton.alsa_karte`): Systempakete aus
   `ton.apt`; fehlt Kernelmodul oder Overlay-Datei, holt `network_git`
   die Herstellerquelle am festgelegten Commit und ruft `install_driver.sh`
   nach Prüfsummenvergleich (I4). Danach `boot_neutral()`: entfernt
   `dtparam=i2s=on` und `dtoverlay=<overlay>` wieder aus der
   Bootkonfiguration (Sicherung, Sidecar + `mv`, Zeilen mit
   `vorher_da` bleiben; `write_atomic` verweigert eine leere Datei), und
   schaltet die Hersteller-Unit `whisplay-soundcard-warmup` ab (Chimera
   setzt den Mixer selbst). `/etc/asound.conf` kommt aus der
   Herstellervorlage, nur wenn keine da ist. Dann **zur Laufzeit laden**:
   `python3 -m chimera.displays ton <typ>` (dtparam/dtoverlay aus
   `ton.*`, Mixer aus `ton.mixer`, wartet bis zu 5 s auf die Karte).
4. **Nachweis** = `pruefe` (SPI-Gerät) **und** ALSA-Karte vorhanden.
   rc 3 nur, wenn eine Bus-Zeile neu in die Bootkonfiguration kam.

Gemessen chimera-pi 11.10.2026: nach Reboot ohne Karte → Schritt 40 lädt
`dtparam i2s=on` + `dtoverlay whisplay-soundcard`, Karte nach ~2 s,
Mixer 80/80, rc 0 in 23 s; zweiter Lauf „bereits eingerichtet", rc 0.

### 4a. Modul 25 — Speicher (zram und Auslagerungsdatei)

Die Logik steht in `installer/lib/speicher.sh`, geprueft in
`tests/test-speicher.sh` (Werkzeuge als Shell-Funktionen) und auf
echter Hardware (chimera-pi, 11.10.2026). Mechanik aus PiPortal
uebernommen, nicht nachgebaut:

- **zram** ueber das Paket `zram-tools`: Konfiguration
  `/etc/default/zramswap` (`PERCENT=75`, `ALGO=lz4`, `PRIORITY=100`),
  Dienst `zramswap.service`. Das Paketskript rechnet
  `MemTotal * PERCENT / 100` und haelt `/dev/zram0` in `/proc/swaps`.
- **Auslagerungsdatei** ueber DietPis eigenes Werkzeug
  `dietpi-set_swapfile <MiB> <Pfad>`: Es pflegt fstab und
  `/boot/dietpi.txt` selbst, damit der Firstboot nichts zurueckdreht.
  Groesse: gestaffelt nach Groesse des Systemdatentraegers (2/4/8/16 GiB,
  Dezimal-GB wie aufgedruckt, gemessen in sysfs am Blockgeraet).
- **Idempotent nach Zustand:** Zielgroesse erreicht und aktiv -> nichts
  tun. Zu wenig Platz (Reserve 8 GiB, `CHIMERA_SWAP_RESERVE_MIB`)
  -> Befund, nicht kuerzen. Fremde zram-Verwaltung
  (`systemd-zram-generator`, `rpi-swap`, `dphys-swapfile`) -> Abbruch mit
  benannter Meldung; deren Umstellen ist ein offenes Ende (ROADMAP).
- **Manifest:** frueher Zustand der Datei als neue Art `swapdatei`
  (`vorher:<MiB>:<Ort>`, nur der ERSTE Umbau wird vermerkt — ein
  spaeterer Kartenwechsel ueberschreibt den Ausgangszustand nicht),
  `zram-tools` als `paket`, Original der zram-Konfiguration als
  `sicherung`.
- **Bewusste Ausnahme:** beim Ersetzen schaltet DietPis Werkzeug mit
  `swapoff -a` kurz ALLE Auslagerung ab, auch zram — danach wird
  `zramswap` neu gestartet (nach Zustand gemessen, nicht nach Marke).
  Design 5e begruendet die Ausnahme.
- **Rueckbau** (`uninstaller/steps/25-remove-speicher.sh`): fruehere
  Groesse und Ort mit demselben Werkzeug zurueck, zram-Konfiguration aus
  der Sicherung, `zramswap` neu. Das Paket nimmt Rueckbau 20 (`neu`, nur
  auf Wunsch).

### 4a-m. Modul 46 — Mikrofone messen

Welche Mikrofone einer Anzeige brauchbar sind, wird **gemessen, nicht
festgelegt**: Ein Defekt an einem Board darf nicht zur Einstellung für alle
werden, die das Repo ziehen.

- **Messung** (`python3 -m chimera.displays mikro`): Der eigene Lautsprecher
  spielt 1, 2 und 3 kHz, beide Kanäle nehmen gleichzeitig auf. Je Kanal und
  Ton: Grundton, Oberwellen 2–5, Rauschen im selben Band.
- **Entscheidung:** `beide`, `links`, `rechts` oder `keins`. Ein Kanal ist
  untauglich, wenn er den Ton nicht hört, mehr als 20 dB leiser ist als der
  andere oder bei der Mehrheit der Töne klirrt (Oberwellen über −10 dB).
  Nur leiser ist kein Defekt. Bei Zweifel bleibt es bei `beide`, mit Warnung.
- **Ergebnis:** `state/mikro.json` (Messwerte, Anzeige, Zeit) und
  `/etc/alsa/conf.d/50-chimera-mikro.conf` mit dem Gerät `chimera_mikro`.
  Bei einem guten Mikro bekommt man es mono, bei zweien beide Kanäle. Andere
  Programme behalten die Geräte des Herstellers.
- **Wann:** Nur im vollen Lauf, nicht beim Boot-Abgleich, weil die Messung
  Töne spielt. Neu gemessen wird, wenn sich die Anzeige geändert hat
  (Kartentausch), oder mit `CHIMERA_MIKRO_NEU=1 chimera-install --only 46`.
- Eine gescheiterte Messung ist kein Befund über die Mikrofone: Die alte
  Messung bleibt stehen. Eine fremde Datei am Zielort wird nicht angefasst.

Gemessen am chimera-pi: `rechts` mit dem Grund „links: klirrt“ (Oberwellen
links +2 bis −3 dB, rechts −23 bis −47 dB). Ein zweiter Lauf misst nicht
neu, und `arecord -D chimera_mikro` nimmt auf.

### 4b. Modul 50 — Python-Umgebung (venv)

Chimera ist ein Python-Dauerprozess. Debian hält `/usr/lib/python3` von
apt ab und lehnt `pip` dort seit Trixie ab (PEP 668) — zu Recht. Zwei
Wege lösen das: ein **venv** oder Systempakete mit
`--break-system-packages`. Chimera nimmt das venv:

- `--break-system-packages` wechselt die Tür aus, die Debian genau aus
  diesem Grund schließt — ein pip-Lauf dort kann Debian-Pakete
  überbieten, ohne dass der Nutzer es sieht.
- Ein venv gehört ganz Chimera, liegt unter `/opt/chimera/productive/venv`
  (Regel 10r: Code und venv getrennt, damit der Tausch von `code/` das
  venv nicht mitnimmt), und steht im Manifest (`verzeich`) — die Deinstallation kann es als
  Ganzes entfernen, ohne fremde Pakete anzufassen.

**`requirements.txt` im Repo ist die eine Quelle** der
Python-Abhängigkeiten. Der Installer liest sie, niemand anderer rät.
Stdlib-Module stehen dort nicht; was nur in einer Ausnahme gebraucht
wird, holt der Installer gezielt dazu (Schritt 20), nicht die
Anforderungsliste.

**Das Repo bleibt die Quelle des Moduls.** Chimera wird nicht ins venv
kopiert — ein `git pull` plus Installerlauf muss genügen (Regel 10).
Statt einer Kopie verdrahtet Schritt 50 den Quellpfad als
`chimera.pth` im `site-packages` des venv: das Modul ist dann unter
`python -m chimera` erreichbar, folgt aber dem Repo.

**Der Nachweis ist das Modul selbst**, nicht der Exitcode von pip:
`venv/bin/python -m chimera --pruefen` muss durchlaufen. Ein pip-Lauf
meldet Erfolg auch dann, wenn das Modul selbst nicht lauffähig ist
(Regel 10j).

**Abhängigkeiten mit Versionsprüfung (11.10.2026).** `lib/python.sh`
misst im venv (`importlib.metadata`), was von `requirements.txt` **und**
`deps.pip` des festgehaltenen Anzeigemoduls (`display.json`) fehlt oder
zu alt ist, holt **nur das** (`pip install --upgrade`), und misst nach —
das Ergebnis zählt, nicht pips Exitcode. Ein `pip install -r` bei jedem
Lauf hätte offline versagt, obwohl alles da war, und ein vorhandenes,
zu altes numpy als erfüllt durchgehen lassen. numpy steht seit heute in
`requirements.txt`: ohne es rechnet die RGB565-Umrechnung 25-mal
langsamer, und ein Pi Zero 2 W hält keine 15 Bilder je Sekunde.

Nachweis des Anzeigemoduls: `registry.panel_klasse(<typ>)` im venv —
lädt das Modul, **öffnet das Panel nicht** (das belegte die Leitungen des
laufenden Dienstes). Kein Herstellerbaum, keine zweite `.pth` mehr.

**Umgebungskonfiguration.** Die Vorlage `.env.example` liegt im
Repo-Wurzelverzeichnis — nur mit Platzhaltern, nie mit echten Werten
(Regel 12). Schritt 50 legt sie als `/opt/chimera/config/.env` ab, **nur wenn
dort noch keine steht**: eine von Hand ausgefüllte Datei wird nie
überschrieben, der zweite Installerlauf ändert nichts (idempotent).
Rechte 600 ab Anlage — in die Datei gehören später Schlüssel. Die
Vorlage bleibt daneben als `/opt/chimera/config/.env.example`. Was fehlt oder
noch auf dem Platzhalter steht, benennt `python -m chimera --pruefen`
je Connector — der Installer meldet keinen Erfolg für Werte, die er
nicht hat.

**Pfadregeln des Schritts:** Repo-Wurzel ist `dirname($0)/../..` relativ
zum Schritt (`installer/steps/` → Repo), daraus kommen
`requirements.txt`, `.env.example` und `src/`. Der Testbaum bildet
exakt dieses Layout nach — der erste Testbaum trug die Struktur an der
falschen Stelle, der echte Lauf wäre an `requirements.txt fehlt`
gescheitert, unentdeckt weil der Test grün war.

### 4c. Modul 98 — Dienst (Dienstnutzer und systemd-Unit)

**Boot-Abgleich (11.10.2026, DESIGN 6e-Ergänzung).** Schritt 98 legt
neben der Dienst-Unit `chimera-hardware.service` an: `Type=oneshot`,
root, `RemainAfterExit`, `Before=chimera.service`, `ExecStart=
chimera-install --hardware` aus `source/` (nur Module 40/45/50 — kein
Netzabgleich 00, kein 98). `SuccessExitStatus=1 3`: ein Befund („nichts
erkannt") oder ein Neustartwunsch verhindert den Dienst nicht, erst ein
Abbruch (≥ 2). `CHIMERA_NETWORK_LIMIT=20`: ohne Netz wird 20 s gewartet,
dann läuft der Dienst mit dem, was da ist; nachgeholt wird beim nächsten
Boot mit Netz. Die Dienst-Unit hat `After=`/`Wants=chimera-hardware`
(kein `Requires`: blind mit Grund ist besser als gar nicht).

Die Antwort des Abgleichs erreicht den Dienst über
`/run/chimera/anzeige.env` (`CHIMERA_ANZEIGE=<typ>`, von Schritt 40
geschrieben, `EnvironmentFile=-` in der Unit): tmpfs, je Boot frisch, und
der Dienstnutzer braucht kein Leserecht auf `state/`.

Gemessen chimera-pi: Abgleich 17,8 s (Schritt 40: Erkennung 3,3 s,
Profil 1,2 s, Ton laden 2,0 s; Schritt 50: Inhaltsprüfsumme 4,4 s,
Nachweis 5,1 s), Dienst startet danach mit `Anzeige: whisplay 240x280`
und Ton — ohne Zutun. Gemessen mit `journalctl -o short-monotonic`: Die
Wanduhr springt beim Boot mit der Zeitsynchronisation (fake-hwclock), eine
erste Messung über die Wanduhr ergab deshalb fälschlich 31 s.

Chimera läuft als Dauerdienst `chimera.service`. Die Logik steht in
`installer/lib/service.sh`, der Schritt ruft nur auf — so ist sie ohne
systemd prüfbar (`tests/test-service.sh`, Werkzeuge als Shell-Funktionen).

**Eigener Systemnutzer `chimera`, nicht root.** Der Agent hat ein
Werkzeug, das Programme startet; die Schranken davor (`agent/safety.py`)
sind ernst gemeint, aber eine Schranke ersetzt keine fehlenden Rechte.
Gibt es den Nutzer schon, wird er übernommen und als `vorher_da`
vermerkt — der Rückbau löscht ihn dann nie (neue Manifest-Art `nutzer`).

**Hardwaregruppen in der Unit, nicht am Nutzer.** `SupplementaryGroups=`
nennt nur Gruppen, die es auf dem System gibt (`audio spi gpio i2c video`,
gefiltert per `getent`) — eine fehlende Gruppe ließe systemd den Start
verweigern. Damit gibt es kein `usermod` und nichts zurückzunehmen außer
der Unit.

**Datenablage `/home/<nutzer>/chimera/data`** (700, gehört dem
Dienstnutzer, in Schritt 98 angelegt und geprüft), dort liegt
`CHIMERA_HOME`. Das Manifest in `/opt/chimera/state` gehört root und
bleibt für den Dienst unlesbar (Regel 10r):
Sonst könnte ein Werkzeugaufruf des Agenten bestimmen, was der
Deinstallierer löscht. `ProtectSystem=strict` und `ProtectHome=read-only`
setzen das durch.

**Startbegrenzung (Regel 10p, Punkt 4).** `StartLimitIntervalSec=300`
und `StartLimitBurst=5` stehen in `[Unit]` — in `[Service]` ignoriert
systemd sie mit einer Warnung im Journal, und die Unit sieht trotzdem
richtig aus. `Restart=on-failure`, aber `RestartPreventExitStatus=2`:
Exitcode 2 heißt „Konfiguration falsch" (etwa Telegram-Token ohne
erlaubte Absender), und ein Neustart würde daran nichts ändern.

**Dienstmodus im Programm.** `ExecStart` ruft `python -m chimera
--dienst`. Ohne ihn liefe das Terminalgespräch: Unter systemd ist stdin
leer, das Gespräch endet sofort mit 0, und die Unit hielte das für ein
sauberes Ende. `--dienst` wartet auf SIGTERM, öffnet Telegram, wenn ein
Token gesetzt ist, und läuft ohne Sprachmodell weiter (Gesicht).

**Nachweis: aktiv nach 10 s und `NRestarts=0`.** `is-active` allein
sieht eine Neustartschleife als gesund, wenn man im richtigen Moment
fragt. Erst wenn beides stimmt, gilt der Schritt als erledigt.

**Protokolle: Datei im RAM, Abgleich beim Stopp und in Ruhezeiten**
(DESIGN 10r). `--dienst` schreibt zusätzlich zum Journal
`dienst-<zeit>.log` nach `$CHIMERA_LOG_RAM` (`RuntimeDirectory=`), ab
1 MiB in Stücken `dienst-<zeit>.1.log` (höchstens drei). Auf die Karte
bringt sie `installer/bin/log-abgleich.sh` (lädt `common.sh`, ruft
`log_sync`/`log_rotate`): als `ExecStopPost=` sofort, und über
`chimera-logabgleich.timer` alle 5 min mit `--ruhig` — abgeglichen wird,
wenn 120 s nichts geschrieben wurde, spätestens aber nach einer Stunde.
Der Kurzdienst des Timers hat bewusst **kein** `RuntimeDirectory=`:
systemd löschte es an dessen Ende und mit ihm die Protokolle des
laufenden Hauptdienstes. Timer und Kurzdienst stehen im Manifest
(`datei`, `dienst`); der Rückbau schaltet den Timer vor dem Dienst ab.
Mit echtem systemd 257 am chimera-pi geprüft (11.10.2026).

**Ein `git pull` startet den Dienst neu.** Der Schritt hält eine
Prüfsumme über `src/` und `requirements.txt` fest
(`/opt/chimera/state/dienst-stand`) — erst **nach** gelungenem Nachweis.
Weicht sie ab, wird neu gestartet; sonst liefe nach „pull plus
Installerlauf" weiter der alte Code (Regel 10). Ein gescheiterter Start
hält keinen Stand fest, der nächste Lauf versucht es erneut.

**Lesbarkeit vorher prüfen.** Die `.pth` aus Schritt 50 zeigt ins Repo.
Liegt es in einem geschlossenen Verzeichnis (`/root`), kann der
Dienstnutzer das Programm nicht lesen, und der Dienst stirbt beim Start.
Der Schritt prüft das per `runuser` vor dem Schreiben der Unit und
bricht benannt ab (Ausweg: Repo nach `/opt/chimera/repo`).

**Speicherbegrenzung steht nicht in der Unit.** `MemoryMax=` wirkt auf dem
Pi nicht (Regel 10q, gemessen) und wäre stiller Erfolg. Die
Selbstbegrenzung im Prozess ist ein eigener Punkt der Roadmap.

**Rückbau** (`uninstaller/steps/98-remove-service.sh`): stoppen und
abschalten (`disable --now`, am Ergebnis geprüft), Unit und Standdatei
entfernen, `daemon-reload`, zuletzt den Nutzer — nur wenn er `neu` ist.
Die Nutzerdaten bleiben (§6).

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
