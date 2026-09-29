# Chimera — Roadmap

Was noch fehlt, nach Priorität. Entscheidungen und Begründungen stehen in
`docs/DESIGN.md`, nicht hier.

Stand: 2026-09-29. Pre-Alpha.

---

## Phase 0 — Blaupause ✅ (läuft)

- [x] `docs/DESIGN.md` — Architektur, Regeln, Grenzen
- [x] `docs/ROADMAP.md`
- [x] `CHANGELOG.md` mit `[Unreleased]`
- [x] `README.md`, `LICENSE`, `VERSION`
- [x] `docs/HARDWARE.md` — Zielplattform und Boardfrage
- [ ] Hardware-Revision der vorhandenen Whisplay prüfen (**V2?**)
- [ ] `uname -r`, `/lib/modules/$(uname -r)/build`, `modinfo snd-soc-wm8960`
      auf dem Zielgerät notieren (Checkliste in `docs/HARDWARE.md` §4)

---

## Phase 1 — Mood-Schema und Validator

**Ohne Hardware testbar.** Kern der neuen Idee, deshalb zuerst.

- [x] Kanonische Feldtabelle (`src/chimera/mood/schema.py`)
- [x] Schema für den Agenten *aus derselben Tabelle* (`describe_for_llm`)
- [x] Validator: zurechtstutzen statt ablehnen, unbekannte Felder verwerfen
- [x] Rückfall-Mood
- [x] Registry mit dynamischer Nummernvergabe, Ablage als JSON
- [x] Herkunft, Anlage- und Nutzungszeit; Aufräumen nach Gebrauch
- [x] **Freie Zeichenformen** (`draw.py`) — 11 Grundformen, Regel 1a
- [x] Noisys 41 Moods als Startbestand (`tools/import-noisy-moods.py`)
- [x] 68 Tests mit Gegenproben

## Phase 2 — Mischen und Variieren

**Ohne Hardware testbar.**

- [x] `mix(a, b, gewicht)` — Farbton statt Kanäle, Listen werden vereinigt
- [x] `vary(mood, seed)` — gleicher Anlass, gleiches Ergebnis
- [ ] Offline-Renderziel: Mood → PNG in eine Datei, zum Ansehen
      (**nächster Schritt** — beantwortet, ob generierte Ausdrücke taugen)
- [ ] Kontaktbogen: alle Startmoods plus Mischungen als Bildübersicht
- [ ] `MAX_SHAPES` auf echter Hardware messen

## Phase 3 — Display und Renderer

Hardware ist vorhanden, also nicht blockiert.

- [ ] Display-Adapter: `PIL.Image` → RGB565 → `board.draw_image()`
- [ ] Renderer neu, **auflösungsrelativ** (Architekturregel 6)
- [ ] Komponenten-Pipeline in fester Zeichenreihenfolge
- [ ] Blink-Engine, Nachlauf-Effekte, Software-Dimming
- [ ] Mood-Übergangsglättung
- [ ] Statuszeile in den 40 zusätzlichen Zeilen
- [ ] Framerate auf Zielhardware messen

## Phase 4 — Agent-Kopplung

- [ ] openclawgotchi-Basis übernehmen (Skills, Memory, LLM, Telegram)
- [ ] Alten Display-Layer entfernen (Architekturregel 7)
- [ ] Renderer als Dauer-Thread, Zustandsübergabe über Shared Memory
- [ ] `skills/mood/SKILL.md` (Architekturregel 8)
- [ ] Agent-Zustände auf Moods abbilden (denkt, spricht, hört zu)

### E-Ink-Ausgabe auf Whisplay umbiegen

Die Steuerbefehle bleiben, nur das Ziel wechselt (`docs/DESIGN.md` §6).

- [ ] `FACE:` auf Mood-Datensätze statt Emoticons legen; generierte Moods
      zulassen
- [ ] `DISPLAY:` auf die Statuszeile legen
- [ ] `SAY:` auf Sprechblase **und** Sprachausgabe legen
- [ ] Ghosting-Behandlung und Vollbild-Auffrischung ersatzlos entfernen
- [ ] Die 10 alten Emoticon-Moods als Startbestand abbilden, damit
      bestehende Skills unverändert laufen

## Phase 4b — Provider-Schicht

Kann parallel zu Phase 4 laufen; berührt den Renderer nicht.

- [ ] Router auf **Registry** umbauen (Architekturregel 5a) — geordnete
      Liste statt fester Attribute `self.claude` / `self.litellm`
- [ ] `LLMConnector` um `supports_tools` und `context_window` erweitern
- [ ] **Anthropic-Connector mit Abo-Anmeldung** nach dem Muster von
      OpenMinis PR #407 (Architekturregel 5b)
