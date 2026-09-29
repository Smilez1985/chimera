# Chimera — Hardware

Zielplattform, Einschränkungen und der Stand zur Boardfrage.

Stand: 2026-09-29.

---

## 1. Entscheidung

**Zielplattform ist der Raspberry Pi Zero 2 W** mit Whisplay HAT (V2).

Das ist eine Entscheidung aus Notwendigkeit, nicht aus Vorliebe: Auf dem
Radxa Zero 3W wäre mehr Luft, aber der Audiotreiber läuft dort unter
DietPi nicht (§3). Bis das gelöst ist, ist der Zero 2 W die Plattform,
auf der alles funktioniert.

### Folgen für die Architektur

512 MB RAM sind der harte Rahmen. Nach Architekturregel 5 in
`DESIGN.md` heißt das: **Sprache läuft lokal, das Sprachmodell nicht.**

    OS + Python ~120 · Renderer ~60 · STT ~150 · TTS ~60
    VAD + KWS ~25 · Agent + Telegram ~80  =  ~495 MB

Das Sprachmodell fehlt darin vollständig. Es läuft auf dem Ollama-Server
im eigenen Netz. "Ohne API" bleibt erfüllt: kein Fremdanbieter, kein
Token-Konto, nichts verlässt das Netz.

Zwei Konsequenzen, die man im Auge behalten muss:

- **Modellrotation** wird wahrscheinlich nötig: STT und TTS nicht
  gleichzeitig geladen halten. Kostet 1–3 s Umschaltlatenz, spart ~60 MB.
  Erst messen, dann bauen.
- **Kein Swap auf SD-Karte.** Bei laufendem Renderer bedeutet das Ruckeln
  und eine Karte, die nach Wochen stirbt.

---

## 2. Whisplay HAT

