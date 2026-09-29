# Blaupausenprüfung H4

**Stand:** 2026-09-29, Arbeitsbaum auf `abcc21e` plus unversionierte H4-Dateien.
**Geprüft gegen:** `docs/DESIGN.md`, 38 Architekturregeln.
**Anlass:** Regel „was gebaut wird, wird gegen die Blaupause geprüft — vorher,
nicht nachher". Diese Prüfung holt das für H4 nach.

Geprüfte Dateien: `agent/session.py`, `bot/telegram.py`, `app.py`,
`__main__.py`, sowie die Änderungen an `mood/registry.py`.

---

## Ergebnis in einem Satz

Die Bedienschnittstelle ist regelkonform gebaut; **die Gesichtskette war es
nicht** — sie war an fünf Stellen unterbrochen, und zwar so, dass kein Test
und kein Lauf es meldete.

---

## Stand nach der Behebung

**Alle Befunde sind behoben**, die Entscheidung zu B1 lautete „anschließen".
Vier neue Regeln (5i, 5j, 7a, 7b) und Regel 10k sind eingetragen; das
Verzeichnis führt 42 Regeln und ist mit dem Fließtext deckungsgleich.

Nachgewiesen: 431 Tests grün, davon 27 neue für die Gesichtskette
(`tests/test_display_wiring.py`). Jede Gegenprobe wurde gegen den alten
Code **verifiziert** — jeder Befund färbt den Test rot, wenn man ihn
wiederherstellt. Ein echter Lauf zeichnet 30 Bilder in zwei Sekunden und
hält sauber an.

Zwei Dinge sind beim Beheben zusätzlich aufgefallen und stehen unten:
ein zweiter Fehler in `run()` (B3b) und eine dauerhaft wirkungslose
Temperaturkopplung (B6).

---

## 1. Was der Regel entspricht

### Regel 5d — Ein Gespräch, zwei Türen

Umgesetzt, und zwar an der richtigen Stelle. `Session` besitzt **einen**
Agenten; `Channel` ist eine eingefrorene Beschreibung ohne eigenen Zustand.
Beide Türen rufen dieselbe `ask()`, der Verlauf ist gemeinsam.

Bemerkenswert korrekt: `/neu` im Bot leert `session.agent.history`, nicht
einen kanaleigenen Verlauf. Ein Kanal mit eigenem Zustand wäre genau die
Spaltung, die 5d verbietet.

`threading.RLock` serialisiert den Zugriff. Die Begründung im Modulkopf
trifft zu: Der Agent ist nicht wiedereintrittsfähig, zwei gleichzeitige
Läufe würden `history` und Schleifenwächter überschreiben — ein Fehler,
der erst unter Last auftritt.

### Regel 5h — Kein Anbieter wird vorausgesetzt

`build()` scheitert an nichts: ohne Anbieter, ohne Panel, ohne Skills läuft
es und sammelt das Fehlende in `notes`. `__main__.py` verweigert das
Gespräch erst, wenn wirklich kein Modell erreichbar ist (Exitcode 2) —
`--pruefen` läuft trotzdem durch.

### Regel 8a — Stiller Erfolg ist die gefährlichste Fehlerart

`TelegramAPI.call()` macht aus `{"ok": false}` einen Fehler, statt
weiterzulaufen. Richtig.

### Regel 13 — Keine Secrets im Repo

Token und Absenderliste kommen aus der Umgebung
(`CHIMERA_TELEGRAM_TOKEN`, `CHIMERA_TELEGRAM_ALLOWED`), mit sprechenden
Fehlermeldungen. Kein Vorgabewert, keine Beispieldatei mit echten Werten.

### Nicht in der Blaupause, aber richtig: die Positivliste

`Bot.__post_init__` verweigert den Start ohne erlaubte Absender. Ein
offener Bot mit `execute_bash` dahinter wäre ein Fernzugang für jeden, der
die Adresse kennt. **Das steht in keiner Regel** — Vorschlag dazu unter §3.

---

## 2. Befunde

### B1 — Das Gesicht bewegt sich nicht (Regel 10h)

`NoisyRenderer` wird im gesamten `src/` **nirgends instanziiert**. Nur
`tests/test_render.py` und `tools/contact-sheet.py` benutzen ihn.

Folge: `Face` setzt Ausdrücke auf `State`, und niemand liest sie. Der
Zustand ändert sich, das Bild entsteht nie. Nach Regel 10h ist der
Renderer damit kein fertiger Baustein, sondern ein offenes Ende.

### B2 — `app.py` öffnet ein Panel und wirft es weg

In `_try_face()`:

    panel = open_panel()          # geöffnet
    notes.append(...)             # ausgewertet
    return Face(moods, State())   # nicht übergeben

Das Panel wird nur benutzt, um zu melden, ob es eines gibt. Danach fällt
es aus dem Gültigkeitsbereich. Ein echtes `WhisplayPanel` wäre damit
geöffnet und unbenutzt — auf dem Gerät ein belegter SPI-Bus ohne Zweck.

