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
