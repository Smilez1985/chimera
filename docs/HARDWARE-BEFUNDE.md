# Befunde von echter Hardware

Was sich erst am Gerät gezeigt hat. **Kein Entwurfsdokument** — die
Blaupause steht in `DESIGN.md`, hier stehen Messwerte, Fehlschläge und
ihre Ursachen.

Wer eine Regel daraus ableiten will, schlägt sie vor; eingetragen wird sie
in `DESIGN.md`, nicht hier.

---

## Gerät

| | |
|---|---|
| Board | Raspberry Pi Zero 2 W Rev 1.0, `raspberrypi,model-zero-2-w` |
| System | DietPi 10.7 auf Debian 13 (Trixie) |
| Kernel | 6.18.50+rpt-rpi-v8 |
| Speicher | 462 MB nutzbar von 512 MB |
| Python | **3.13.5** |
| HAT | PiSugar Whisplay, aufgesteckt |

**Python 3.13 ist entscheidend für die Audio-Anbindung (Regel 5g):** Der
dokumentierte `resource_tracker`-Kniff aus Noisy ist dort nicht mehr
nötig, `SharedMemory(track=False)` gibt es ab 3.13 offiziell. Die ältere
Umgehung würde funktionieren, aber sie ist der Umweg.

---

## Erster Preflight auf echter Hardware

Exitcode 0, alles richtig erkannt. Bemerkenswert:

- **Regel 10b greift.** Das Board wurde über `compatible` bestimmt, nicht
  über den Klartextnamen. Der Hersteller-Installer von PiSugar macht es
  anders (`[[ "$model" == *"Radxa"* ]]`) und würde jedes Radxa-Board auf
  dasselbe Profil legen.
- Die Speicherwarnung stimmt: Bei 462 MB meldet der Preflight korrekt,
  dass STT und TTS rotieren müssen.
- Die Header-Empfehlung war richtig (`raspberrypi-kernel-headers`).

### Ausgangslage vor dem ersten Eingriff

```
kein /dev/i2c*, kein /dev/spi*
kein /proc/device-tree/hat/
dtparam=audio=off  (DietPi-Vorgabe)
wm8960-soundcard.dtbo liegt bereits im System
```

**Ohne aktives I2C liest die Firmware das HAT-EEPROM nicht.** Ein
fehlender `hat`-Knoten sagt vor dem ersten Einschalten von `i2c_arm`
deshalb *nichts* über die Hardware aus — nur über die Sichtbarkeit. Das
ist der Unterschied, den Regel 10j meint, und er ist hier real: Der HAT
steckte die ganze Zeit drauf.

---

## Whisplay-Treiber: was wirklich passiert ist

### Der Herstellerinstaller hat eine Lücke

`audio/whisplay-soundcard/scripts/install.sh` hat zwei Pfade für die
Kernel-Header. Der eine (Zeile 142) installiert
`raspberrypi-kernel-headers` **und** Bauwerkzeug; der andere (Zeile 159)
installiert `linux-headers-$(uname -r)` **ohne** `make` und `gcc`.

Auf Raspberry Pi OS fällt das nicht auf — dort sind beide vorinstalliert.
**Auf DietPi nicht.** Der Lauf brach bei Schritt 3 von 8 ab:

```
[3/8] Building snd-soc-whisplay-soundcard.ko ...
install.sh: Zeile 569: make: Kommando nicht gefunden.
```

Zu diesem Zeitpunkt hatte er bereits rund 40 Pakete nachgeladen — der
Abbruch kam also nach dem ersten Eingriff, nicht davor.

**Daraus folgte Modul 20:** Abhängigkeiten werden geprüft und geholt,
bevor irgendein Modul anfängt. Und Modul 40 prüft die Voraussetzungen des
Fremdinstallers selbst, statt sich darauf zu verlassen, dass er es tut —
fremder Code ist fremder Code (Regel 5f).

### Mein Modul hat den Fehlschlag beschönigt

Schwerwiegender als der fehlende Compiler: Modul 40 meldete danach

> Ergebnis: eingerichtet, aber noch nicht nachweisbar.
> Das ist der Normalfall direkt nach der Installation.

Das war **falsch**. Es war kein Normalfall, es war ein Fehlschlag — das
Kernelmodul existierte nicht. Die Meldung war für den Fall gedacht, dass
Overlay und Modul erst beim Neustart laden, und sie deckte ungewollt auch
den echten Fehler ab.

Behoben, indem am **Ergebnis** unterschieden wird: Gibt es
`snd-soc-whisplay*.ko` unter `/lib/modules/$(uname -r)`? Wenn nein, ist
es ein Fehlschlag, unabhängig vom Exitcode und unabhängig davon, ob ein
Neustart bevorsteht. Der Grund wird aus dem Herstellerprotokoll
herausgesucht und gezeigt.

