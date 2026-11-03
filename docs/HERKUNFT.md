# Herkunft — was übernommen wird und was nicht

Arbeitsnotizen zur Analyse von **openclawgotchi** (Upstream und eigener
Fork) und **OpenMinis**. Dieses Dokument beantwortet drei Fragen für jeden
Baustein: Was nehmen wir, was lassen wir, und in welcher Form.

Stand: 2026-09-29. Geprüft gegen `turmyshevd/openclawgotchi` (11 525
Zeilen Python), `Smilez1985/openclawgotchi` (Fork, 41 Commits hinter dem
Upstream) und `OpenMinis/OpenMinis`.

---

## 0. Die Lizenzgrenze — zuerst, weil sie alles andere bestimmt

| Projekt | Lizenz | Folge |
|---|---|---|
| openclawgotchi | **MIT** | Code darf übernommen werden |
| Noisy | **MIT** (eigen) | Code darf übernommen werden |
| Chimera | **MIT** | — |
| **OpenMinis** | **GPL-3.0** | **Kein Code. Nur Muster.** |

GPL-3 ist viral und in Richtung MIT nicht verträglich. Aus OpenMinis wird
deshalb **keine Zeile übernommen, auch nicht übersetzt**. Was übernommen
wird, sind Lösungsmuster: Schwellwertschemata, Staffelungen, Reihenfolgen.
Algorithmen sind nicht schutzfähig, Quelltext ist es.

Praktisch heißt das: lesen, verstehen, zuklappen, aus dem Verständnis neu
schreiben. Wer einen Baustein aus OpenMinis ergänzt, vermerkt ihn in §3
als *nachgebaut*.

Bei openclawgotchi ist Kopieren erlaubt. Dass wir es trotzdem nur selten
tun, ist eine technische Entscheidung (§1) — das Projekt ist für andere
Hardware und ein anderes Prozessmodell gebaut.

---

## 1. openclawgotchi

### 1.1 Was das Projekt ist

Ein agentischer Telegram-Bot für einen Pi Zero mit E-Paper-Anzeige.
11 525 Zeilen Python. Schwerpunkte: Agent-Schleife mit Werkzeugen,
Wissensspeicher, Skills, Selbstwartung.

Das Display ist dort **Nebensache** — 289 Zeilen, die per Unterprozess ein
Zeichenskript aufrufen. Bei Chimera ist es die Hauptsache. Dieser
Unterschied zieht sich durch die ganze Bewertung.

### 1.2 Übernehmen — mit Anpassung

| Baustein | Zeilen | Warum | Anpassung |
|---|---|---|---|
| `skills/loader.py` | 347 | Skill-Gating über `bins`, `any_bins`, `env`, `os` — besser als alles, was OpenMinis dafür hat | Pfade, sonst kaum |
| `llm/base.py` | 51 | Saubere Connector-Schnittstelle | um `supports_tools`, `context_window` erweitern |
| `llm/rate_limits.py` | 249 | Begrenzung ist bei externem Modell Pflicht | pro Anbieter statt global |
| `audit_logging/` | ~120 | Jede Werkzeugnutzung als JSONL | in unser Protokoll einhängen (Regel 10e) |
| `memory/vault.py` | 577 | Markdown-Wissensspeicher ohne feste Taxonomie — das Modell vergibt Projekt und Themen selbst | Ablagepfade |
| `memory/knowledge.py` | 573 | Rückruf aus dem Speicher | — |
| `cron/scheduler.py` | 276 | Zeitgesteuerte Aufgaben | — |
| `hooks/runner.py` | 172 | Erweiterungspunkte | — |
| `hardware/battery.py` | 248 | Akkustand | auf PiSugar umstellen |
| `drivers/epd2in13_V4.py`, `epdconfig.py` | 672 | **E-Paper bleibt** — Chimera unterstützt mehrere Anzeigen (Regel 6c) | aus dem **eigenen Fork**, wo mono/B bereits unterschieden wird |
| `bot/telegram.py` | ~200 | Telegram bleibt (Regel 5d) | Verlauf mit Sprache teilen |
| `gotchi-skills/*` | 10 Skills | `SKILL.md` im Anthropic-Format | als Beispiele |

