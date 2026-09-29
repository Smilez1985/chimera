# Hybrid-Plan

Wie openclawgotchi, OpenMinis-Muster und der Noisy-Port zu **einem** Gerät
werden. Was übernommen wird und warum, steht in `docs/HERKUNFT.md`; hier
geht es um Aufbau und Reihenfolge.

Stand: 2026-09-29.

---

## 1. Der Gedanke dahinter

Die drei Quellen lösen jeweils ein Drittel:

| Quelle | bringt | fehlt ihr |
|---|---|---|
| openclawgotchi | Agent, Werkzeuge, Skills, Gedächtnis, Telegram | ein Gesicht (E-Paper mit 10 Emoticons) |
| OpenMinis | Härtung der Agent-Schleife | alles Gerätenahe |
| Noisy | Renderer, Ausdruck, Audioerfahrung | ein Agent |

Chimera fügt zusammen und ergänzt, was keiner hat: **einen Agenten, der
seinen eigenen Ausdruck schreibt.**

Der verbindende Gedanke, der alles zusammenhält: **Innerer Zustand wird
sichtbar.** Ein Agent, der nachdenkt, sieht nachdenklich aus. Einer, der
sich verrennt, sieht nervös aus. Das ist kein Schmuck — es ist das
ehrlichste Statusdisplay, das sich bauen lässt.

---

## 2. Aufbau

    ┌─ Eingänge ────────────────────────────────────────┐
    │  Telegram            Sprache (KWS→VAD→STT)        │
    │  Zeitsteuerung       Umgebungshören (Tagger)      │
    └──────────────────┬────────────────────────────────┘
                       │  gemeinsamer Verlauf (Regel 5d)
    ┌──────────────────▼────────────────────────────────┐
    │  Agent-Schleife                                    │
    │  ├─ Anbieter-Registry   Anthropic │ Ollama │ …    │
    │  ├─ Werkzeuge           + Vorprüfung, Reparatur   │
    │  ├─ Schleifenerkennung  ← OpenMinis-Muster        │
    │  ├─ Kontextschwellen    ← OpenMinis-Muster        │
    │  ├─ Skills (Gating)     ← openclawgotchi          │
    │  └─ Gedächtnis          ← openclawgotchi + Rang   │
    └──────────────────┬────────────────────────────────┘
                       │  Zustand + Mood
    ┌──────────────────▼────────────────────────────────┐
    │  Ausdrucksschicht                     ✅ fertig    │
    │  ├─ Mood-Vokabular, Validator, Registry           │
    │  ├─ Mischen, Variieren, Übergänge                 │
    │  └─ freie Zeichenformen                           │
    └──────────────────┬────────────────────────────────┘
    ┌──────────────────▼────────────────────────────────┐
    │  Renderer (aus Noisy)                 ✅ fertig    │
    │  Panel → SPI → LCD                    ✅ fertig    │
    │  + RGB-LED, Lautsprecher, Taste                   │
    └───────────────────────────────────────────────────┘

**Fertig ist die untere Hälfte.** Ausdruck, Renderer und Ausgabe stehen
und sind geprüft (162 Tests). Was fehlt, ist der Agent darüber — und
genau der existiert in openclawgotchi bereits.

---

## 3. Die Nahtstelle

Der heikle Punkt ist nicht der Agent und nicht der Renderer, sondern
**wie sie sich unterhalten.**

openclawgotchi steuert die Anzeige über Textbefehle im Modellausgang:

    FACE: happy
    DISPLAY: Alles ruhig
    SAY: Guten Morgen

Diese Befehle **bleiben**. Nur was dahinter geschieht, ändert sich:

| Befehl | vorher | nachher |
|---|---|---|
| `FACE:` | Emoticon aus einer Datei mit 10 Einträgen | Mood aus der Registry — auch ein erfundener |
| `DISPLAY:` | Text aufs E-Paper | Statuszeile in den 40 zusätzlichen Zeilen |
| `SAY:` | Sprechblase | Sprechblase **und** Sprachausgabe |

Damit laufen bestehende Skills und der Systemprompt unverändert weiter.
Das ist der Grund, diese Schnittstelle nicht anzufassen, obwohl sie
unelegant wirkt: Sie ist die Bruchstelle mit den wenigsten Folgen.

**Was ersetzt wird**, ist die Ebene darunter: `hardware/display.py` startet
je Bild einen Unterprozess mit `sudo`, Sperre und 45 s Zeitgrenze. Bei 15
Bildern je Sekunde wären das 15 Prozessstarts je Sekunde. Stattdessen
läuft der Renderer als Dauer-Faden, und der Agent setzt nur den Zustand
(Regel 7).

### Zustandsübergabe

Der Renderer liest einen `State` (Mood, Pegel, spricht gerade, …). Der
Agent schreibt hinein. Zwei Fäden in einem Prozess brauchen dafür kein
geteiltes Gedächtnis — Noisys `noisy_shm.py` löst ein Problem, das erst
bei **getrennten Prozessen** entsteht.

Ob Audio als eigener Prozess läuft, entscheidet die Messung: Wenn die
Sprachverarbeitung den Renderer ausbremst, wird sie getrennt, und dann
kommt Noisys geteiltes Gedächtnis samt seinem dokumentierten Kniff um den
`resource_tracker` zum Einsatz. **Erst messen** (Regel 10g).

