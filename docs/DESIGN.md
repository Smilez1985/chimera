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

Ein Board mit mehr Speicher könnte alles lokal fahren — siehe
`docs/HARDWARE.md` zur Boardfrage. Die Plattform ist bewusst eine
**Konfigurationsfrage, keine Architekturfrage**: ob das Sprachmodell lokal
oder im Netz liegt, entscheidet die Registry (Regel 5a), nicht der Code.

Bemerkenswert: PiSugars eigene Whisplay-Referenzanwendung lässt Whisper,
Piper und Ollama per Docker auf einem separaten Rechner laufen. Der
Hersteller traut der Platine die Last selbst nicht zu.

---

## 4a. Sprachmodelle: Provider-Schicht

Chimera soll **mehrere Anbieter gleichzeitig** kennen: Anthropic per
Abo-Anmeldung, Ollama im eigenen Netz, dazu beliebige weitere über
LiteLLM. Keiner davon ist Pflicht.

### Ausgangslage aus openclawgotchi

Die Abstraktion ist da und taugt: `LLMConnector` mit `call()` und
`is_available()`, dazu `LLMError` / `RateLimitError`. Zwei
Implementierungen existieren (Claude-CLI, LiteLLM).

Der **Router** taugt nicht. Er kennt genau zwei Connectoren als feste
Attribute und schaltet mit einem Bool (`force_lite`) zwischen ihnen um.
Ein dritter Anbieter passt da nicht hinein, ohne die Klasse aufzubohren.

### Architekturregel 5a — Registry statt fester Connector-Attribute

Der Router hält eine **geordnete Liste** von Connectoren, nicht benannte
Felder. Ein Anbieter meldet sich mit Name, Priorität und
Verfügbarkeitsprüfung an. Auswahl geschieht über den Namen, nicht über
einen Schalter; Fallback läuft die Liste entlang.

Damit kostet ein neuer Anbieter eine Datei und einen Registry-Eintrag —
keine Änderung am Router.

`LLMConnector` wird um zwei Dinge erweitert:
- `supports_tools` — nicht jeder Anbieter kann Tool-Calls
- `context_window` — nötig für die gestaffelten Kontextschwellen (§8.3).
  Die Kapazität muss gegen das Modell geprüft werden, das die Anfrage
  **tatsächlich bedient**. Bei Fallback über die Registry sonst gegen das
  falsche Fenster.

### Architekturregel 5b — Anthropic-Anmeldung wie im OpenMinis-PR