Das ist Regel 8a in einer Form, die beim Entwurf nicht offensichtlich
war: **Ein zu freundlich formulierter Zwischenzustand kann einen Fehler
verdecken.** Nicht nur Schweigen ist gefährlich, auch Beschönigen.

### Zweiter Lauf: erfolgreich

Nach dem Nachinstallieren von `build-essential`:

```
[3/8] Building snd-soc-whisplay-soundcard.ko ...  -> gebaut
[  7.863554] whisplay-soundcard sound: Whisplay 'whisplaysound' registered (chip=WM8960)
[  8.779303] Boot defaults applied (playback = 80, capture = 80)
[  9.279092] Userspace mixer: 2 public controls active, 59 legacy controls removed
```

Nach dem Neustart:

```
Karte 0: whisplaysound [Whisplay Sound],
  Gerät 0: Whisplay HiFi wm8960-hifi-0
```

**Der Codec ist WM8960**, nicht ES8389. Der Treiber meldet ihn korrekt
unter dem einheitlichen Kartennamen.

---

## Der Nachweis hing an den Rechten des Aufrufers

Direkt nach dem Neustart meldete `aplay -l` als Nutzer `dietpi`:

```
aplay: device_list:279: keine Soundkarten gefunden ...
```

Gleichzeitig stand in `/proc/asound/cards` **„Whisplay Sound"**, und
`/dev/snd/` war vollständig da. Die Karte existierte — der Nutzer war
nur nicht in der Gruppe `audio`.

Das ist ein **Mangel im Nachweis, nicht in der Installation**: Ein
Prüfbefehl, dessen Ergebnis davon abhängt, wer ihn ausführt, misst nicht
den Zustand des Systems. Wäre der Lauf hier abgebrochen, hätte man den
Fehler beim Treiber gesucht.

DietPi legt den Nutzer `dietpi` ohne `audio`-Gruppe an. Das gehört in die
Installation (und ins Bestandsverzeichnis, denn es ist eine Änderung am
System).

---

## Fallen bei der Erkennung

### `/dev/i2c-*` ist kein Beleg für aktives I2C

Nach dem Neustart gab es `/dev/spidev0.0` und `0.1`, aber **kein**
`/dev/i2c-1` — obwohl `dtparam=i2c_arm=on` gesetzt war und der Codec
nachweislich über I2C angesprochen wurde (`wm8960 1-001a` im Kernel-Log).

Grund: `/dev/i2c-*` entsteht durch das Modul `i2c-dev`, das nur für
*Userspace*-Zugriff nötig ist. Der Kernel-Treiber braucht es nicht.

**Folge für `anzeige_erkennung_moeglich()`:** Die Prüfung auf
`/dev/i2c-*` beantwortet nicht „ist I2C an", sondern „kann Userspace auf
I2C zugreifen". Für die HAT-Erkennung über das EEPROM ist das die
richtige Frage — für „läuft der Codec" die falsche.

### Der HAT-Knoten blieb auch nach dem Neustart leer

`/proc/device-tree/hat/` existiert weiterhin nicht, obwohl der HAT läuft.
Bedeutet: **Das EEPROM dieses Exemplars ist nicht programmiert.** Damit
ist auch die Frage nach dem Overlay-Weg beantwortet (siehe
`WHISPLAY-TREIBER.md`): Ohne EEPROM schreibt der Installer
`dtoverlay=whisplay-soundcard` in die `config.txt` — und genau das ist
hier passiert.

Die Erkennung über das EEPROM funktioniert also bei diesem Gerät
grundsätzlich nicht. `CHIMERA_ANZEIGE=whisplay` war nötig und richtig.

---

## Shell-Fallen, die Zeit gekostet haben

### `while` in einer Pipe läuft in einer Subshell

```sh
liste | while read -r x; do FEHLT="$FEHLT $x"; done
echo "$FEHLT"     # leer
```

Klassiker, aber im Ergebnis tückisch: Modul 20 hielt **vorhandene** Pakete
für fehlend, weil die Sammelvariable draußen leer blieb. Lösung: über eine
Datei sammeln und nach der Schleife lesen.

### Ein Prüfbefehl muss auf Existenz prüfen, nicht auf Erfolg

```sh
git        # Exit 1 (zeigt nur die Hilfe)  -> gilt als "fehlt"
command -v git   # Exit 0                  -> richtig
```

Dieselbe Klasse wie `/dev/tcp` in BusyBox: Das Werkzeug tut etwas anderes
als gedacht, und das Ergebnis wird als Messung gelesen.

### Ein Trockenlauf darf nichts anlegen — auch keine Sicherung

