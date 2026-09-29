# Chimera — Design

Was und warum. Tragende Entscheidungen, Architekturregeln, Grenzen.
Wer etwas ändert, das hier beschrieben ist, ändert **zuerst dieses Dokument**.

Stand: 2026-09-29. Pre-Alpha, nichts getaggt.

---

## 1. Was Chimera ist

Ein agentisches Harness auf Raspberry Pi mit Whisplay HAT. Zwei Dinge
unterscheiden es von openclawgotchi, aus dem es hervorgeht:

1. **Der Avatar wird generiert, nicht gezeichnet.** Der Agent schreibt,
   mischt und variiert seine Mood-Assets selbst.
2. **Sprachchat statt nur Text.** Vollständig offline.

Chimera ist **kein Fork** von Noisy und kein Merge. Noisy läuft
unverändert auf eigener Hardware weiter.

---

## 2. Herkunft und Lizenzgrenzen

| Quelle | Lizenz | Was übernommen wird |
|---|---|---|
| openclawgotchi | MIT | Code: Agent, Skills, Memory, LLM-Router, Telegram |
| Noisy | MIT (eigen) | Verfahren: Mood-Architektur, Render-Pipeline |
| OpenMinis | **GPL-3.0** | **Nur Muster. Kein Code.** |

### Architekturregel 1 — Die GPL-Grenze ist hart

Chimera ist MIT. OpenMinis ist GPL-3.0. GPL ist viral und in diese
Richtung nicht MIT-kompatibel.

**Es wird keine Zeile OpenMinis-Code übernommen — auch nicht übersetzt.**
Was übernommen wird, sind Lösungsmuster: Schwellwertschemata,
Staffelungslogik, Reihenfolgen. Algorithmen sind nicht schutzfähig,
Quelltext ist es. Wer hier einen Baustein ergänzt, dokumentiert ihn in §8
mit dem Hinweis "nachgebaut, nicht kopiert".

Noisy gehört uns selbst — dort ist Kopieren erlaubt. Dass der Renderer
trotzdem neu geschrieben wird, ist eine technische Entscheidung (§5).

---

## 3. Mood-Assets: das Kernkonzept

### 3.1 Warum Noisys Format taugt

Ein Mood ist ein **deklaratives Dict**: Defaults plus Overrides. Kein
Code, keine Logik, geschlossenes Vokabular mit benannten Feldern und
erkennbaren Wertebereichen. Damit ist es von einem LLM zuverlässig
erzeugbar — und weil es keine ausführbare Logik enthält, entsteht dabei
**keine Ausführungslücke**.

Slots und Felder:

| Slot | Felder |
|---|---|
| `body` | `color`, `glow` |
| `eyes` | `scale_w`, `scale_h`, `look_offset`, `droopy` |
| `mouth` | `style` (Enum), `width` |
| `hair` | `visible`, `wobble`, `color`, `color_dark`, `color_light` |
| `physics` | `headbang_*`, `bounce_*`, `sway_*`, `shake_x/y`, `toke` |
| `particles` | `type` (Enum), `rate`, `color` |
| `accessory` | `type` (Enum) |

### 3.2 Was gegenüber Noisy entfällt

Noisy leitet Moods aus Umgebungsgeräuschen ab. Chimera tut das **nicht**.
Ersatzlos gestrichen:

- `labels` — AudioSet-Label → Mood (in Noisy 41×)
- `fingerprint` — Genre-Erkennung über Label-Indizien (7×)
- `energy` — BPM-/Lautstärke-Fenster (21×)

Es bleiben `priority`, `fast_track` und alle Darstellungs-Slots.
Neu hinzu: `origin` (builtin / mixed / generated), `created_at`,
`last_used` — für Herkunft und Aufräumen.

Mood-IDs werden **dynamisch** vergeben. Noisys feste Bereiche pro Gruppe
(Emotionen 20–29 usw.) funktionieren nicht, wenn zur Laufzeit neue Moods
entstehen.

### 3.3 Drei Stufen der Erzeugung

Von billig nach teuer. Das ist bewusst so gestaffelt: Ein LLM-Call pro
Gesichtsausdruck wäre weder bezahlbar noch schnell genug.

**Stufe 1 — Mischen. Kein LLM.**
Zwei Moods interpolieren: Farben im HSV-Raum, Zahlen gewichtet gemittelt,
bei Enums gewinnt das höhere Gewicht. Deckt den Alltag ab, kostet nichts.