- [ ] Client-Kennung **zur Laufzeit ermitteln**, nie einkompilieren;
      Rückfallwert und Cache, Auffrischung bei Prozessstart
- [ ] Test: veraltete Kennung muss erkannt werden (mit Gegenprobe)
- [ ] **Ollama als eigenständiger Connector** (Architekturregel 5c), nicht
      als LiteLLM-Sonderfall
- [ ] LiteLLM-Connector aus openclawgotchi übernehmen (weitere Anbieter)
- [ ] Aufgabenzuordnung konfigurierbar: Gespräch → Anthropic,
      Mood-Erfindung und Zusammenfassen → Ollama
- [ ] Aus dem eigenen Fork übernehmen (Ideen, nicht Code —
      `docs/DESIGN.md` §4a): `/model`-Befehl zum Umschalten im Chat,
      **persistente Modellwahl** über Neustarts, Platzhalter-Adresse als
      „nicht gesetzt" behandeln statt Verbindungsfehler, Installer fragt
      die Ollama-Adresse ab
- [ ] Fehlender Schlüssel ⇒ Connector meldet sich als nicht verfügbar,
      kein Startabbruch
- [ ] `.env.example` mit Platzhaltern für alle Anbieter

## Phase 4c — Telegram erhalten

- [ ] Telegram-Bot aus openclawgotchi unverändert übernehmen
- [ ] **Gemeinsamer Verlauf** für Telegram und Sprache
      (Architekturregel 5d) — keine getrennten Sitzungen je Kanal
- [ ] Kanal als Kontext an den Agenten geben (Antwortlänge: gesprochen
      kürzer als geschrieben)
- [ ] Avatar zeigt auch bei Telegram-Anfragen den Agentenzustand

## Phase 5a — Umgebungshören im Ruhezustand

Setzt Phase 5 voraus (Audioaufnahme läuft bereits). Details in
`docs/DESIGN.md` §3.4.

- [ ] Tagger-Schicht, die Zipformer und CED gleich aussehen lässt —
      sherpa-onnx spricht beide unterschiedlich an. Das Modell ist eine
      Einstellung, kein Architekturmerkmal
- [ ] Voreinstellung CED-tiny (5,9 MB, 0,83 s gegen 4,71 s auf dem
      Pi Zero 2 W, laut Noisys Messung)
- [ ] Schwellenfaktor je Modell: CED liefert flachere Wahrscheinlichkeiten
- [ ] Ebene 1: kleine Reflextabelle für Sofortreaktionen (Knall, Lachen),
      ohne Modell, unter 1 s
- [ ] Ebene 2: Stimmungslage aus den letzten Minuten, lokal über Mischen
      und Variieren
- [ ] Ebene 3: Lagebeschreibung an das Sprachmodell, Antwort ist ein
      Mood-Name, eine Mischanweisung oder ein neuer Mood
- [ ] **Nur im Ruhezustand** hören; Wake-Word oder Taste beendet es
      (Regel 3b)
- [ ] Anfragen begrenzen (Mindestabstand, Auslösung bei deutlicher
      Änderung) — das Modell wird pro Situation befragt, nicht pro Geräusch
- [ ] Netzausfall: Ebene 1 und 2 laufen weiter, Zustand wird angezeigt
- [ ] **Auf Hardware messen:** Bildrate des Renderers mit laufendem
      Tagging; falls zu teuer, Taktrate senken

## Phase 5 — Sprache

Einzeln nachrüstbar, in dieser Reihenfolge.

- [ ] sherpa-onnx auf der Zielhardware, Modelle laden
- [ ] VAD (`silero_vad_v5`)
- [ ] STT (`nemo-fast-conformer-ctc-en-de-es-fr-int8`), Latenz messen
- [ ] TTS (`thorsten_emotional-medium-int8`)
- [ ] TTS-Emotion an Mood koppeln (Architekturregel 4b)

### Mienenspiel beim Sprechen (`docs/DESIGN.md` §4.1)
- [ ] Mundform folgt der Lautstärke der Sprachausgabe, jedes Bild
- [ ] Kopfbewegung und Pausen aus dem Sprachsignal, ~100 ms
- [ ] Sprachmodell liefert **Regieanweisung zum Satz** (Mood-Name oder
      Mischung), keine Einzelbilder — Latenz macht alles andere unmöglich
- [ ] **Messen:** hält der Renderer 15 Bilder/s, während gesprochen wird?
- [ ] Falls nicht: Bildrate beim Sprechen senken, aufwendige Ebenen
      aussetzen, Sprachausgabe stückweise erzeugen