Der erste Trockenlauf von Modul 40 scheiterte mit „Keine Berechtigung",
weil er `backup_file` aufrief. Eine Sicherung im Trockenlauf **wäre selbst
eine Änderung**. Und er prüfte auf eine Datei, die er nicht geholt hatte —
er meldete sein eigenes Nichtstun als Fehler.

Dazu verwies er auf eine Sicherung, die es nicht gab: „Die gesicherte
Bootkonfiguration liegt neben …". Ein Verweis auf einen Rückweg, den
niemand angelegt hat, ist schlimmer als keiner.

---

## Was das Bestandsverzeichnis leistet

`/var/lib/chimera/bestand.tsv`, angelegt von `lib/bestand.sh`:

```
zeit                  modul       art     name           angabe
2026-09-29T23:58:27   20-pakete   paket   python3-pil    neu
2026-09-29T23:58:27   20-pakete   paket   i2c-tools      neu
```

Der Kern ist die Unterscheidung **`neu`** gegen **`vorher_da`**:
`apt-get install` meldet Erfolg auch für ein bereits installiertes Paket.
Wer das nicht vor der Installation prüft, kann später nicht sagen, was er
entfernen darf — und eine Deinstallation, die alles Aufgelistete entfernt,
reißt Fremdes mit.

Dasselbe gilt für Zeilen in fremden Dateien: Stand `dtparam=spi=on` schon
in der `config.txt`, gehört sie dem Nutzer und bleibt beim Aufräumen
stehen.

---

## Funktionsnachweis am Gerät

Nicht „der Treiber meldet sich", sondern: Ein Mensch hat es gesehen bzw.
gehört. Der Unterschied ist der ganze Punkt.

| Funktion | Nachweis |
|---|---|
| **LCD** | Testmuster fotografiert: vier Farbfelder in richtiger Lage, Rahmen an allen vier Kanten, beide Diagonalen, kein Versatz. Panel ist hochkant 240×280. |
| **Lautsprecher** | 440-Hz-Sinus über `speaker-test -D plughw:whisplaysound` gehört |
| **Mikrofon** | Aufnahme mit Pegel 0,0203 — bei zugedrehtem Regler 0,0059. Faktor 3,4, also echtes Signal statt Grundrauschen |
| **RGB-LED** | Wechsel vom blauen Grundzustand auf Grün, bestätigt |

Nötige Pakete für die Python-Ansteuerung: `python3-spidev`,
`python3-gpiozero`, `python3-libgpiod`, `python3-pil`, `python3-numpy`.
`gpiod` fehlte zuerst und ist in `example/requirements.txt` des
Herstellers gelistet, nicht im Installer.

### Die LED fällt zurück, wenn der Prozess endet

Zuerst sah es aus, als hätte die LED-Steuerung nicht gewirkt: Die LED war
seit dem Einschalten blau und danach wieder blau. Sie hatte gewirkt — aber
nur für die Laufzeit des Testskripts.

Grund: `gpiod` hält die GPIO-Leitungen als Ressource des laufenden
Prozesses. Endet er, gibt der Kernel sie frei und die LED fällt in ihren
Grundzustand.

**Folge für Chimera:** Der Renderer muss dauerhaft laufen, sonst ist nach
jedem Programmende alles dunkel. Das stützt Regel 7a (Dauer-Faden) mit
einem Grund, der beim Entwurf nicht bekannt war.

**Folge für die Fernwartung:** Ein Test, der einen Zustand herstellen und
halten soll, muss vom Aufruf abgekoppelt laufen (`setsid`, `nohup`,
`tmux`) — sonst stirbt er mit der SSH-Sitzung. Ein `timeout` auf der
aufrufenden Seite hilft dabei nicht: Er beendet den lokalen Client, nicht
den Prozess auf dem Zielrechner.

## Offen

- **Whisplay V1 gegen V2 ist nicht bestimmbar**, solange das EEPROM nicht
  programmiert ist. Die Herstellerwarnung (5 V auf der Tastenleitung)
  nennt ausdrücklich nur Orange Pi Zero 3W und Radxa Cubie A7Z.
- Bildrate des Renderers auf diesem Board: ungemessen. Die 15 aus Noisy
  sind übernommen, nicht belegt.
- Ob `dtparam=audio=off` (DietPi-Vorgabe) bleiben kann: bisher ja, der HAT
  bringt seinen eigenen Codec mit. Nicht unter Last geprüft.
- **Der Knopf ist ungeprüft.** Er ist die einzige Funktion des HAT, die
  noch nicht nachgewiesen wurde — und ausgerechnet die, vor der die
  V1-Warnung steht (5 V auf der Tastenleitung). Solange die Revision
  nicht feststeht, wird er nicht gedrückt.