Zusammen mit B1: Selbst wenn der Renderer liefe, bekäme er dieses Panel
nicht. Er baut sich in seinem Konstruktor ein eigenes `NullPanel`.

### B3 — `NoisyRenderer.run()` stürzt sofort ab

Zeile 2260 und 2280 lesen `TARGET_FPS` und `FRAME_TIME` als **globale**
Namen. Die gibt es nicht; sie existieren nur als `self.TARGET_FPS` und
`self.FRAME_TIME` (Zeile 362/363). Nachgewiesen:

    NameError: name 'TARGET_FPS' is not defined

Der Fehler tritt in der zweiten Zeile von `run()` auf, also vor dem ersten
Bild. **Warum es niemand merkte:** `test_render.py` ruft `render()` und
`show()` direkt auf — nie `run()`. Dieselbe Klasse von Lücke wie beim
`Registry.load()`-Fehler: Der Test prüft an der Schleife vorbei.

Die drei Befunde bilden eine Kette: `run()` ist defekt (B3), würde aber
ohnehin nichts anzeigen (B2), und wird ohnehin nicht aufgerufen (B1).

**Behoben:** `self.TARGET_FPS`/`self.FRAME_TIME`, dazu ein Stop-Event, damit
sich die Schleife beenden lässt, ohne auf das nächste Bild zu warten.

### B3b — `run()` hätte auch ohne B3 kein Bild ausgegeben

Beim Beheben von B3 aufgefallen: Die Schleife rief `self.render()`. Das
zeichnet ein Bild und **gibt es zurück** — ans Panel schickt es erst
`show()`. Zwei unabhängige Fehler auf demselben Weg, beide hinter demselben
nie betretenen Zweig. Hätte man nur den `NameError` behoben, wäre eine
laufende Schleife entstanden, die nichts anzeigt — und die Ursache hätte
man beim Panel gesucht.

**Behoben:** `run()` ruft `show()`.

### B6 — Die Temperaturkopplung war wirkungslos, und zwar lautlos

Gefunden mit `tools/check-globals.py`, das für B3 entstand:
`read_temperature()` öffnete `THERMAL_PATH` — einen Namen, den es im Modul
nie gab. Der `NameError` fiel in ein `except Exception` darunter und wurde
zu `cpu_temp = 45.0`.

Folge: Noisys Kopplung von Müdigkeit an die CPU-Temperatur (Augenlider
sinken, wenn der Pi heiß wird) hat **nie funktioniert**. Jeder Lauf sah aus
wie ein Gerät bei angenehmen 45 °C. Das ist Regel 8a in Reinform — und
wäre auf der Zielhardware als „Kalibrierungsfrage" fehlgedeutet worden,
weil die Recherche dort ein echtes Problem erwartet (Dauerlast macht den
Avatar permanent müde).

**Behoben:** `thermal_path` ist eine Instanzeigenschaft mit Vorgabewert
(Regel 10c — auf dem Radxa heißt die Zone anders). Gefangen wird nur noch
`OSError`/`ValueError`, einmal gemeldet, danach abgeschaltet statt bei
15 Bildern je Sekunde das Protokoll zu fluten.

### B4 — `Chimera.face` ist typlos und wird nur geraten

`face: object = None`, und `_on_state` ruft `self.face.show_state(what)`.
Dass `Face` diese Methode hat, stimmt zufällig (face.py:90). Ein
`AttributeError` hier landet im `except` von `Bot._state` und wird zur
Debug-Zeile — ein stiller Fehlschlag nach Regel 8a.

**Behoben:** `Chimera.face` ist `Face | None`, `_on_state` prüft auf `None`
und protokolliert einen Fehlschlag als Fehler. Dazu Regel 7b.

### B5 — Regel 7 ist nicht anwendbar, solange B1 gilt

„Ein Prozess, ein Framebuffer" setzt voraus, dass überhaupt jemand
zeichnet. Sobald B1 behoben wird, muss entschieden werden, ob der
Renderer im Hauptprozess als Faden läuft (dann konkurriert er mit dem
Agenten um die globale Sperre) oder getrennt — analog zu Regel 5g für
Audio.

**Entschieden, nach Recon in beiden Vorlagen** (`docs/RECHERCHE.md` §5,
Regel 7): Die Vorlagen haben **verschiedene** Prozessmodelle, und zwar zu
Recht — openclawgotchi startet für E-Ink einen Subprozess je Bild (~2 s je
Bild, jedes teuer), Noisy hält für das LCD einen Dauer-Thread (15 Bilder/s).
Keines ist falsch; sie bedienen verschiedene Anzeigen.

Chimera braucht beides, weil das Panel eine Eigenschaft ist (Regel 6c).
Daraus wurde **Regel 7a**: Die Bildrate gehört zum Panel, der Renderer
liest sie. `fps = 0` heißt „nur auf Anstoß" — der E-Ink-Fall, ohne
Sonderweg im Renderer.

Faden, nicht Prozess: Der Renderer zeichnet mit Pillow und wandelt mit
numpy um, das die globale Sperre freigibt — gemessen 2,5 ms von 66,7 ms
Budget. Ein eigener Prozess würde den Bildspeicher über eine
Prozessgrenze schieben und auf 512 MB einen zweiten Python-Heap kosten.
Anders als Audio (Regel 5g), das wirklich rechnet.

