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
| SPI-Geräte (`/dev/spidev*`) | ob überhaupt SPI aktiv ist |
| Panel-Antwort | ST7789 lässt sich auslesen; E-Paper nicht zuverlässig |
| Einstellung | letzte Instanz, wenn nichts eindeutig ist |

**Nicht alles ist erkennbar.** Ein E-Paper meldet sich nicht von selbst —
die mono- und die B-Variante sind elektrisch gleich. Dafür bleibt die
Einstellung, und die Erkennung schlägt vor, statt zu raten (Regel 10g).

Bei mehrdeutigem Befund: melden, Vorschlag nennen, Einstellung verlangen.
Nicht das nächstbeste Profil nehmen — ein falscher Treiber auf einem
E-Paper kann das Panel beschädigen.

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

---

## 7. Offen

- Der reduzierte Renderer für 1-Bit-Panels ist **Entwurf, kein Code**.
  Dass Noisys Renderer sich dafür abspecken lässt, ist plausibel, aber
  ungeprüft.
- Ob die Bildrate auf dem GamePi13 (240×240) identisch zur Whisplay ist,
  muss gemessen werden.
- Ob sich die E-Paper-Varianten zuverlässig unterscheiden lassen, ist
  offen — vorerst über die Einstellung.
