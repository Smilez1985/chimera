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
- [ ] Hardware-Revision der vorhandenen Whisplay prüfen (**V2?**)

---

## Phase 1 — Mood-Schema und Validator

**Ohne Hardware testbar.** Kern der neuen Idee, deshalb zuerst.

- [ ] Kanonische Feldtabelle: Slot, Feld, Typ, Min/Max bzw. Enum-Werte
- [ ] Schema-Generator für den Agenten *aus derselben Tabelle*
      (Architekturregel 2 — keine zweite Liste)
- [ ] Validator mit Clamping; unbekannte Keys verwerfen
- [ ] Fallback-Mood
- [ ] Mood-Registry mit dynamischer ID-Vergabe
- [ ] Felder `origin`, `created_at`, `last_used`
- [ ] Noisys 41 Moods als Startbestand importieren, `labels`/`fingerprint`/
      `energy` abstreifen
- [ ] Tests inkl. Gegenprobe: absurde Werte müssen geklemmt werden

## Phase 2 — Mischen und Variieren

**Ohne Hardware testbar.**

- [ ] `mix(a, b, gewicht)` — HSV für Farben, gewichtetes Mittel für Zahlen,
      Gewichtsentscheid bei Enums
- [ ] `vary(mood, seed)` — begrenztes Rauschen
- [ ] Offline-Renderziel: Mood → PNG in eine Datei, zum Ansehen
- [ ] Kontaktbogen: alle Startmoods plus Mischungen als Bildübersicht

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

## Phase 5 — Sprache

Einzeln nachrüstbar, in dieser Reihenfolge.

- [ ] sherpa-onnx auf der Zielhardware, Modelle laden
- [ ] VAD (`silero_vad_v5`)
- [ ] STT (`nemo-fast-conformer-ctc-en-de-es-fr-int8`), Latenz messen
- [ ] TTS (`thorsten_emotional-medium-int8`)
- [ ] TTS-Emotion an Mood koppeln (Architekturregel 4)
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

## Phase 8 — Installer und erstes Release

- [ ] Idempotenter Installer mit Migrationsfunktion (Architekturregel 10)
- [ ] `VERSION` ins System stempeln, `chimera --version`
- [ ] `*.example`-Konfigvorlagen, Secret-Scan vor Push
- [ ] CI: Tests der hardwarefreien Teile
- [ ] **Erst nach Hardware-Test:** `v0.1.0` taggen

---

## Offen / zu entscheiden

- **Zielboard:** Zero 2 W mit remote-LLM oder Pi 5 autark? Entscheidet
  über Architekturregel 5. Hängt daran, welcher Pi unter der Whisplay sitzt.
- **Mood-Aufräumen:** Wenn der Agent dauerhaft speichern darf, wächst die
  Bibliothek unbegrenzt. LRU über `last_used`? Obergrenze?
- **Bleibt Telegram** die Hauptschnittstelle, wenn Mikrofon, Lautsprecher
  und Button da sind?
- **Wake-Word oder Button** als Gesprächsauslöser (siehe Phase 5).