- LCD 240×280, ST7789-kompatibel, SPI bis 100 MHz auf dem Pi
- WM8960 bzw. ES8389 Codec, Mikrofon und Lautsprecher onboard
- 1 Button, RGB-LED
- Python-API: `runtime/whisplay.py` aus
  [PiSugar/Whisplay](https://github.com/PiSugar/Whisplay)

**Nur Revision V2 verwenden.** Auf V1 führt die Button-Leitung 5 V; ein
Tastendruck kann das Board stromlos schalten. Herstellerwarnung im
Whisplay-README.

---

## 3. Radxa Zero 3W — warum es (noch) nicht geht

### Der Wunsch

Der Radxa Zero 3W (RK3568, bis 8 GB RAM) wäre das bessere Board: Mit
genug Speicher könnte das Sprachmodell lokal laufen und Architekturregel 5
entfallen. Der Whisplay-HAT ist dafür grundsätzlich vorbereitet — es gibt
eine fertige Gerätebaum-Beschreibung
(`dts/whisplay-soundcard-radxa-zero3w.dts`) und einen eigenen
Installationspfad im Treiberpaket.

### Der Befund

Der Audiotreiber läuft unter **DietPi** nicht, weil das Modul im dortigen
Kernel fehlt.

Wichtig für die weitere Suche: **Der Treiber ist gar nicht Teil des
Kernels, sondern ein Out-of-Tree-Modul.** Das Makefile baut
`snd-soc-whisplay-soundcard.ko` gegen
`/lib/modules/$(uname -r)/build`. Die Aussage "fehlt im Kernel" ist also
keine Sackgasse — das Modul muss nicht im Kernel sein, es muss *gebaut
werden können*. Dafür braucht es:

1. **Kernel-Headers passend zur laufenden Kernelversion.**
   Der Installer versucht `linux-headers-$(uname -r)` per apt. Auf DietPi
   mit Radxas Vendor-Kernel gibt es dieses Paket in der Regel nicht —
   das ist der wahrscheinliche Bruchpunkt.
2. **`snd-soc-wm8960` aus dem Kernel.** Das Whisplay-Modul setzt den
   eingebauten WM8960-Codec-Treiber voraus und ergänzt ihn nur. Fehlt der
   im DietPi-Kernel, fehlt die Grundlage.
3. **Gerätebaum-Overlay** nach `/boot/dtbo`, plus Abschalten der
   kollidierenden Overlays `rk3568-i2s3-m0` und `wm8960-radxa-zero3`.
4. **`u-boot-update`** zum Schreiben von `/boot/extlinux/extlinux.conf`.

Punkt 3 und 4 sind DietPi-spezifisch heikel: Der Installer erwartet
Radxas eigene Verzeichnisstruktur (`/boot/dtbo`, `extlinux.conf`,
`rsetup`). DietPi legt das anders ab.

### Was der Hersteller selbst tut — und was es verrät

Für den Orange Pi Zero 3W steht im Treiberpaket ein aufschlussreicher
Hinweis: Dort fehlen im offiziellen Abbild ebenfalls die Kernel-Headers.
Die Lösung ist, ein passendes Headers-Paket **von außen** zu laden, in ein
privates Verzeichnis zu entpacken, die ARM64-Header neu zu erzeugen,
`fixdep` und `modpost` selbst zu bauen und dann gegen die
`/boot/config-*` des Boards zu konfigurieren. Sogar `wm8960.c` liegt als
GPL-2.0-Kopie im Repo, weil das Headers-Paket nicht alles mitbringt.

Das heißt: **Der Hersteller hat dieses Problem für ein anderes Board
schon gelöst — mit ziemlich viel Aufwand.** Derselbe Weg wäre für DietPi
auf dem Radxa denkbar, ist aber ein eigenes Projekt und kein Nebenbei.

### Realistische Wege, in der Reihenfolge des Aufwands

1. **Radxas offizielles Debian statt DietPi.** Dort greift der
   unterstützte Installationspfad, inklusive `/boot/dtbo` und
   `u-boot-update`. Kostet DietPis Schlankheit — bei 8 GB RAM aber ein
   Preis, der nicht weh tut. *Der mit Abstand aussichtsreichste Weg.*
2. **Headers für den DietPi-Kernel beschaffen** und das Modul direkt
   bauen. Steht und fällt damit, ob es ein passendes Headers-Paket zur
   exakten Kernelversion gibt und ob `snd-soc-wm8960` vorhanden ist.
   Beides vorab prüfbar:

       uname -r
       ls /lib/modules/$(uname -r)/build
       modinfo snd-soc-wm8960

3. **Orange-Pi-Verfahren auf Radxa übertragen** — privates
   Headers-Verzeichnis, Hostwerkzeuge selbst bauen. Machbar, aber
   erheblicher Aufwand und bei jedem Kernelupdate erneut.

### Wie Chimera damit umgeht

Das Board ist eine **Konfigurationsfrage, keine Architekturfrage.**
Konkret:

- Keine Annahme über die RAM-Größe im Code. Ob das Sprachmodell lokal
  oder remote liegt, ist eine Einstellung — Architekturregel 5a (Registry
  für Anbieter) macht genau das möglich.
- Display- und Audiozugriff laufen über die Whisplay-API, die selbst
  mehrere Plattformen erkennt. Nichts davon ist Pi-spezifisch verdrahtet.
- Auflösungsrelativer Renderer (Regel 6) — ein Boardwechsel ändert daran
  nichts.

Wird der Radxa später nutzbar, kostet der Umzug eine Konfigurationsdatei
und keinen Umbau. Das ist der Grund, es so zu bauen.

---

## 4. Vor dem ersten Start prüfen

- [ ] Whisplay-Revision: **V2?** Wenn nicht aufgedruckt, vor dem ersten
      Tastendruck klären
- [ ] `uname -r` und `ls /lib/modules/$(uname -r)/build` notieren
- [ ] `modinfo snd-soc-wm8960` — vorhanden?
- [ ] Audioaufnahme und -ausgabe mit `example/test.py` prüfen, bevor
      irgendetwas gebaut wird
- [ ] Freien Speicher unter Last messen (`free -m` mit laufendem Renderer)
