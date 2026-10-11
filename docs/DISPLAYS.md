# Anzeigen

Chimera ist **nicht auf ein Panel festgelegt.** Das ist keine
Bequemlichkeit, sondern senkt die Einstiegshürde: Wer schon einen Pi mit
E-Paper oder einen GamePi13 hat, soll Chimera benutzen können, ohne erst
Hardware zu kaufen.

Stand: 2026-09-29. Entwurf — außer dem Whisplay-Panel ist noch nichts
gebaut.

---

## 1. Grundsatz

### Architekturregel 6c — Das Panel ist eine Eigenschaft, keine Annahme

Kein Teil von Chimera oberhalb der Anzeigeschicht darf wissen, welches
Panel angeschlossen ist. Der Renderer fragt nach Fläche und Fähigkeiten,
nicht nach dem Modell.

Daraus folgt, was ein Panel beschreiben muss:

| Eigenschaft | Beispiele | Wirkung |
|---|---|---|
| `width`, `height` | 240×280, 250×122, 240×240 | Bildgröße |
| `colors` | `rgb565`, `mono`, `mono+red` | Farbtiefe |
| `refresh_hz` | 15, 30, ~0.07 | ob Animation möglich ist |
| `full_refresh_every` | – / 3 | Geisterbilder bei E-Paper |
| `busy_timeout` | 45 s / 120 s | Wartezeit |
| `interface` | SPI, I²C | Anbindung |

`refresh_hz` ist das entscheidende Feld: Es trennt **Bewegtbild** von
**Standbild** und bestimmt damit, welche Darstellungsart überhaupt
infrage kommt (§3).

---

## 2. Unterstützte Anzeigen

| Panel | Auflösung | Farben | Bildrate | Stand |
|---|---|---|---|---|
| **Whisplay HAT** | 240×280 | RGB565 | ~30 | ✅ gebaut |
| **GamePi13** (ST7789) | 240×240 | RGB565 | 15 | geplant |
| **Waveshare 2.13" V4 mono** | 250×122 | 1 Bit | ~0,4 /s | geplant |
| **Waveshare 2.13" B** | 250×122 | S/W + Rot | ~0,07 /s | geplant |

Der E-Paper-Treiber wird **aus dem eigenen Fork übernommen**, nicht aus
dem Upstream: Dort ist die Unterscheidung mono gegen B bereits gebaut
(Zweig `feat/display-variant-detect-v2`), samt dem Wissen, das teuer ist:

- Die B-Variante macht **immer** Vollbild-Auffrischung, rund 15–20 s
- Zeitgrenze deshalb 120 s statt 45 s, Wiederholung nach 20 s statt 4 s
- Mindestabstand zwischen Auffrischungen, sonst arbeitet das Panel
  dauernd
- Geisterbild-Behandlung nur bei der mono-Variante nötig
- Rot ist bei der B-Variante ein **Akzent**, keine vierte Farbe

Diese Zahlen stehen künftig im Panel-Profil, nicht verstreut im Code.

---

## 3. Darstellungsarten

Eine Anzeige, die 20 Sekunden für ein Bild braucht, kann keinen Avatar
animieren. Sie kann aber ein **gutes Standbild** zeigen.

### Architekturregel 6d — Dieselben Moods, verschiedene Darstellungen

Der Mood bleibt derselbe Datensatz (`docs/DESIGN.md` §3). Was sich ändert,
ist seine Umsetzung:

| Art | für | was passiert |
|---|---|---|
| **animiert** | RGB, ≥ 10 Bilder/s | voller Renderer, Bewegung, Partikel |
| **Standbild** | RGB, langsam | ein Bild je Moodwechsel, keine Bewegung |
| **reduziert** | 1 Bit | Umrisse statt Flächen, kein Schein, keine Partikel |
| **reduziert+Akzent** | S/W + Rot | wie reduziert, ein Element rot |

Die reduzierte Art ist **kein Notbehelf**, sondern eine eigene Gestaltung.
Ein Gesicht in Strichzeichnung kann ausdrucksstärker sein als eines mit
Farbverlauf — es muss nur dafür entworfen sein.

