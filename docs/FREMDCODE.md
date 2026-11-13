# Fremdcode-Prüfung: aiavatar-pi, rpi-permission-gate

Zwei Bibliotheken wurden am 13.11.2026 auf Brauchbarkeit geprüft, bevor jemand
Zeit hineinsteckt. Die vollständigen Berichte liegen in der Recherche-Ablage
außerhalb des Repos (aus dem Gerät erzeugt, mit Quellen und Abrufdatum); hier
steht nur, was für Entscheidungen zählt.

## aiavatar-pi (`uezo/aiavatar-pi`, Apache-2.0, v0.1.3)

**Was es ist:** ein fertiges *Client-Programm* — verbindet sich per WebSocket
mit einem AIAvatarKit-Server und zeichnet einen sprechenden Avatar mit
Lip-Sync. Gebaut für **genau unser Panel** (Pi Zero 2 W + Whisplay HAT:
`ST7789(height=280, y_offset=20)`, GPIO-Pin 11, RGB565 über `spidev`).

**Warum es nicht als Ganzes geht:**
- Es **besitzt** Mikrofon, Lautsprecher und Display exklusiv (eigener
  `asyncio`-Prozess). Neben unserem Dienst ist es nicht zu betreiben.
- Es braucht einen **AIAvatarKit-Server** (VAD, STT, LLM, TTS) — den haben wir
  als Gateway schon, und ihn durch ein Fremdprotokoll zu ersetzen wäre Umbau,
  nicht Zusatz.
- Der reizvollste Modus (Video-Avatar) scheitert am Panel: unser `show`
  braucht gemessen 29,4 ms (SPI), Video will 24 fps.

**Was wir nehmen:** `aiavatar_pi/lipsync.py` (246 Zeilen, keine Abhängigkeiten)
plus die RMS-/Spektralcentroid-Berechnung aus `display/base.py`.
Fünf Mundformen (`closed/half/open/u/e`), selbst nachjustierende Schwellen
(Perzentile über 10-s-Fenster), Vokalwechsel nur an Envelope-Peaks mit 0,12 s
Mindestabstand. Dazu als Idee: Blinzeln nur wenn untätig und Gesicht neutral.
Apache-2.0 ⇒ Lizenztext beilegen, Herkunft im Dateikopf nennen (es ist selbst
ein Port von `lipsync.js` aus AIAvatarKit).

## rpi-permission-gate (`pi-rust/rpi-package`, MIT, v0.1.5)

**Der Name führt in die Irre:** `rpi` ist ein **Rust-Agent**, nicht Raspberry
Pi. Das Paket vergibt **keine** Systemrechte (kein GPIO, SPI, ALSA, kein sudo,
keine polkit-/udev-Regeln). Es hängt sich als In-Process-Plugin vor die
Werkzeugaufrufe `bash`/`write`/`edit`/`background` und fragt im Dialog
„erlauben?" — Ablehnung blockiert, fehlende Antwort blockiert auch
(fail-closed). Einschaltbar per Flag, mit `--bypass` global abschaltbar.

**Für uns nicht brauchbar:** Es legt die Entscheidung über Ausführung in den
**netzberechtigten** Prozess — genau die Trennung, die chimera zieht
(Gateway hat Netz, Ausführer führt aus). Kein Code zu übernehmen.

**Was als Konzept bleibt:** „keine Antwort ⇒ blockieren" (haben wir: „das
Gateway ist nicht erreichbar" sperrt) und „deny-first, dann Allow-Liste, sonst
verboten" als Formulierung für die Freigabetabelle.