**Stufe 2 — Variieren. Kein LLM.**
Begrenztes Rauschen auf einen bestehenden Mood, Seed aus dem Anlass.
Verhindert, dass dasselbe Gefühl immer pixelgleich aussieht.

**Stufe 3 — Erfinden. LLM, selten.**
Nur wenn Mischen nicht reicht. Der Agent bekommt das Vokabular als
Schema und schreibt einen neuen Mood. Ergebnis wird validiert (§3.4),
persistiert und ist danach kostenlos wiederverwendbar.

### Architekturregel 2 — Ein generierter Mood wird immer validiert

Ein Mood geht direkt in den Renderer. Ohne Schranken bedeutet
`headbang_amp: 5000`, dass der Avatar das Display verlässt, und
`rate: 0.99` eine Partikelflut, die bei 15 FPS auf einem Pi Zero die
Framerate bricht.

Also: **Clamping pro Feld gegen eine kanonische Schema-Tabelle.**
Min/Max je Zahl, erlaubte Werte je Enum, RGB auf 0–255. Unbekannte Keys
werden verworfen, nicht durchgelassen. Ein Fallback-Mood greift, wenn
alles fehlschlägt.

**Dieselbe Tabelle erzeugt das Schema für den Agenten und den Validator.**
Zwei getrennte Listen driften auseinander, sobald jemand ein Feld
ergänzt. (Muster nachgebaut aus OpenMinis' `ToolPreflight`, wo genau das
dokumentiert ist.)

---

## 4. Sprache — vollständig offline

Ein Framework für alles: **sherpa-onnx**. Läuft auf Raspberry Pi, ohne
Netz, und deckt STT, TTS, VAD und Keyword-Spotting ab.

Kette:

    KWS ("Hey Chimera") → VAD → STT → Agent
      → Mood-Entscheidung → Renderer
      → TTS (Emotion aus Mood) → Lautsprecher

### Architekturregel 3 — VAD läuft vor STT, KWS vor VAD

Dauerhaft laufende Spracherkennung frisst die CPU, die der Renderer für
15 FPS braucht. Das Wake-Word hält den Ruhezustand billig, die
Sprachaktivitätserkennung begrenzt die Erkennung auf echte Äußerungen.

### Architekturregel 4 — Gesicht und Stimme tragen denselben Mood

Die Mood-Entscheidung fällt **vor** der Sprachausgabe. Ein müder Avatar
mit munterer Stimme zerstört die Illusion sofort. Die deutsche Stimme
`thorsten_emotional` hat Emotionsvarianten — die werden an den Mood
gekoppelt, nicht fest gewählt.

Modelle (int8, deutsch):

| Aufgabe | Modell | Größe |
|---|---|---|
| VAD | `silero_vad_v5` | ~2 MB |
| KWS | `kws-zipformer-gigaspeech-3.3M-mobile` | 14 MB |
| STT | `nemo-fast-conformer-ctc-en-de-es-fr-14288-int8` | 98 MB |
| TTS | `vits-piper-de_DE-thorsten_emotional-medium-int8` | 22 MB |

### Architekturregel 5 — Sprache lokal, LLM darf remote sein

Auf einem Pi Zero 2 W (512 MB) passen Sprache **und** LLM nicht
gleichzeitig in den Speicher:

    OS + Python ~120 · Renderer ~60 · STT ~150 · TTS ~60
    VAD+KWS ~25 · Agent+Telegram ~80  =  ~495 MB

Das LLM fehlt darin komplett. Swap auf SD-Karte ist keine Lösung — bei
laufendem Renderer bedeutet das Ruckeln und tote Karten.

"Ohne API" ist deshalb so definiert: **kein Fremdanbieter, kein
Token-Konto, nichts verlässt das eigene Netz.** Ein LLM auf dem eigenen
Ollama-Server erfüllt das. Sprache bleibt in jedem Fall auf dem Gerät.

Ein Pi 5 mit 8/16 GB kann alles lokal — dann entfällt diese Einschränkung.
Whisplay unterstützt beide Boards.

Bemerkenswert: PiSugars eigene Whisplay-Referenzanwendung lässt Whisper,
Piper und Ollama per Docker auf einem separaten Rechner laufen. Der
Hersteller traut der Platine die Last selbst nicht zu.