Praktisch heißt das: Die Mood-Felder werden übersetzt, nicht ignoriert.
Körperfarbe wird zu Füllmuster oder Umrissstärke, der Schein entfällt,
Partikel werden zu wenigen festen Zeichen. Bewegungsfelder
(`headbang_speed` und dergleichen) bestimmen bei Standbildern die
**Pose** statt der Bewegung.

Die freien Zeichenformen (Regel 1a) funktionieren in allen Arten — sie
sind ohnehin geometrisch und brauchen nur eine Farbabbildung.

---

## 4. Erkennung

### Architekturregel 6e — Bei jedem Start prüfen, nicht nur bei der Installation

Wer das Panel wechselt, soll das Gerät einschalten können und es
funktioniert. Deshalb:

1. **Bei jedem Start** wird erkannt, was angeschlossen ist.
2. Weicht es von der letzten Erkennung ab, werden die fehlenden
   Abhängigkeiten **nachinstalliert** und der passende Treiber aktiviert.
3. Erst dann startet die Anzeige.

Das ist dieselbe Haltung wie beim Installer: Er ist auch das
Aktualisierungswerkzeug, und ein Lauf bringt das System in den richtigen
Zustand — unabhängig davon, in welchem es war.

### Woran ein Panel erkannt wird

| Quelle | erkennt |
|---|---|
| HAT-EEPROM (`/proc/device-tree/hat/`) | Whisplay (PiSugar), andere HATs mit EEPROM |
| Gerätebaum-Overlays in der Bootkonfiguration | was eingerichtet wurde |
| Gebaute Kernelmodule (`/lib/modules/…`) | der Treiber eines Panels wurde installiert |
| ALSA-Karte (`/proc/asound/cards`) | Panels mit eigenem Codec (Whisplay: `whisplaysound`) |
| SPI-Geräte (`/dev/spidev*`) | ob überhaupt SPI aktiv ist |
| Panel-Antwort | ST7789 lässt sich auslesen; E-Paper nicht zuverlässig |
| Einstellung | letzte Instanz, wenn nichts eindeutig ist |

**Der Whisplay-HAT ist der Fall, der das erzwingt.** Auf dem
ausgelieferten Exemplar ist das EEPROM nachweislich **nicht
programmiert** — der HAT-Knoten bleibt auch nach einem Neustart leer
(`docs/HARDWARE-BEFUNDE.md`). Wer nur dort nachsieht, findet „keins" und
bricht ab, obwohl die Anzeige angeschlossen ist. Die übrigen Quellen sind
deshalb am Herstellertreiber belegt, nicht vermutet: Er schreibt
`dtoverlay=whisplay-soundcard` in die Bootkonfiguration, trägt die Module
in `/etc/modules` ein und benennt die ALSA-Karte `whisplaysound`.

**Nicht alles ist erkennbar.** Ein E-Paper meldet sich nicht von selbst —
die mono- und die B-Variante sind elektrisch gleich. Dafür bleibt die
Einstellung, und die Erkennung schlägt vor, statt zu raten (Regel 10g).

Bei mehrdeutigem Befund: melden, Vorschlag nennen, Einstellung verlangen.
Nicht das nächstbeste Profil nehmen — ein falscher Treiber auf einem
E-Paper kann das Panel beschädigen.

### Gebaut (11.10.2026): drei Klassen, Prüfliste je Modul

Die Prüfliste steht in `display.json` des Moduls (`erkennung`), die
Entscheidung in `src/chimera/displays/erkennen.py`
(`python3 -m chimera.displays erkennen [--json]`):

| Klasse | Bedeutung | Whisplay |
|---|---|---|
| `pflicht` | ohne Treffer kommt das Modul nicht in Frage | ST7789-Kennung mit DC27: `8181b3` |
| `eindeutig` | ein Treffer wählt — wenn die Pflicht erfüllt ist | Codec am I2C-1: `0x1a` (WM8960) oder `0x10` (ES8389) |
| `eingerichtet` | belegt nur, dass schon einmal installiert wurde — **wählt nicht** | Overlay-Zeile, ALSA-Karte `whisplaysound`, Kernelmodul |
| `rueckfall` | wenn nichts passt | Modul `keine` |