**Die Sicherheitsschicht ist der stärkste Teil und wird übernommen.**
Anders als erwartet steckt sie nicht nur in Prompt-Text (`SAFETY.md`),
sondern im Code:

- `BLOCKED_EXECUTABLES` (`sudo`, `su`, `doas`)
- Verkettung, Umlenkung und Ersetzung (`|`, `>`, `` ` ``, `$(`) werden
  abgelehnt
- verschachtelte Shells blockiert
- `shell=False`, Argumente über `shlex` zerlegt
- Zeitgrenze, Ausgabegrenze, festes Arbeitsverzeichnis

Das ist ernst gemeinte Absicherung, kein Feigenblatt. Bei einem Gerät, das
mit einem externen Modell spricht und `execute_bash` anbietet, ist das die
Untergrenze.

### 1.3 Übernehmen — als Idee, neu gebaut

| Baustein | Warum nicht direkt |
|---|---|
| `llm/router.py` (82) | Kennt zwei Connectoren als feste Attribute und schaltet per Bool. Ein dritter Anbieter passt nicht hinein → **Registry** (Regel 5a) |
| `llm/litellm_connector.py` (1513) | Enthält *alles*: Werkzeuge, Ausführung, Modellwahl, Zustand. Die Werkzeugliste ist gut, die Vermischung nicht → aufteilen |
| `memory/summarize.py` (110) | Feste Grenze (`VERBATIM_COUNT = 5`) statt Staffelung nach Fenstergröße → siehe §3.3 |
| `hardware/auto_mood.py` (137) | Wählt Stimmung nach `minute % len(moods)`. In Chimera entscheidet das Modell (§3.4 im Design) |
| `harden.sh` | Gute Punkte (Watchdog, Dienste abschalten, Firewall, SSH), aber Swap mit festem Gigabyte → bei uns zram + Auslagerung (Regel 5e) |

### 1.4 Nicht übernehmen

| Baustein | Grund |
|---|---|
| `ui/gotchi_ui.py`, `ui/faces.py` (~700) | Zeichnet Text-Emoticons. Chimera hat Noisys Renderer — die reduzierte Darstellung wird daraus abgeleitet, nicht übernommen |
| `hardware/display.py` (289) | Startet je Bild einen Unterprozess mit `sudo`, Sperre und 45 s Zeitgrenze. Bei 15 Bildern je Sekunde wären das 15 Prozessstarts je Sekunde → **ersetzen, nicht anpassen** (Regel 7) |
| `data/custom_faces.json` | 10 Emoticons. Werden als Startbestand *abgebildet*, nicht übernommen |
| `bot/discord_inbound.py` (430) | Zweiter Chat-Weg. Telegram und Sprache reichen |
| `skills/devto.py` | Artikel veröffentlichen — nicht unser Zweck |
| `utils/patch_self.py` | **Ersetzt**, nicht übernommen: keine Sicherung, keine Selbstprüfung, kein Rückweg (Regel 10i) |

### 1.5 Der eigene Fork

`Smilez1985/openclawgotchi`: **0 voraus, 41 zurück** auf `main`.
Der Zweig `feat/model-ollama-switcher` ist 5 voraus und 41 zurück.

Zehn Merkmalszweige vorhanden: `model-ollama-switcher`, `bot-mcp-client`,
`bot-rag-integration`, `display-variant-detect-v2`,
`mcp-tool-auto-registration`, `model-menu-and-restore-persistence`,
`self-update`, `split-rag-rest-mcp-urls`, `time-awareness-quiet-schedule`,
`deploy/all-features`.

**Chimera setzt auf dem Upstream auf, nicht auf dem Fork.** Ein Rebase
über 41 Commits samt anschließendem Umbau auf die Registry wäre mehr
Arbeit als die Neuimplementierung.

Übernommen werden die **Ideen** aus dem Ollama-Zweig:

- Preset-Eintrag `ollama` mit `ollama_chat/<modell>` und `OLLAMA_API_BASE`
- `/model`-Befehl: Modelle zur Laufzeit auflisten und umschalten, ohne SSH
- **Auswahl überlebt Neustarts** (`active_model.json`), mit Vorrang vor
  der Voreinstellung
- **Platzhalter-Adresse wird als „nicht gesetzt" erkannt** und mit klarem
  Hinweis gemeldet, statt in einen Verbindungsfehler zu laufen — die
  eleganteste der fünf Änderungen
- Der Installer fragt die echte Adresse ab

Ebenso aus dem Fork: der Zweig **`feat/display-variant-detect-v2`**
(4 Commits). Er unterscheidet die Waveshare-Varianten mono und B und
bringt das Wissen über deren Zeitverhalten mit — Grundlage für die
Panel-Profile in `docs/DISPLAYS.md`.

Der Code dazu sitzt auf `set_model()` des LiteLLM-Connectors auf und passt
nicht in die Registry, in der Ollama ein eigener Connector ist (Regel 5c).

---

## 2. OpenMinis — nur Muster

Über 90 % sind für uns ohne Belang: eine mobile App mit Sandbox,
Cloud-Sicherung und zwei Oberflächen. Was bleibt, sind vier Muster aus der
Agent-Schleife — dort hat OpenMinis Betriebserfahrung, die Gotchi fehlt.

**Nicht übernehmen:** Sicherungssystem (28 Dateien, rclone, Krypto),
Browser-Steuerung, iSH/PRoot, alle Oberflächen, SkillStore in SQLite
(2 489 Zeilen — Gotchis dateibasierter Loader mit Gating ist hier besser),
Live-Aktivitäten und Hintergrund-Wachhaltung.

### 2.1 Tool-Schleifen-Erkennung ⭐

*Quelle: `ToolLoopDetector.swift` (370 Zeilen) — nachgebaut, nicht kopiert*

Werkzeugname und Argumente hashen, Fenster der letzten Aufrufe halten,
gestaffelt reagieren: warnen → blockieren → Notbremse.

Zwei Feinheiten, die den Unterschied machen:

- Die Prüfung läuft **vor** der Ausführung. Bei „blockieren" wird der
  Aufruf verhindert und die Meldung als *Werkzeugergebnis* eingespeist —
  das Modell erfährt also, dass es feststeckt.
- Auch der **Ergebnis-Hash** wird verfolgt. Gleiche Frage mit gleicher
  Antwort ist eine Schleife; gleiche Frage mit anderer Antwort ist
  legitimes Nachsehen.
- Warnungen sind gedrosselt, damit die Warnung nicht selbst zur Schleife
  wird.

**Für Chimera kritisch**, weil das Gerät autonom läuft (Zeitsteuerung,
Umgebungshören) und an einem bezahlten oder begrenzten Modell hängt. Eine
Schleife um drei Uhr nachts ist dort keine Unannehmlichkeit, sondern eine
Rechnung. `rate_limits.py` begrenzt die Frequenz, nicht die Sinnlosigkeit.

### 2.2 Werkzeug-Vorprüfung und JSON-Reparatur ⭐

*Quelle: `AIChatViewModel+ToolPreflight.swift` (284 Zeilen)*

Pflichtfelder gegen **dieselbe** Schema-Liste prüfen, die dem Modell
geschickt wird — sonst driften Prüfung und Versprechen auseinander. Dazu:
Zeichenketten müssen nicht-leer sein; `{"path": ""}` besteht eine reine
Existenzprüfung und ist trotzdem kaputt.

Vor dem Verwerfen wird **repariert**: Ist der Argumentblock leer, aber ein
Rest vorhanden, wird das Parsen mit angehängten schließenden Klammern
erneut versucht. Modelle brechen mitten im Strom ab und hinterlassen oft
ein Objekt, dem eine einzige Klammer fehlt.

Das Muster kennen wir schon — es steckt in unserem Mood-Validator
(Regel 2, eine Tabelle für Schema und Prüfung). Hier gilt es für Werkzeuge.

### 2.3 Gestaffelte Kontextschwellen ⭐

*Quelle: `ContextPolicy.swift` (92 Zeilen)*

Statt fester Grenze skalieren die Schwellen mit dem Fenster des Modells:

| Fenster | Auslagern bei Rest ≤ | Verdichten bei Rest ≤ |
|---|---|---|
| < 32 K | – | – |
| 32–64 K | 10 K | – |
| 64–128 K | 20 K | 10 K |
| ≥ 128 K | 40 K | 20 K |

Der eigentliche Lerneffekt steht in einem Kommentar zur Verdichtung: Die
Kapazität muss gegen das Modell geprüft werden, das die Anfrage
**tatsächlich bedient**. Bei OpenMinis lief das auseinander, wenn eine
Modellgruppe auf ein anderes Mitglied umgeroutet hatte — geprüft wurde
gegen das falsche Fenster.

Chimera hat mit der Anbieter-Registry samt Rückfall exakt dieselbe
Konstellation. Deshalb bekommt `LLMConnector` das Feld `context_window`
(Regel 5a).

### 2.4 Rangordnung im Gedächtnis

*Quelle: `AIChatViewModel+MemoryTools.swift`*

Dauerhafte, nutzergepflegte Notizen sind für den Agenten **nur lesbar**;
Tageslogs schreibt er selbst. Beide werden in den Systemprompt eingespeist
— mit der ausdrücklichen Ansage, dass es Hintergrundkontext ist und die
letzte Nutzernachricht Vorrang hat.

Das löst ein reales Problem: Ohne diese Ansage behandelt das Modell alte
Notizen als aktuelle Aufträge und nimmt abgeschlossene Aufgaben wieder
auf.

Gotchis `vault.py` ist reichhaltiger. Was fehlt, ist die **Rangordnung**
und die Nur-Lesen-Grenze.

---

## 3. Was Chimera selbst beisteuert

Kein Erbe, sondern der Grund für das Projekt:

- **Generierte Mood-Assets** statt Auswahlliste (`mood/`, Regel 1a)
- **Freie Zeichenformen** — elf Grundformen, relativ, mit Bewegung
- **Renderer aus Noisy**, auflösungsrelativ gemacht
- **Übergänge** über alle Felder, weich und hart (Regel 6b)
- **Umgebungshören mit Deutung durch das Modell** statt fester
  Label-Tabelle (§3.4)
- **Mienenspiel beim Sprechen** (§4.1)
- **Installer**, der die Treiberfrage löst

---

## 4. PiSugar Whisplay — HAT, Daemon und Chatbot

Geprüft am 3.11.2026, weil die Hersteller-Repos inzwischen mehr enthalten
als unser Nachbau vom 11.10.

### 4.0 Welche Repos gemeint sind

Ein Repo **`pisugar/whisplay-ai-studio` gibt es nicht** (die Organisation
hat 31 Repos, keines heißt so; geprüft über die Org-Liste der API). Gemeint
ist mit hoher Wahrscheinlichkeit **`PiSugar/whisplay-ai-chatbot`** — der
Taschen-Chatbot auf Basis des HAT. Mitgeprüft, weil sie zum selben Gerät
gehören: `PiSugar/Whisplay` (der Treiber), `whisplay-talk` und
`whisplay-plus`. Alle als flacher Klon, Arbeitsordner außerhalb des Repos.

### 4.1 Die Lizenzgrenze

| Repo / Teil | Lizenz | Folge für uns (MIT) |
|---|---|---|
| `Whisplay` — `runtime/`, `daemon/`, `example/`, `script/` | **Apache-2.0** | Übernehmen erlaubt (Namensnennung, Änderungen kennzeichnen). Wir bauen trotzdem nach. |
| `Whisplay` — `audio/whisplay-soundcard/src/**` (Kernelmodul, `whisplay-core.c`, `es8389.c`, **`whisplay-gain-lut.h`**) | **GPL-2.0-only** (SPDX-Kopfzeile je Datei) | **Keine Zeile.** Auch die Lautstärke-Tabelle nicht — sie ist Teil dieses Baums, nicht Apache. |
| `whisplay-ai-chatbot` | **GPL-3.0** | **Kein Code, nur Muster.** |
| `whisplay-talk` | **GPL-3.0** | dito (P2P-Sprechanlage, anderes Produkt). |
| `whisplay-plus` | Apache-2.0 | anderes Gerät (2,8″ DSI, 480×640, Pi 3/4/5) — für uns nicht relevant. |

Die Apache-Datei im Wurzelverzeichnis von `Whisplay` gilt **nicht** für den
Kernelbaum darunter; das steht nur in den Dateiköpfen. Wer dort
„Apache-2.0" liest und die LUT mitnimmt, verstößt gegen die Lizenz des
Urhebers — und das fällt bei einem `LICENSE`-Scan nie auf.

### 4.2 Der Treiber: Stand unseres Nachbaus

Unser `src/chimera/displays/whisplay/` ist aus `runtime/whisplay.py`,
Commit `c73051e6`, nachgebaut (Apache-2.0, im `display.json` vermerkt).
Gegen den heutigen Stand (`2026-10-30`) sind es **+123 Zeilen**, und zwar
genau drei Dinge:

1. **MangoPi MQ Quad** als Plattform (Erkennung über die SDIO-Kennung
   `0xd723`, eigene Pin-Tabelle, dynamische spidev-Suche über
   `/sys/class/spidev/*/device/of_node`).
2. **Joystick (5-Wege)** — optional per `enable_joystick`:
   BOARD 32/33/31/29/37 = BCM 12/13/6/5/26, **active-low mit internem
   Pull-up**, Entprellung 20 ms, Polling 5 ms wie die Taste.
3. **Pull-up als Option** für Eingänge (`_request_input(..., pull_up)`).

Alles andere — Einschaltfolge des ST7789, `+20`-Zeilen-Versatz, MADCTL
`0xC0`, RGB-LED als invertiertes Soft-PWM, Backlight PWM/An-aus je Modell,
Tastenpolling 5 ms — ist unverändert. Unser Nachbau ist also aktuell; zu
tun ist nichts.

**Eine bewusste Abweichung (3.11.2026): Die Taste wird nicht mehr
abgefragt.** Die Vorlage liest die Leitung alle 5 ms
(`BUTTON_POLL_INTERVAL_SEC`) — auf einem Zero 2 W sind das 200 `ioctl`s je
Sekunde für einen Taster, der meistens nicht gedrückt ist; am Gerät
gemessen 1,3 % eines Kerns im Leerlauf. Unser Treiber fordert stattdessen
**Kantenereignisse** an (`event_buffer_size` + `GPIO_V2_LINE_FLAG_EDGE_*`,
Kernel-ABI v2, das wir ohnehin sprechen) und wartet im Kern auf die Flanke.
Am Pi belegt: „Taste: Kantenereignisse (keine Abfrage im Leerlauf)“ im
Protokoll, Gesamtlast 10,8 % → 9,5 %. Fällt die Anforderung durch (alter
Kernel), greift die Abfrage als Rückfall — ohne Sonderweg im Aufrufer.

Was für die **Radxa-Portierung** (`docs/HARDWARE.md` §1, bisher
„nicht unterstützt") drinsteht und was nicht:

- Pin-Tabellen je Board (BOARD-Pin → `(gpiochip, Zeile)`) für Radxa Zero 3W,
  Cubie A7Z, Orange Pi Zero 2W/3W, MangoPi.
- SPI-Bus je Board: **Radxa Zero 3W = SPI3, CS0**, Cubie A7Z = SPI1,
  Orange Pi Zero 2W = SPI1, Zero 3W = SPI3; Takt außerhalb des Pi
  **48 MHz** statt 100 MHz. Auf dem Pi 5 liegt der Chip auf `gpiochip4`.
- **Ungeprüft auf unserem Gerät.** Das sind Herstellerangaben aus fremder
  Hardware; übernommen wird daraus nur, was wir am Radxa selbst messen
  (Regel 10g). Wert: Sie sagen uns, *wo* wir zuerst nachsehen.

### 4.3 Der Daemon: warum wir ihn nicht übernehmen

`daemon/` (Apache-2.0) ist die Gegenarchitektur zu unserer: Er hält LCD,
LED, Backlight und Taste exklusiv, Apps reden über einen Unix-Socket
(`/tmp/whisplay-daemon.sock`, zeilenweises JSON, Version 1) und malen in
einen **mmap-Framebuffer** (240×280, RGB565, stride 480) — inklusive
App-Registry, Fokus/Session-Token und Gesten (`quad_click` in 5 s,
`long_press`).

Das ist sauber gebaut und für ein Gerät mit mehreren Apps richtig. Für uns
falsch: DESIGN Regel 7 sagt *kein Daemon, kein exklusiver Zugriff*. Unser
Dienst besitzt Panel und LED selbst. Übernommen wird daraus nur die
**Gesten-Semantik** für unsere eine Taste (kurz / lang / mehrfach), nicht
der Transport.

*Stand 3.11.2026:* Die Semantik ist übernommen und um zwei Punkte
erweitert — `BUTTON_LONG_PRESS_SEC = 0.7` unverändert, das Klickfenster
aber **0,8 s statt `QUAD_CLICK_WINDOW_SEC = 3.0`** (bei uns hängt an einem
kurzen Druck eine Aktion, die nicht drei Sekunden auf ihre Bestätigung
warten darf), und das **Halten hat ein Ende** (`halten` / `halten_ende` für
Push-to-Talk), weil der Daemon nur einmal je Loslassen handelte. Die
Erkennung selbst ist Eigenbau (`display/gesten.py`, reine Zustandsmaschine
nach DESIGN Regel 7d) — der Daemon verzahnt seine Gesten mit App-Fokus und
Framebuffer, davon ist nichts übertragbar.

### 4.4 Ton: was uns fehlt und was wir nicht anfassen

- **`asound.conf`** (Apache-2.0, außerhalb des Kernelbaums): `dmix`
  (ipc_key 555555) und `dsnoop` (666666), `S16_LE`, **48 kHz, stereo**,
  period 1024, buffer 4096, `speexrate_best`. Wir haben heute nur die
  Karte und zwei Mixerwerte (Speaker/Mic = 80). Mehrere Prozesse, die
  gleichzeitig aufnehmen und abspielen, sind damit bei uns noch nicht
  abgesichert — relevant, sobald VAD und TTS nebeneinander laufen.
- **Lautstärke-Tabelle** (`whisplay-gain-lut.h`): 101 Stützstellen, 0–100 %
  → Codec-Register (WM8960-Kopfhörer 0–126, ES8389-DAC 108–218), aus einer
  Messung des Herstellers. **GPL-2.0 — wird nicht kopiert.** Der Nutzen
  ist ohnehin der Gedanke: eine *wahrgenommene* Kurve statt linearer
  Registerwerte. Diese Kurve bauen wir selbst (Messung oder Formel), sie
  steht in `ROADMAP` bei „Lautstärkeverwaltung".
- **Kernelmodul** (`whisplay-core.c`, `es8389.c`): GPL-2.0, wird als
  Overlay geladen, nicht von uns gebaut. Bleibt so.

### 4.5 Sprachverarbeitung — die Muster, die wir nachbauen

Der Chatbot ist GPL-3.0, also **Muster, keine Zeilen**. Interessant ist
nicht die Engine-Auswahl (Vosk/Whisper/faster-whisper bzw.
Piper/espeak-ng/Cloud — bei uns entscheidet das sherpa-onnx, `ROADMAP`
Phase 5), sondern die Mechanik drumherum. Vier Dinge, die auf einem
Zero 2 W den Unterschied machen:

1. **Aufnahme mit Energie-VAD statt fester Zeit.** `sox … silence 1 0.1
   <start>% 1 <ende>s <ende>%`: Aufnahme beginnt bei Pegel `start`, endet
   nach 1,5 s unterhalb von `ende = start × 0,5`; zusätzlich eine harte
   Höchstdauer. Kein Modell, kein Speicher, ~0 CPU.
2. **Nachgeführter Geräuschpegel.** Alle 30 s 0,35 s aufnehmen, RMS×100 als
   Prozent, Schwelle = Pegel + 1, geklemmt auf 2–60, geglättet mit 0,7
   (alter Wert) / 0,3 (neuer). Das ist die Größe, die oben in `start`
   eingesetzt wird — die Schwelle wandert also mit dem Raum, statt bei
   jedem Nutzer falsch zu sein. ~30 Zeilen, kein Modell.
   **Grenze:** Das ist ein Pegelmesser, kein Spracherkenner. Für „ist da
   Stimme?" bleibt Silero VAD die bessere Wahl; der Pegel taugt als
   Startwert, als VU-Anzeige und als Rückfall, wenn das Modell fehlt.
3. **Satzstrom statt fertiger Antwort.** Der LLM-Text wird beim Eintreffen
   an Satzzeichen zerlegt (`。！？!?，,` und `.` nur vor Leerraum/Ende),
   kurze Sätze zu ≤ 60 Zeichen zusammengefasst, der Rest bleibt liegen.
   Jeder Satz geht **sofort** an die TTS; bis zu **5** Synthesen
   gleichzeitig, Wiedergabe **in Reihenfolge**, ein leerer Ton wird einmal
   wiederholt, ein Watchdog bricht bei „Dauer + 2 s" ab. Das ist genau der
   Punkt „Sprachausgabe stückweise erzeugen" aus `ROADMAP` (Mienenspiel
   beim Sprechen) — und die einzige Antwort auf RTF > 1.
4. **Text vor der TTS reinigen.** URLs → „link", Markdown-/Symbolzeichen
   weg, Emoji weg, doppelte Satzzeichen zusammenfassen. Klingt nach
   Detail, ist der Unterschied zwischen „Sternchen Sternchen" und einem
   Satz.

Dazu zwei Kleinigkeiten mit Signalwirkung:

- **ALSA-Besitz ist exklusiv.** Vor jeder Aufnahme wird der
  Wiedergabeprozess beendet und **500 ms** gewartet, bis das Gerät wirklich
  frei ist; danach wird er neu gestartet. Wir werden dasselbe brauchen,
  sobald Aufnahme und Ausgabe im selben Dienst laufen.
- **Weckton** aus drei `sox synth`-Tönen (720/980/1320 Hz, zusammen
  0,36 s, mit Fade) — billiger und verlässlicher als eine Audiodatei.

Nicht übernehmen: die Wolke. Dort ist ASR/TTS/LLM standardmäßig ein
Cloud-Dienst (Gemini, OpenAI, Volcengine, Tencent). Unser Rahmen ist
lokal (Architekturregel 5); die Cloud-Pfade sind für uns nur Beleg, dass
die Schnittstellen austauschbar sind.

### 4.6 Was das für Rust heißt

Ehrlich: **die Sprachverarbeitung gehört nicht nach Rust.** Die Rechenlast
steckt in sherpa-onnx (C++), der Rest ist Prozess- und Warteschlangen-
Verwaltung — das ist bei Python richtig, weil der Agent dort schon lebt.
Ein Rust-Dienst dazwischen kostet eine Schnittstelle und bringt nichts.

Rust lohnt an zwei anderen Stellen:

- **Soft-PWM.** Backlight mit 1 kHz kostet uns bei 50 % rund 9 % eines
  Kerns (`ROADMAP`: „Software-PWM bei Zwischenwerten"). Der Hersteller
  löst das nicht besser — er hat denselben Python-Takt. Ein kleiner
  Rust-Helfer (eigener Thread, `SCHED_FIFO`, `nanosleep`) wäre die
  billigere Variante; ob es sich lohnt, entscheidet eine Messung, nicht
  das Gefühl.
- **OPUS**, falls wir je Sprache über Telegram schicken: `whisplay-talk`
  kodiert mit libopus über `ctypes` (GPL, also nur als Muster) — in Rust
  wäre das ein `opus`-Crate ohne Fremdprozess.

Ein eigener **Panel-Daemon** in Rust nach Herstellervorbild ist **nicht**
vorgesehen: Er würde Regel 7 aufgeben, um ein Problem zu lösen, das wir
nicht haben.

### 4.7 Offene Punkte aus dieser Analyse

1. **Joystick:** Hat unsere HAT-Revision die fünf Schalter? Wenn ja, wäre
   er ein Geschenk für die Bedienung (Menü, Lautstärke, PTT) — als Opt-in
   im Panel, mit Pull-up und 20 ms Entprellung. Prüfen am Gerät, nicht
   annehmen.
2. **`asound.conf` mit dmix/dsnoop** in den Installer aufnehmen, bevor
   Aufnahme und Ausgabe gleichzeitig laufen.
3. **Lautstärkekurve** selbst bauen (0–100 % → Codec-Wert), nicht die
   GPL-Tabelle.
4. **Satzstrom-TTS** als eigenes Modul im Agenten, wenn Phase 5 beginnt.