---

## 5. Renderer

### Architekturregel 6 — Keine absoluten Pixelwerte

Noisys Renderer ist auf 240×240 festgenagelt (18 Stellen mit
Pixelkonstanten, dazu Werte wie `HAIR_MAX_LAG = 7`). Whisplay ist
240×**280**.

Chimeras Renderer rechnet **ausschließlich relativ zu `WIDTH`/`HEIGHT`**.
Kein Letterboxing, keine Verzerrung. Die 40 zusätzlichen Zeilen werden
Statuszeile: Mood-Name, Akku, Agent-Zustand.

Übernommene Mechanik aus Noisy: Komponenten-Pipeline mit fester
Zeichenreihenfolge (Glow → Body → Frisur → Accessoires → Augen → Mund →
Partikel), Blink-Engine, Nachlauf-Effekte, Software-Dimming.

`AUDIO_SMOOTHING = 0.18` (bei 15 FPS ≈ 1/3 s Nachlauf) wird zur
**Mood-Übergangsglättung** umgedeutet. Chimera hat keine Audiokopplung,
braucht aber weiche Übergänge — sonst springt das Gesicht hart um.
Erprobter Wert, andere Eingangsgröße.

### Architekturregel 7 — Ein Prozess, ein Framebuffer

openclawgotchis Display-Layer startet pro Update einen `sudo`-Subprozess
mit Lock und 45 s Timeout. Bei 15 FPS wären das 15 Prozessstarts pro
Sekunde. Dieser Layer wird **ersetzt, nicht angepasst**.

Der Renderer ist ein Dauer-Thread. Zustandsübergabe vom Agenten über
Shared Memory (Muster aus Noisys `noisy_shm.py`, inklusive des dort
dokumentierten `resource_tracker`-Workarounds: Python 3.13+ `track=False`,
älter manuell abmelden und `/dev/shm` direkt entfernen).

Display-Anbindung: ein Adapter nimmt ein fertiges `PIL.Image`, wandelt
nach RGB565 und ruft `board.draw_image()`.

---

## 6. Was von openclawgotchi bleibt

Unverändert übernommen:

- `skills/loader.py` — Skill-Gating über `bins`, `any_bins`, `env`, `os`.
  Bleibt bewusst dateibasiert; OpenMinis' SQLite-SkillStore kennt kein
  Requirement-Gating und wäre hier ein Rückschritt.
- `memory/` — Vault, Knowledge, Flush
- `llm/` — Router und LiteLLM-Connector, Rate Limits
- `audit_logging/`
- Skills im Anthropic-`SKILL.md`-Format
- Telegram-Anbindung

**E-Ink entfällt.** Bewusste Entscheidung mit realem Verlust: E-Paper
bleibt ohne Strom lesbar, was für ein Gerät, das schläft, ein echter
Vorteil war. Gegenleistung: Farbe, 30–60 FPS, Mikrofon, Lautsprecher,
Button, LED auf einer Platine.

### Architekturregel 8 — Die Mood-Steuerung ist ein Skill, kein Sonderweg

Der Agent steuert sein Gesicht über `skills/mood/SKILL.md`, nicht über
einen eingebauten Spezialpfad. Damit greift das bestehende Gating, und
der Ausdruck wird mit demselben Mechanismus verwaltet wie alles andere.

---

## 7. Zustand sichtbar machen

Der verbindende Gedanke des Projekts. Interner Zustand wird Ausdruck:

| Zustand | Quelle | Ausdruck |
|---|---|---|
| hört zu | VAD/KWS | aufmerksam, LED blau |
| denkt | Agent | Partikel |
| spricht | TTS | Mund animiert, Stimmemotion = Mood |
| Tool-Schleife | LoopDetector | agitiert, LED rot |
| Kontext fast voll | ContextPolicy | müde Augen |
| CPU heiß | Thermal | müde Augen |
| Akku niedrig | PiSugar | eigener Mood |

Noisys Thermal-Hack (Müdigkeit an CPU-Temperatur) wird übernommen, aber
**neu kalibriert**: Mit Agent, STT und TTS als Dauerlast wäre der Avatar
sonst permanent müde. In Chimera ist das ein bewusster Kanal, kein
Nebeneffekt.

---

## 8. Übernommene Muster aus OpenMinis (nachgebaut, nicht kopiert)