---

## 4. Reihenfolge

Jede Stufe endet mit etwas, das läuft. Keine Stufe hängt von Hardware ab,
die noch nicht da ist.

### H1 — Agent-Grundlage *(ohne Hardware)*

openclawgotchi-Kern übernehmen, ohne alles Gerätenahe.

- `llm/base.py` → um `supports_tools` und `context_window` erweitern
- **Anbieter-Registry** statt Router (Regel 5a)
- Ollama- und Anthropic-Connector; Anthropic mit Abo-Anmeldung, Kennung
  zur Laufzeit ermittelt (Regel 5b)
- `skills/loader.py`, `memory/`, `audit_logging/` übernehmen
- Werkzeuge aus dem LiteLLM-Connector herauslösen, **Sicherheitsschicht
  unverändert mitnehmen** (`shell=False`, keine Verkettung, keine
  verschachtelten Shells, `sudo` gesperrt)

*Fertig, wenn:* Der Agent antwortet über Ollama und kann Werkzeuge nutzen.
Kein Gesicht, kein Telegram.

### H2 — Härtung *(ohne Hardware, parallel zu H1 möglich)*

Die vier OpenMinis-Muster, nachgebaut. Zusammen rund 300 Zeilen,
voneinander unabhängig, einzeln prüfbar.

- Schleifenerkennung + Gegenprobe (echte Schleife simulieren und
  nachweisen, dass sie ohne Erkennung durchläuft)
- Werkzeug-Vorprüfung und JSON-Reparatur
- Gestaffelte Kontextschwellen, geprüft gegen das **bedienende** Modell
- Rangordnung im Gedächtnis

*Fertig, wenn:* Eine erzwungene Schleife wird erkannt und abgebrochen.

### H3 — Agent trifft Gesicht *(Hardware hilfreich, nicht nötig)*

- `hardware/display.py` entfernen, Renderer als Dauer-Faden
- `FACE:`/`DISPLAY:`/`SAY:` auf die Ausdrucksschicht legen
- die 10 alten Emoticons als Startbestand abbilden
- `skills/mood/SKILL.md` — der Agent steuert sein Gesicht über einen
  Skill, nicht über einen Sonderpfad (Regel 8)
- **Zustände auf Moods abbilden:** denkt, spricht, hört zu, Schleife
  erkannt, Kontext voll
- Statuszeile

*Fertig, wenn:* Der Agent denkt und das Gesicht zeigt es.

### H4 — Telegram *(ohne Hardware)*

- Bot übernehmen, Verlauf **mit der Sprache teilen** (Regel 5d)
- Kanal als Kontext mitgeben (gesprochene Antworten kürzer)
- Zeitsteuerung und Erweiterungspunkte

*Fertig, wenn:* Eine Telegram-Anfrage ist dem Gesicht anzusehen.

### H5 — Installer und erste Inbetriebnahme *(Hardware nötig)*

- Module 20–70 für den Pi (`docs/INSTALLER.md`)
- zram und Auslagerung (Regel 5e)
- **Erster Lauf auf echter Hardware.** Hier fallen die Antworten auf:
  Bildrate, Speicherlage, Whisplay-Revision

### H6 — Sprache *(Hardware nötig)*

VAD → Wake-Word → Erkennung → Synthese, einzeln. Emotion der Stimme an
den Mood koppeln (Regel 4b). Danach das Mienenspiel beim Sprechen (§4.1)
— der härteste Lastfall.

### H7 — Umgebungshören *(Hardware nötig)*

Tagger, drei Geschwindigkeiten, nur im Ruhezustand (§3.4).

### H8 — Restliche Peripherie

RGB-LED an den Mood-Schein, Taste, Lautsprecher, Akkustand,
Thermik neu kalibrieren.

---

## 5. Was sich dabei von selbst klärt

Drei Fragen, die heute offen sind und keine Entscheidung brauchen,
sondern eine Messung:

1. **Hält der Renderer 15 Bilder je Sekunde, während gesprochen wird?**
   In der Entwicklungsumgebung braucht ein Bild 0,7 ms bei 66,7 ms
   Budget — das Zielgerät ist deutlich langsamer. Antwort in H6.
2. **Müssen Erkennung und Synthese rotieren?** Mit zram und Auslagerung
   wahrscheinlich nicht; der Kernel verdrängt feiner als eine
   Rotationsmechanik. Antwort in H5.
3. **Braucht Audio einen eigenen Prozess?** Nur wenn es den Renderer
   ausbremst. Antwort in H6.

Für alle drei sind die Auswege bereits benannt und tasten den Entwurf
nicht an.

---

## 6. Was dieser Plan bewusst nicht tut

- **Kein Merge von openclawgotchi.** Chimera nimmt Module, nicht das
  Projekt. Der E-Paper-Teil, die Discord-Anbindung und die
  Selbstveränderung bleiben draußen.
- **Keine Portierung von Noisy.** Noisy läuft unverändert weiter. Der
  Renderer wurde übernommen und angepasst, nicht abgelöst.
- **Kein Code aus OpenMinis.** Vier Muster, neu geschrieben.
- **Keine Selbstveränderung.** `patch_self.py` bleibt draußen — auf einem
  Gerät, dessen System auf eMMC liegt, gibt es keinen Rettungsweg
  (`docs/HARDWARE.md` §3a).