- [ ] Wake-Word prüfen — die KWS-Modelle sind nicht auf deutschem Material
      trainiert. Wenn "Hey Chimera" unzuverlässig ist: eigenes Keyword
      trainieren oder Button als Auslöser
- [ ] Speicherverbrauch gegen Architekturregel 5 nachmessen
- [ ] Falls nötig: Modellrotation (STT und TTS nie gleichzeitig geladen)

## Phase 6 — Agent-Härtung

Vier unabhängige Bausteine, ~300 Zeilen. Berührt eine andere Ecke als
Phase 1–5, also parallel machbar. Details in `docs/DESIGN.md` §8.

- [ ] Tool-Schleifen-Erkennung + Gegenprobe-Test
- [ ] Tool-Preflight und JSON-Reparatur
- [ ] Gestaffelte Kontextschwellen; Kapazität gegen das *tatsächlich
      bedienende* Modell prüfen
- [ ] Rangordnung im Gedächtnis (read-only vs. agentgeschrieben)
- [ ] Schleifen- und Kontextzustand auf Moods/LED abbilden

## Phase 7 — Restliche Peripherie

- [ ] RGB-LED an Mood-Glow
- [ ] Button: Gesten (kurz / lang / mehrfach)
- [ ] Lautsprecher-Routing, Lautstärkeverwaltung
- [ ] PiSugar-Akkustand als Mood-Eingang
- [ ] Thermal-Hack neu kalibrieren (Agent-Grundlast einrechnen)

## Phase 8 — Installer

Entwurf steht in `docs/INSTALLER.md`. Der Installer traegt die
Plattformfrage, deshalb eigene Phase und nicht am Ende angehaengt.

### 8a — Geruest
- [x] `installer/lib/common.sh` — Ausgabe, Systemabfragen über `CHIMERA_ROOT`
- [x] Atomares Schreiben: Sidecar neben dem Ziel, dann `mv`
- [x] **`mktemp` geprueft** — ungeprueft leert es Zieldateien (I3)
- [x] **Leere Eingabe wird abgelehnt** (Regel 8a: stiller Erfolg). Gefunden
      durch den eigenen Test, nicht durch Nachdenken
- [x] `chimera-install` als Einstieg, Module nach Nummer, `--only`, `--list`
- [x] **Protokolldatei je Lauf, auch bei Erfolg** (Regel 10e)
- [ ] `--dry-run` und `--check` in den Modulen tatsaechlich auswerten
      (werden bisher nur durchgereicht)
- [ ] Protokolle aufraeumen (Anzahl oder Alter begrenzen)
- [ ] `VERSION` ins System stempeln, `chimera --version`

### 8b — Modul 10 `preflight` + Boardprofile  ✅ erster Wurf steht
Liefert sofort Nutzen: klaert die offenen Fragen zum Zielgeraet.
**Von Anfang an mit beiden Boards im Blick** (`docs/INSTALLER.md` §2a) —
sonst bedeutet Portieren spaeter ein Durchsuchen aller Module.
- [x] Board und Betriebssystem **getrennt** erkennen (zwei Achsen: derselbe
      Chip unter DietPi und unter Radxa-Debian sind zwei Faelle)
- [x] Bootmethode erkennen: `config.txt` / extlinux / u-boot-Skript
- [x] Erkennung auf **konkrete `compatible`-Kennung** stuetzen, nicht auf
      `model == *"Radxa"*` — das trifft jedes Radxa-Board
- [x] **Profiltabelle** fuer alles Boardabhaengige (Header-Stufe, SPI-Bus
      und -Takt, Overlay-Quelle und -Ziel, kollidierende Overlays,
      Bootmethode, ALSA-Vorlage) — ein neues Board = ein Eintrag
- [x] Radxa-Eintrag von Anfang an vorhanden, meldet „noch nicht
      unterstuetzt" als bewussten Zustand
- [x] Unbekanntes Board ⇒ **Abbruch mit Auskunft**, kein Rateversuch.
      `--force-board` nur fuer Entwicklung, nie im Fehlertext vorgeschlagen
- [x] Whisplay-EEPROM auslesen (`/proc/device-tree/hat/`)
- [ ] **Offen, braucht Hardware:** laesst sich daraus V1 gegen V2
      unterscheiden? Bis dahin bleibt die Warnung stehen
- [x] `uname -r`, Header-Verzeichnis, `snd-soc-wm8960`, `/boot/config-*`,
      Speicher erfassen und berichten
- [ ] Warnen, wenn ungeteilte Kernelupdates aktiv sind
- [ ] Protokolldatei statt nur Ausgabe auf dem Schirm
- [x] Test ohne Hardware: erfundene `model`- und `os-release`-Inhalte in
      einem temporaeren Wurzelverzeichnis (31 Tests, mit Gegenproben)

