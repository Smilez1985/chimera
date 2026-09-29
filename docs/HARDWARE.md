# Chimera — Hardware

Zielplattform, Einschränkungen und der Stand zur Boardfrage.

Stand: 2026-09-29.

---

## 1. Entscheidung

**Chimera unterstützt zwei Boards: Raspberry Pi Zero 2 W und Radxa Zero 3W**,
jeweils mit Whisplay HAT (V2) und **DietPi** als Betriebssystem. Der
Installer erkennt das Board selbst (`docs/INSTALLER.md` §2a).

Chimera ist **headless** — kein Desktop, keine grafische Oberfläche.
Höchstens eine schlanke Web-Oberfläche für Einstellungen (§3).

**Entwickelt wird zuerst auf dem Pi Zero 2 W**, portiert wird danach auf
den Radxa. Nicht weil der Pi das bessere Board wäre — der Radxa hat bis zu
8 GB und könnte das Sprachmodell lokal fahren —, sondern weil auf dem Pi
alles funktioniert, während der Radxa unter DietPi erst einen
Treiber-Bootstrap braucht (§3).

Die Reihenfolge ist bewusst: Erst ein Gerät, das nachweislich läuft, dann
die schwierige Plattform. Andernfalls debuggt man den Modulbau gegen eine
Baustelle und weiß bei jedem Fehler nicht, ob es der Treiber oder der
eigene Code war.

Damit die Portierung billig bleibt, steht alles Boardabhängige in **einer
Profiltabelle** — der Radxa-Eintrag existiert von Anfang an und meldet
zunächst „noch nicht unterstützt".

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

## 3. Radxa Zero 3W

### Der Wunsch

Der Radxa Zero 3W (RK3568, bis 8 GB RAM) wäre das bessere Board: Mit
genug Speicher könnte das Sprachmodell lokal laufen und Architekturregel 5
entfallen. Der Whisplay-HAT ist dafür grundsätzlich vorbereitet — es gibt
eine fertige Gerätebaum-Beschreibung
(`dts/whisplay-soundcard-radxa-zero3w.dts`) und einen eigenen
Installationspfad im Treiberpaket.

### Betriebssystem: DietPi

**DietPi ist das Betriebssystem der Wahl — auf beiden Boards.**

Chimera ist **headless**. Es gibt einen 240×280-Bildschirm, der ein Gesicht
zeigt, und zwei Bedienwege (Telegram, Sprache). Ein Desktop hat darin keine
Aufgabe. Wenn später Einstellungen im Browser einstellbar sein sollen, wird
das eine schlanke Web-Oberfläche — kein X-Server.

Das ist auf dem Radxa Zero 3W kein Geschmacksurteil: Radxas offizielle
Abbilder gibt es als KDE- und XFCE-Varianten, und ein Desktop auf diesem
Board frisst die Reserven, die eigentlich das Sprachmodell tragen sollen.
Ein GUI-Abbild einzurichten, um dann den Desktop abzuschalten, ist der
Umweg — DietPi startet dort, wo man hinwill.

Zur Vollständigkeit: Radxa bietet auch `cli`-Abbilder ohne Desktop an
(Debian Bullseye, Ubuntu Jammy). Die bleiben als Ausweichpfad im
Boardprofil vorgesehen, falls sich unter DietPi etwas als unlösbar erweist.

### Der Befund zum Audiotreiber

Der Whisplay-Audiotreiber ist **kein Kernel-Bestandteil, sondern ein
Out-of-Tree-Modul.** Das Makefile baut `snd-soc-whisplay-soundcard.ko`
gegen `/lib/modules/$(uname -r)/build`. „Fehlt im Kernel" heißt also nicht
„unmöglich", sondern: es braucht Kernel-Headers zur laufenden Version.

Voraussetzungen im Einzelnen:

1. **Kernel-Headers passend zur laufenden Version** — der wahrscheinliche
   Bruchpunkt
2. **`snd-soc-wm8960` aus dem Kernel.** Das Whisplay-Modul setzt den
   eingebauten WM8960-Codec voraus und ergänzt ihn nur
3. **Gerätebaum-Overlay** nach `/boot/dtbo`, plus Abschalten der
   kollidierenden `rk3568-i2s3-m0` und `wm8960-radxa-zero3`
4. **Bootkonfiguration** — der Hersteller-Installer ruft `u-boot-update`
   auf und erwartet `/boot/extlinux/extlinux.conf`

### Warum DietPi die Header-Frage entschärft

Hier liegt der Grund, warum DietPi nicht der schwierigere, sondern der
gangbarere Weg ist:

**DietPi baut für den Radxa ZERO 3 keinen eigenen Kernel, sondern nutzt
Armbians `rockchip64`-Familie.** Im DietPi-Abbildbau ist das Board mit
`root_size='rockchip64'` geführt.

Und im Armbian-Paketindex existieren genau die passenden Pakete:

    linux-image-current-rockchip64
    linux-headers-current-rockchip64
    linux-image-edge-rockchip64
    linux-headers-edge-rockchip64

Damit ist **Header-Stufe 2 erreichbar, ohne das Orange-Pi-Verfahren
nachzubauen**: Armbians Repository einbinden oder das passende
`linux-headers-…-rockchip64`-Paket zur installierten Kernelversion laden.
Die Kernelversion des Headers-Pakets muss exakt zur laufenden passen —
genau dafür gibt es die Tabelle bekannter Kombinationen
(`docs/INSTALLER.md` §3.4).

Stufe 3 (Header aufbereiten, `fixdep` und `modpost` selbst bauen) bleibt
als Rückfallebene beschrieben, ist aber vermutlich **nicht nötig**. Das ist
vor dem Bauen zu prüfen, nicht anzunehmen:

    uname -r
    ls /lib/modules/$(uname -r)/build
    modinfo snd-soc-wm8960
    dpkg -l | grep -E 'linux-(image|headers|dtb)'

Punkt 3 und 4 aus dem Befund bleiben trotzdem zu lösen — DietPi legt die
Bootkonfiguration anders ab als Radxas Abbild. Das ist Aufgabe von
Installermodul 60 (Bootmethode erkennen statt voraussetzen).

### Was der Hersteller für ein anderes Board tut

Für den Orange Pi Zero 3W fehlen im offiziellen Abbild ebenfalls die
Header. PiSugars Lösung dort: Headers-Paket von außen laden, in ein
privates Verzeichnis entpacken, ARM64-Header neu erzeugen, `fixdep` und
`modpost` selbst bauen, gegen `/boot/config-*` synchronisieren. Sogar
`wm8960.c` liegt als GPL-2.0-Kopie im Repo.

Das ist das Vorbild für Stufe 3 — und der Beleg, dass der Weg gangbar ist,
falls Stufe 2 auf dem Radxa doch nicht trägt.

### Wie Chimera damit umgeht

Das Board ist eine **Konfigurationsfrage, keine Architekturfrage.**
Die Treiberfrage löst der Installer (Phase 8e), nicht der Nutzer.
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