Anthropic wird auf demselben Weg eingebunden wie in
[OpenMinis PR #407](https://github.com/OpenMinis/OpenMinis/pull/407):
über den **OAuth-Pfad der Abo-Anmeldung**, nicht nur über einen
API-Schlüssel. Das erlaubt die Nutzung eines bestehenden Abos, statt pro
Token zu zahlen — auf einem Gerät, das dauernd läuft, ist das der
Unterschied zwischen benutzbar und nicht benutzbar.

Der Kern dieses PRs ist eine Lehre, die hier direkt gilt:

> Anthropic sperrt neue Modelle hinter einer Mindestversion des
> CLI-Clients und prüft das über den User-Agent. Eine **fest verdrahtete
> Versionskennung veraltet** und quittiert mit
> `claude_code_version_too_old` — für ein neues Modell, das eigentlich
> verfügbar wäre.

Also: **Die Client-Kennung wird zur Laufzeit ermittelt, nie einkompiliert.**
Ermittlung aus der real installierten CLI, mit gepflegtem Rückfallwert
und Zwischenspeicher. Genau das tut `ClaudeCliVersion` im PR.

Für Chimera heißt das zusätzlich: Wo die CLI als Unterprozess läuft,
kommt sie über den Gerätestart hinweg nicht mit. Der ermittelte Wert
gehört gecacht und bei Prozessstart einmal aufgefrischt — nicht bei jedem
Aufruf, das kostet auf einem Zero spürbar.

### Vorarbeit im eigenen Fork von openclawgotchi

Im Fork `Smilez1985/openclawgotchi`, Branch `feat/model-ollama-switcher`,
ist Ollama bereits angebunden. Fünf Commits, die inhaltlich übernommen
werden:

- `LLM_PRESETS`-Eintrag `ollama` mit `ollama_chat/<modell>` und
  `OLLAMA_API_BASE`
- `/model`-Befehl im Chat: Modelle zur Laufzeit auflisten und umschalten,
  ohne SSH
- **Auswahl bleibt über Neustarts erhalten** (`active_model.json`), mit
  Vorrang vor dem Voreinstellungs-Preset
- Platzhalter-Hostname wird als „nicht gesetzt" behandelt und mit einem
  klaren Hinweis gemeldet, statt in einen Verbindungsfehler zu laufen
- Der Installer fragt die echte Ollama-Adresse ab

Die Muster sind gut und werden übernommen — insbesondere die persistente
Modellwahl und die Behandlung des Platzhalters. **Der Code selbst wird
nicht übertragen**, weil er auf dem alten Zwei-Connector-Router aufsitzt
(`set_model()` auf dem LiteLLM-Connector). In der Registry ist Ollama ein
eigener Connector, kein umgeschalteter LiteLLM (Regel 5c).

Zum Stand des Forks: Er liegt **41 Commits hinter dem Upstream** und 5
voraus. Das Upstream-Projekt ist in der Zwischenzeit deutlich
weitergegangen. Chimera setzt daher auf dem **aktuellen Upstream** auf und
baut die Fork-Ideen dort neu ein, statt den divergierten Fork
nachzuziehen. Ein Rebase über 41 Commits mit anschließendem Umbau auf die
Registry wäre mehr Arbeit als die Neuimplementierung.

### Architekturregel 5c — Ollama ist ein erstklassiger Anbieter

Ollama läuft im eigenen Netz und ist damit der Anbieter, der Regel 5
erfüllt (nichts verlässt das Netz). Er wird **nicht** als Sonderfall von
LiteLLM behandelt, sondern als eigener Connector mit eigener
Verfügbarkeitsprüfung — sonst lässt sich nicht sauber unterscheiden, ob
der Server weg ist oder ein Schlüssel fehlt.

Die Zuordnung von Aufgabe zu Anbieter ist konfigurierbar. Sinnvolle
Voreinstellung:

| Aufgabe | Anbieter |
|---|---|
| Gespräch, Werkzeugnutzung | Anthropic (Abo), Fallback Ollama |
| Mood-Erfindung (§3.3 Stufe 3) | Ollama — selten, günstig, lokal |
| Zusammenfassen, Aufräumen | Ollama |

Mood-Erfindung auf dem lokalen Modell zu belassen, ist bewusst: Der
Ausdruck des Geräts sollte nicht an einem bezahlten Kontingent hängen.

### Konfiguration

Alle Anbieter sind optional, alle über `.env` einzurichten, keiner
hartkodiert. Fehlt ein Schlüssel, meldet der Connector sich als nicht
verfügbar und die Registry überspringt ihn — kein Absturz, keine
Fehlermeldung beim Start.

Zugangsdaten gehören nicht ins Repo (§12). `*.example` mit Platzhaltern.

---

## 4b. Schnittstellen zum Nutzer

Chimera hat **zwei gleichwertige Wege** hinein, nicht einen mit Anhängsel:

| Weg | Nutzung |
|---|---|
| **Telegram** | Von unterwegs, lange Texte, Dateien, Verlauf |
| **Sprache am Gerät** | Vor Ort, beiläufig, freihändig |

Telegram bleibt aus openclawgotchi **vollständig erhalten** — es ist die
einzige Schnittstelle, die auch funktioniert, wenn man nicht im selben
Raum steht.

### Architekturregel 5d — Ein Gespräch, zwei Türen

Beide Wege führen in **denselben Agenten mit demselben Verlauf**. Wer
morgens per Telegram etwas bespricht und abends davorsteht und nachfragt,
redet mit demselben Gegenüber. Getrennte Sitzungen je Kanal wären ein
Fehler und würden das Gerät in zwei Persönlichkeiten spalten.

Praktisch: Die Kanäle unterscheiden sich nur in Ein- und Ausgabe
(Text gegen STT/TTS) und in der Ausgabelänge — gesprochene Antworten
müssen kürzer sein als geschriebene. Der Agent bekommt den Kanal als
Kontext mitgeteilt, damit er sich darauf einstellen kann.

Der Avatar zeigt in beiden Fällen denselben Zustand (§7). Wenn per
Telegram eine Anfrage läuft, sieht man das dem Gesicht an.

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

### E-Ink wird umgebogen, nicht gestrichen

Die Anzeige verschwindet nicht — sie wechselt das Medium. Was
openclawgotchi über E-Paper ausgibt, gibt Chimera über die Whisplay aus,
mit Noisys Mechanik dahinter.

Die Übersetzung im Einzelnen:

| openclawgotchi (E-Ink) | Chimera (Whisplay) |
|---|---|
| `FACE: <mood>` steuert Emoticon aus `custom_faces.json` | steuert einen Mood-Datensatz (§3) |
| 10 feste Text-Emoticons | Mood-Bibliothek, vom Agenten erweiterbar |
| `DISPLAY: <text>` Statuszeile | Statuszeile in den 40 zusätzlichen Zeilen |
| `SAY: <msg>` Sprechblase | Sprechblase **und** Sprachausgabe (§4) |
| Vollbild-Auffrischung gegen Geisterbilder | entfällt — LCD hat kein Ghosting |
| ~2 s pro Bild, statisch | 15 FPS, animiert |

**Die Steuerbefehle bleiben erhalten.** Der Agent schreibt weiterhin
`FACE:`, `DISPLAY:`, `SAY:` — was sich ändert, ist ausschließlich das,
was dahinter passiert. Damit funktionieren bestehende Skills und der
Systemprompt unverändert weiter; `FACE:` nimmt zusätzlich die neuen,
generierten Moods entgegen.

Der reale Verlust ist die Lesbarkeit ohne Strom. Dafür: Farbe, Animation,
Mikrofon, Lautsprecher, Button und LED auf einer Platine.

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

### Architekturregel 8a — Stiller Erfolg ist die gefährlichste Fehlerart

Beim Bau von Modul 10 gefunden, durch den eigenen Test: Schreibt man eine
Datei über eine Pipe und der Erzeuger liefert **nichts**, dann schreibt
`cat` nichts, das Umbenennen gelingt, der Exitcode ist 0 — und die
Zieldatei ist **geleert**. Kein Fehler, keine Meldung, Datenverlust.

Deshalb lehnt `write_atomic` leere Eingaben ab, sofern sie nicht
ausdrücklich erlaubt werden (`CHIMERA_ALLOW_EMPTY=1`). Dieselbe
Fehlerklasse wie beim ungeprüften `mktemp`, nur mit anderem Auslöser:
**etwas scheitert weiter oben, und die Kette meldet Erfolg.**

Verallgemeinert: Wo ein Schritt ein Ergebnis liefern *soll*, wird das
Ergebnis geprüft — nicht nur der Exitcode des letzten Befehls.

### Architekturregel 9 — Kein Test, der eine Formel nachrechnet

Ein Test, der eine Berechnung im Testcode nachbildet statt sie
aufzurufen, prüft nichts. **Jeder Regressionstest braucht eine
Gegenprobe:** alten Zustand wiederherstellen und prüfen, ob der Test rot
wird. Ist er das nicht, misst er nichts.

Konkret für die Schleifen-Erkennung: eine echte Schleife simulieren und
nachweisen, dass sie ohne Detektor durchläuft.

Dass die Regel trägt, hat sich beim ersten Modul sofort gezeigt: Der Test
zum atomaren Schreiben war zunächst **falsch gebaut** — er setzte ein
kaputtes `TMPDIR`, aber `mktemp` mit explizitem Template ignoriert
`TMPDIR`. Die Gegenprobe (denselben Vorgang ohne Schutz ausführen und
nachweisen, dass die Datei *tatsächlich* geleert wird) hat den
Denkfehler aufgedeckt — und dabei einen echten Fehler im Code gefunden
(Regel 8a). Ein Test ohne Gegenprobe wäre grün geblieben und hätte nichts
gemessen.

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

## 10a. Installer

Der Installer trägt die Plattformfrage: Er löst das Beschaffen der
Kernel-Headers und das Einhängen des Overlays, nicht der Nutzer. Entwurf,
Modulaufbau und die Fallstricke stehen in `docs/INSTALLER.md`.

Sechs Grundregeln, drei davon aus bezahltem Lehrgeld: idempotent,
Versionssprung bricht keine Installation, atomar schreiben mit geprüftem
`mktemp`, nichts ungeprüft aufrufen, fremde Pakete nie über `/` entpacken,
jeder Schritt einzeln aufrufbar.

### Architekturregel 10a — Board, Betriebssystem und Bootmethode sind drei Achsen

Nicht eine Variable, sondern drei unabhängige:

    board = rpi_zero2w | radxa_zero3w | unsupported_* | unknown
    os    = dietpi | raspios | radxa_debian | armbian | debian | unknown
    boot  = config_txt | extlinux | uboot_script | unknown

Derselbe Chip unter DietPi und unter Radxas Abbild sind **zwei
Installationsfälle**, weil Overlay-Ablage und Bootkonfiguration sich
unterscheiden. Wer das in einer Variablen zusammenfasst, baut sich die
Fallunterscheidungen doppelt.

Praktischer Befund aus der Umsetzung: DietPi setzt auf Debian auf und
meldet sich in `/etc/os-release` als Debian. Die Erkennung muss daher auf
DietPi-eigene Merkmale prüfen (`/boot/dietpi.txt`) und diese **vor**
`os-release` auswerten.

### Architekturregel 10b — Erkennung stützt sich auf `compatible`, nicht auf den Klartextnamen

Der Whisplay-Installer des Herstellers erkennt den Radxa so:

    [[ "$model" == *"Radxa"* ]] && echo radxa_zero3w

Das legt **jedes** Radxa-Board auf ein Profil, das nur zum ZERO 3W passt.
Chimera prüft die konkrete Kennung aus `/proc/device-tree/compatible`
(`radxa,zero3w`, `raspberrypi,model-zero-2-w`) und benennt Verwandtes
ehrlich als `unsupported_radxa` bzw. `unsupported_rpi`.

**Unbekanntes Board bricht ab, ohne zu raten** — mit Auskunft darüber, was
erwartet und was gefunden wurde. Begründung: Ein falsches Overlay in der
Bootkonfiguration kostet bei einem Gerät ohne Bildschirm den Ausbau der
SD-Karte. Ein `--force-board` existiert für Entwicklung, wird aber nie im
Fehlertext vorgeschlagen.

### Architekturregel 10c — Alles Boardabhängige steht in einer Profiltabelle

Header-Stufe, Header-Paket, Paketquelle, SPI-Bus und -Takt,
Overlay-Quelle, kollidierende Overlays, ob der Codec im Kernel liegt, ob
ein lokales Sprachmodell realistisch ist. Ein neues Board ist ein Eintrag,
kein Durchsuchen aller Module.

Der Radxa-Eintrag existiert von Anfang an und meldet `supported=not_yet` —
ein **Zustand**, kein Platzhalter im Code. Damit ist die Portierung im
Wesentlichen ein ausgefüllter Eintrag.

Gleiche Begründung wie bei der Anbieter-Registry (Regel 5a): verteilte
Fallunterscheidungen driften auseinander.

### Architekturregel 10d — Alles Lesende geht über ein Wurzelverzeichnis

Jede Systemabfrage läuft über `CHIMERA_ROOT` (im Betrieb leer). Damit ist
die vollständige Erkennung **ohne Zielhardware** prüfbar: erfundene
`model`- und `compatible`-Dateien in einem temporären Verzeichnis, und der
Installer urteilt darüber wie über ein echtes Gerät.

Das ist kein Testkniff, sondern eine Entwurfsentscheidung. Ohne sie wäre
die Boarderkennung nur auf dem Gerät prüfbar, das man gerade nicht hat.

---

## 11. Hardware

- **Raspberry Pi Zero 2 W (512 MB)** — Entwicklungsziel
- **Radxa Zero 3W** — Portierungsziel, mehr Reserven
- **DietPi** auf beiden, headless (§11a)
Begründung und Grenzen in `docs/HARDWARE.md`.
- **Whisplay HAT V2 — ausschließlich.** Auf V1 führt die Button-Leitung
  5 V; ein Tastendruck kann das Board stromlos schalten. Herstellerwarnung.
- LCD 240×280, ST7789-kompatibel, SPI bis 100 MHz
- WM8960 bzw. ES8389 Codec, Mikrofon und Lautsprecher onboard
- 1 Button, RGB-LED

Lastbetrachtung: Renderer (15 FPS) und Sprachmodelle laufen bei Noisy
bereits gemeinsam auf einem Zero 2 W; der Agent wartet überwiegend auf
I/O. Machbar, aber eng — siehe Architekturregel 5 und `docs/HARDWARE.md`.

---

## 11a. Headless

Chimera hat **keine grafische Oberfläche.** Es gibt den 240×280-Bildschirm
mit dem Gesicht und zwei Bedienwege (Telegram, Sprache). Ein Desktop hätte
darin keine Aufgabe und würde auf beiden Zielboards Reserven verbrauchen,
die Renderer und Sprachmodelle brauchen.

**Betriebssystem ist DietPi**, auf beiden Boards — schlank und ohne
mitgeliefertes Desktop-Gepäck. Auf dem Radxa Zero 3W ist das kein
Geschmacksurteil: Radxas offizielle Abbilder sind KDE- und XFCE-Varianten,
und ein Desktop macht dieses Board für den eigentlichen Zweck unbrauchbar
langsam.

Sollen Einstellungen im Browser bearbeitbar sein, wird das eine **schlanke
Web-Oberfläche** auf einem lokalen Port — HTML und ein Formular, kein
X-Server, kein Framework-Gebirge. Sie ist Zubehör, nicht Voraussetzung:
Chimera muss ohne sie vollständig einsatzfähig sein, konfigurierbar über
`.env` und Installerfragen.

---

## 12. Keine Secrets im Repo

Tokens, Zugangsdaten, SSIDs, Gerätenamen und lokale Pfade gehören nicht
in die Versionsverwaltung. Konfiguration liegt als `*.example` mit
Platzhaltern vor; echte Werte erzeugt der Installer. Vor jedem Push
scannen.