---

## 3. Die Regeln, die daraus wurden

Alle vier sind nach Rücksprache **eingetragen**. Nummern und endgültiger
Wortlaut stehen in `docs/DESIGN.md`; hier bleibt die Begründung.

| Vorschlag | wurde | deckt |
|---|---|---|
| A | **5i** — Ein Kanal hat keinen eigenen Zustand | Bauplan zu 5d |
| B | **5j** — Eine Tür von außen ohne Positivliste startet nicht | war nur im Code |
| C | **7b** — Wer etwas anzeigt, bekommt die Anzeige übergeben | B2, B4 |
| (aus B5) | **7a** — Die Bildrate gehört zum Panel | B5 |

### Vorschlag A — Kanäle haben keinen eigenen Zustand

Ergänzung zu 5d, weil 5d das Ziel nennt, aber nicht den Bauplan:

> Die Sitzung besitzt den Agenten und seinen Verlauf. Ein Kanal beschreibt
> nur Ein- und Ausgabe: Betriebsart, Ausgabelänge, Name. Er hält keinen
> Verlauf, keine Einstellungen, keinen Zähler. Ein Befehl, der den Zustand
> ändert (etwa „Gespräch neu"), wirkt auf die Sitzung, nie auf einen
> einzelnen Kanal — sonst entsteht die Spaltung wieder durch die Hintertür.

### Vorschlag B — Eine Bedienschnittstelle ohne Positivliste startet nicht

Bisher nur im Code begründet:

> Jede Tür von außen (Telegram heute, weitere später) braucht eine Liste
> erlaubter Absender. Ohne Liste startet sie nicht — kein Vorgabewert, kein
> „offen, wenn leer". Begründung: Hinter der Tür steht ein Agent mit
> Dateizugriff und Shell. Wer die Adresse kennt, hätte sonst das Gerät.
> Die Liste steht in der Umgebung, nicht im Repo (§13).

### Vorschlag C — Wer den Zustand anzeigt, wird angeschlossen, nicht vermutet

Deckt B2 und B4 ab:

> Ein Baustein, der eine Anzeige bedient, bekommt sie übergeben. Er sucht
> sie sich nicht selbst und geht nicht davon aus, dass eine da ist. Wo
> nichts angeschlossen ist, steht ausdrücklich ein Platzhalter — damit der
> Unterschied zwischen „läuft blind" und „ist kaputt" sichtbar bleibt und
> nicht in einem `except` verschwindet.

---

## 4. Erledigt

1. ✓ **B3** — Instanzattribute statt Globale, plus Stop-Event.
2. ✓ **B3b** — `run()` ruft `show()`, nicht `render()`.
3. ✓ **B6** — Temperaturpfad als Eigenschaft, engeres `except`.
4. ✓ **B2** — Panel wird durchgereicht und im Renderer benutzt.
5. ✓ **B1** — Renderer angeschlossen, `start_display()`/`stop_display()`.
6. ✓ **B4** — `face: Face | None`, Fehlschlag wird protokolliert.
7. ✓ **B5** — als Regel 7a entschieden, nach Recon in beiden Vorlagen.
8. ✓ **Regeln 5i, 5j, 7a, 7b** eingetragen; Verzeichnis deckungsgleich.
9. ✓ **Changelog** unter `[Unreleased]`, **Roadmap** Phase 4c geschlossen.

Offen bleibt der Commit selbst — und die ehrliche Grenze: **nichts davon
lief auf der Zielhardware.** Die 15 Bilder je Sekunde sind von Noisy
übernommen, nicht auf einem Zero 2 W gemessen; dass die globale Sperre den
Renderer nicht stört, ist begründet, aber nicht belegt. Beides steht als
bekannte Einschränkung im Changelog.

---

## 5. Was diese Prüfung methodisch gezeigt hat

Drei der sechs Befunde lagen hinter **derselben Lücke**: einem Zweig, den
kein Test betritt. `run()` wurde nie aufgerufen, also blieben zwei Fehler
darin unsichtbar; `read_temperature()` wurde aufgerufen, aber sein Fehler
fiel in ein weites `except`.

Daraus zwei übertragbare Lehren:

**Ein Einstiegspunkt, den kein Test startet, ist ungeprüft — egal wie viele
Tests es gibt.** `test_render.py` hatte 16 grüne Prüfungen für den
Renderer. Der Startbefehl war trotzdem defekt.

**`except Exception` um mehr als einen Aufruf verbirgt Programmierfehler.**
Der Block sollte einen fehlenden Sensor abfangen und fing einen `NameError`
mit. Deshalb: das Erwartete fangen (`OSError`, `ValueError`), nicht alles.

Das Werkzeug `tools/check-globals.py` entstand aus dem ersten Punkt und
fand sofort einen dritten Fall, den niemand gesucht hatte. Es gehört in
jede Prüfkette, kostet keine Laufzeit und findet genau die Fehlerklasse,
die Tests strukturell übersehen.