Gewählt wird automatisch bei **genau einem** eindeutigen Modul. Erfüllt
genau ein Modul die Pflicht ohne eindeutig zu sein (GamePi13: Kennung ja,
kein Codec), wird es gewählt und der Grund genannt. Sonst Kandidaten
melden, `CHIMERA_ANZEIGE` entscheidet.

**Messfakten, die das Verfahren tragen:**

- Die ST7789-Kennung ist nur im **3-Draht-Modus über SDA** lesbar (kein
  MISO auf dem Whisplay-HAT, PiSugar-Schaltplan). Sie lautet auf Whisplay
  **und** GamePi13 `81 81 B3` — sie trennt die Boards nicht, nur Panel
  von keinem Panel. Das Lesen braucht DC = low, also freie Leitungen.
- Der WM8960 antwortet auf einen SMBus-Quick-Write auch **ohne gebundenen
  Treiber** (unbind gemessen); Register lesen geht nicht (write-only).
  Vor dem Dienst gibt es keinen Treiber und kein `/dev/i2c-1` — die
  Erkennung lädt als root `i2c-dev` nach.
- Belegte Leitungen (laufender Dienst) sind ein eigener Befund
  (`belegt`), kein „kein Panel". Deshalb läuft die Erkennung **vor** dem
  Dienst, als root (Boot-Abgleich), nie im Dienst.
- Die HAT-EEPROM-Zeile der Tabelle oben bleibt richtig, trägt aber auf
  unserem Exemplar nichts: nur die ES8389-Fassung hat ein EEPROM
  (CAT24C32), die WM8960-Fassung keines.

---

## 5. Aufbau

    Renderer
       │  liefert ein PIL-Bild in Panelgröße
       ▼
    Darstellungsart          animiert │ Standbild │ reduziert
       │  übersetzt den Mood in das, was das Panel kann
       ▼
    Panel (Treiber)          Whisplay │ ST7789 │ EPD mono │ EPD B
       │
       ▼
    SPI / I²C

Jeder Treiber ist ein Modul mit derselben Schnittstelle (`show`,
`backlight`, `led`, `close`) — so wie `WhisplayPanel` und `NullPanel` es
heute schon sind. Ein neues Panel ist ein Modul plus ein Profileintrag,
genau wie ein neues Board im Installer (Regel 10c).

**Gebaut (11.10.2026):** `src/chimera/displays/`

    displays/
      base.py        Panel, NullPanel, Profil (aus display.json), to_rgb565
      registry.py    Ordner = Modul: typen(), profil(typ), oeffne(typ)
      erkennen.py    Klassen pflicht/eindeutig/eingerichtet, Befund als JSON
      ton.py         Laufzeit-Overlays laden, Mixer setzen, ALSA nachweisen
      gpio.py        GPIO-Chardev ABI v2 (ctypes), LeitungBelegt
      spi.py         spidev write + 3-Draht-Lesen (eine ioctl-Nachricht)
      st7789.py      Kern: Einschaltfolge, Fenster, schreibe_bild, kennung_lesen
      softpwm.py     Software-PWM (Backlight, LED)
      i2c.py         SMBus-Quick-Write ohne i2c-tools, i2c-dev nachladen
      whisplay/      display.json + panel.py (LCD, LED, Backlight, Taste)
      keine/         Rückfall: zählt Bilder, zeigt nichts

`display.json` ist die **einzige** Beschreibung einer Anzeige: Maße,
Bildrate, Pins, Abhängigkeiten (`deps.pip/apt`), Erkennungsprüfliste,
Ton (Overlays, Mixer, Herstellerquelle). Dieselbe Datei liest der
Installer (`lib/display.sh` über `python3 -m chimera.displays profil`).
`chimera.display.panel` ist nur noch die Fassade: `open_panel()` folgt
`CHIMERA_ANZEIGE` bzw. `state/anzeige` und erkennt nicht selbst.