Alle vier sind unabhängig voneinander und einzeln testbar.

1. **Tool-Schleifen-Erkennung.** Tool-Name und Argumente hashen, Fenster
   der letzten 30 Aufrufe, gestaffelte Schwellen (warnen / blockieren /
   Notbremse). Prüfung **vor** der Ausführung; die Meldung wird als
   Tool-Ergebnis eingespeist, damit das Modell erfährt, dass es feststeckt.
   Auch der Ergebnis-Hash wird verfolgt: gleiche Frage mit gleicher
   Antwort ist eine Schleife, mit anderer Antwort legitimes Polling.
   Für Chimera kritisch, weil autonome Läufe an einem bezahlten oder
   begrenzten Modell hängen.

2. **Tool-Preflight und JSON-Reparatur.** Pflichtfelder gegen die
   kanonische Schema-Liste prüfen, Strings auf nicht-leer (`{"path": ""}`
   besteht eine reine Existenzprüfung und ist trotzdem kaputt). Vor dem
   Verwerfen: abgebrochenes JSON mit fehlenden Klammern erneut parsen.

3. **Gestaffelte Kontextschwellen.** Offload- und Compact-Grenzen nach
   Fenstergröße statt fester Zahl. Kapazität wird gegen das Modell
   geprüft, das die Anfrage **wirklich bedient** — bei Router-Fallback
   sonst gegen das falsche Fenster.

4. **Rangordnung im Gedächtnis.** Dauerhafte, nutzergepflegte Notizen
   sind für den Agenten **read-only**; Tageslogs schreibt er selbst.
   Beide werden mit der Ansage injiziert, dass es Hintergrundkontext ist
   und die letzte Nutzernachricht Vorrang hat — sonst nimmt das Modell
   abgeschlossene Aufgaben wieder auf.

---

## 9. Tests

### Architekturregel 9 — Kein Test, der eine Formel nachrechnet

Ein Test, der eine Berechnung im Testcode nachbildet statt sie
aufzurufen, prüft nichts. **Jeder Regressionstest braucht eine
Gegenprobe:** alten Zustand wiederherstellen und prüfen, ob der Test rot
wird. Ist er das nicht, misst er nichts.

Konkret für die Schleifen-Erkennung: eine echte Schleife simulieren und
nachweisen, dass sie ohne Detektor durchläuft.

Phasen 1 und 2 (Schema, Validator, Mischen, Variieren) sind vollständig
**ohne Hardware** testbar — Bilder in Dateien rendern und ansehen.

---

## 10. Versionierung

### Architekturregel 10 — Ein Versionssprung bricht keine Installation

Was ein neues Release an bestehenden Installationen ändert, gehört in
eine Migrationsfunktion des Installers, nie in eine Release-Notiz "bitte
neu installieren". Ein `git pull` plus Installer-Lauf muss genügen.

- `VERSION` im Repo-Root ist die einzige Wahrheitsquelle; der Installer
  stempelt sie ins System, damit `chimera --version` ohne Repo antwortet.
- Tags sind unveränderlich. Fehler → neues Patch-Release.
- Der Changelog-Abschnitt ist die Release Notes.
- **Pre-Alpha bleibt ungetaggt.** Ein Release entsteht erst, wenn eine
  Version **auf echter Hardware getestet** ist.

---

## 11. Hardware

- Raspberry Pi Zero 2 W (512 MB) oder Pi 5
- **Whisplay HAT V2 — ausschließlich.** Auf V1 führt die Button-Leitung
  5 V; ein Tastendruck kann das Board stromlos schalten. Herstellerwarnung.
- LCD 240×280, ST7789-kompatibel, SPI bis 100 MHz
- WM8960 bzw. ES8389 Codec, Mikrofon und Lautsprecher onboard
- 1 Button, RGB-LED

Lastbetrachtung: Renderer (15 FPS) und Sprachmodelle laufen bei Noisy
bereits gemeinsam auf einem Zero 2 W; der Agent wartet überwiegend auf
I/O. Machbar, aber eng — siehe Architekturregel 5.

---

## 12. Keine Secrets im Repo

Tokens, Zugangsdaten, SSIDs, Gerätenamen und lokale Pfade gehören nicht
in die Versionsverwaltung. Konfiguration liegt als `*.example` mit
Platzhaltern vor; echte Werte erzeugt der Installer. Vor jedem Push
scannen.