### 8c — Module 20–70 fuer Pi Zero 2 W
Der einfache Fall: Header kommen aus dem Distributionspaket.
- [ ] Systempakete, Header (Stufe 1), Whisplay-Treiber bauen
- [ ] WM8960 pruefen: **`modprobe` versuchen**, nicht nur Existenz pruefen
      (ein vorhandenes Modul kann ABI-inkompatibel sein)
- [ ] Overlay, kollidierende **umbenennen** statt loeschen
- [ ] Bootmethode erkennen statt `u-boot-update` vorauszusetzen
- [ ] Bootdateien vorher sichern
- [ ] ALSA-Konfiguration

### 8d — Module 80–99
- [ ] Headless prüfen: kein Desktop-Paket wird nachgezogen
- [ ] **zram einrichten, 75 % des Arbeitsspeichers** (Regel 5e)
- [ ] **Auslagerungsdatei, ein Viertel des Systemdatenträgers** — auf dem
      Pi die SD, auf dem Radxa der eMMC (laeuft damit ohne SD)
- [ ] `vm.swappiness` niedrig halten; Auslagerungsmenge protokollieren
- [ ] Auf beiden Boards gleich einrichten — auch wo es nicht nötig wäre
- [ ] Python-Umgebung, Modelle laden und Pruefsummen verifizieren
- [ ] `.env` aus Vorlage, Ollama-Adresse erfragen
- [ ] systemd-Unit
- [ ] `migrate_from()` fuer Uebergaenge (I2)
- [ ] Deinstallation, die den Ausgangszustand wiederherstellt

### 8e — Radxa Zero 3W: Portierung
**Zuletzt, gegen ein bereits laufendes Chimera auf dem Pi.** Sonst
debuggt man den Modulbau gegen eine Baustelle und weiss bei jedem Fehler
nicht, ob es der Treiber oder der eigene Code war.
Wenn 8b richtig gebaut ist, ist die Portierung im Wesentlichen **ein
ausgefuellter Profileintrag plus Header-Stufe 2/3**.
Analyse in `docs/INSTALLER.md` §2a und §3.

- [ ] Radxa-Profileintrag ausfuellen (SPI3 CS0, Overlay-Ziel `/boot/dtbo`,
      kollidierende Overlays, Bootmethode je Distribution)
- [ ] Radxa-Debian **und** DietPi als getrennte OS-Faelle behandeln
- [ ] Tabelle bekannter Kombinationen (Board, Kernelversion, Quelle,
      Pruefsumme) statt einer fest verdrahteten Version
- [ ] Headers-Paket laden, Pruefsumme verifizieren
- [ ] **`dpkg-deb -x` in ein privates Verzeichnis** — niemals nach `/`
      entpacken (I5: merged-`/usr` wuerde zerstoert, dynamisch gelinkte
      Programme brechen)
- [ ] Versionskennung in `kernel.release` und `utsrelease.h` anpassen
- [ ] ARM64-Generatoreingaben ergaenzen, `cpucaps.h` und `sysreg-defs.h`
      erzeugen
- [ ] `fixdep` und `modpost` selbst bauen
- [ ] `/boot/config-<kver>` als `.config`, dann `olddefconfig` und
      `syncconfig` — sonst baut das Modul und laedt trotzdem nicht
- [ ] `modules_prepare` **nicht** aufrufen (laeuft bei Vendor-Kerneln endlos)
- [ ] `build`-Symlink setzen
- [ ] WM8960 aus Quelle bauen, falls im DietPi-Kernel nicht vorhanden
- [ ] Unbekannte Kernelversion ⇒ Abbruch mit Auskunft, kein Rateversuch

## Phase 9 — Erstes Release

- [ ] CI: Tests der hardwarefreien Teile
- [ ] Secret-Scan vor jedem Push
- [ ] **Erst nach Hardware-Test:** `v0.1.0` taggen

---

## Offen / zu entscheiden

- **Web-Oberfläche für Einstellungen** — gewünscht, aber nachrangig.
  Schlank, lokaler Port, kein Framework. Chimera muss ohne sie vollständig
  einsatzfähig bleiben (`docs/DESIGN.md` §11a). Gehört in eine eigene Phase
  nach dem ersten Release.
- **Mood-Aufräumen:** Wenn der Agent dauerhaft speichern darf, wächst die
  Bibliothek unbegrenzt. LRU über `last_used`? Obergrenze?
- **Bleibt Telegram** die Hauptschnittstelle, wenn Mikrofon, Lautsprecher
  und Button da sind?
- **Wake-Word oder Button** als Gesprächsauslöser (siehe Phase 5).