Ein neues Panel: Ordner anlegen, `display.json` schreiben, eine
`*Panel`-Klasse in `panel.py` — keine Zeile anderswo.

---

## 6. Installer

Pro Panel ein Modul, gesteuert vom Profil:

    modules/50-display-whisplay.sh
    modules/50-display-st7789.sh
    modules/50-display-epaper.sh

Das Modul mit der passenden Kennung läuft, die anderen melden „nicht
zutreffend" und tun nichts. Nummer 50 bleibt für alle gleich, weil sie
sich gegenseitig ausschließen.

Gemeinsam ist ihnen: Abhängigkeiten installieren, Overlay eintragen,
Bootkonfiguration anfassen (mit Sicherung und, auf eMMC, mit Bestätigung),
prüfen ob es funktioniert.

**Gebaut (11.10.2026) — abweichend von der Skizze oben, gleiche Absicht:**
Statt eines Shell-Moduls je Panel gibt es **ein** Anzeigemodul
(`display.json` + `panel.py`) je Panel und **zwei** Installerschritte, die
daraus lesen:

- **Schritt 40** erkennt (Treiberpaket, vor dem Dienst), hält den Typ in
  `state/anzeige` fest, stellt die **neutralen** Busse sicher (`spi`,
  `i2c_arm` — nie `i2s`), und richtet den **Ton** ein, wenn das Profil
  einen nennt: Systempakete (`alsa-utils`, `raspi-utils-dt`),
  Herstellerinstaller für das Kernelmodul (Commit + Prüfsumme),
  `/etc/asound.conf` aus der Herstellervorlage (nur wenn keine da ist),
  dann **Overlays zur Laufzeit** (`python3 -m chimera.displays ton
  <typ>`), Mixer 80/80, Nachweis = ALSA-Karte vorhanden. Was der
  Herstellerinstaller in die Bootkonfiguration schreibt, wird wieder
  herausgenommen (`boot_neutral`, mit Sicherung, Zeilen von vor Chimera
  bleiben).
- **Schritt 50** holt die Python-Abhängigkeiten aus `requirements.txt`
  **und** `deps.pip` des Moduls — **mit Versionsprüfung**
  (`lib/python.sh`: `pydep_ensure` misst im venv, holt nur Fehlendes oder
  zu Altes, misst nach). Nachweis: das Modul ist über die Registry ladbar,
  ohne das Panel zu öffnen.

Kein Herstellercode mehr im venv, keine zweite `.pth`, kein Quellbau.
Die Shell-Tabelle in `lib/display.sh` ist weg; `display_get` liest
`display.json`.

**Beim Start** läuft `chimera-hardware.service` (Schritt 98 legt sie an):
`chimera-install --hardware` vor dem Dienst, als root, mit freien
Leitungen — Erkennung, Ton laden, `state/anzeige` und
`/run/chimera/anzeige.env`. Der Dienst öffnet dann, was dort steht
(`CHIMERA_ANZEIGE`), und erkennt nicht selbst. **Noch nicht gebaut:** das
Dienst-Template `chimera@<typ>.service` (ein Dienst je Anzeigeart) — heute
startet `chimera.service` mit der Anzeige aus der Umgebung; ein E-Paper
bekäme denselben Renderer. Das trägt, solange nur Whisplay existiert, und
steht in der ROADMAP.

---

## 7. Offen

- Der reduzierte Renderer für 1-Bit-Panels ist **Entwurf, kein Code**.
  Dass Noisys Renderer sich dafür abspecken lässt, ist plausibel, aber
  ungeprüft.
- Ob die Bildrate auf dem GamePi13 (240×240) identisch zur Whisplay ist,
  muss gemessen werden.
- Ob sich die E-Paper-Varianten zuverlässig unterscheiden lassen, ist
  offen — vorerst über die Einstellung.
