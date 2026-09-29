#!/usr/bin/env python3
"""Tests fuer die Gesichtskette: Gesicht -> Renderer -> Panel.

Die Befunde B1-B4 aus `docs/PRUEFUNG-H4.md` waren alle vom selben Typ:
Etwas war gebaut, aber nicht angeschlossen, und **kein Test bemerkte es**,
weil die Tests die Bausteine einzeln aufriefen.

Deshalb prueft diese Datei nicht Bausteine, sondern **Verbindungen**:

* laeuft ``run()`` wirklich, und kommen Bilder am Panel an (B3, B1)
* bekommt der Renderer das Panel, das ``app.py`` geoeffnet hat (B2)
* wirkt ein Ausdruck, den das Gesicht setzt, auf das gezeichnete Bild (B1)
* meldet ``_on_state`` einen Fehler, statt ihn zu verschlucken (B4)
* bestimmt das Panel die Bildrate, nicht der Renderer (Regel 7a)

Jeder Test hat eine Gegenprobe (Regel 9).
"""

import logging
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from chimera import app                                      # noqa: E402
from chimera.display.panel import NullPanel, Panel           # noqa: E402
from chimera.render.avatar import NoisyRenderer, State        # noqa: E402

PASS = FAIL = 0


def ok(msg):
    global PASS
    PASS += 1
    print(f"  ok    {msg}")


def bad(msg):
    global FAIL
    FAIL += 1
    print(f"  FAIL  {msg}")


def check(msg, got, want):
    ok(msg) if got == want else bad(f"{msg} — erwartet {want!r}, bekam {got!r}")


class ZaehlPanel(NullPanel):
    """Ein Panel, das mitschreibt, was es bekommt."""

    def __init__(self, **kw):
        super().__init__(**kw)
        self.bilder = []

    def show(self, image):
        super().show(image)
        self.bilder.append(image)


print("== run() zeichnet wirklich (B3) ==")

# B3: run() las TARGET_FPS/FRAME_TIME als Modulglobale, die es nicht gab.
# Der Aufruf endete in Zeile 2 mit NameError -- ohne dass ein Test es sah,
# weil kein Test run() aufrief. Genau das passiert hier.
panel = ZaehlPanel(fps=30)
r = NoisyRenderer(State(), panel, thermal_path="")
stop = threading.Event()
t = threading.Thread(target=r.run, args=(stop,), daemon=True)
t.start()
time.sleep(1.0)
lief = t.is_alive()
stop.set()
t.join(3.0)

ok("run() ueberlebt die erste Sekunde") if lief \
    else bad("run() ist sofort gestorben (NameError?)")
ok(f"Bilder kamen am Panel an ({len(panel.bilder)})") if panel.bilder \
    else bad("kein einziges Bild am Panel")
ok("run() endet auf Zuruf") if not t.is_alive() \
    else bad("run() haelt nicht an")

# Gegenprobe: Ein Renderer, der nie laeuft, liefert auch nichts. Damit ist
# gezeigt, dass die Bilder oben von run() kommen und nicht vom Aufsetzen.
leer = ZaehlPanel()
NoisyRenderer(State(), leer, thermal_path="")
check("Gegenprobe: ohne run() kein Bild", len(leer.bilder), 0)

print("== Die Bildrate gehoert zum Panel (Regel 7a) ==")


class EInk(Panel):
    """Ein Panel, das nicht animiert werden will."""

    width, height, fps = 240, 280, 0

    def __init__(self):
        self.bilder = 0

    def show(self, image):
        self.bilder += 1


eink = EInk()
re = NoisyRenderer(State(), eink)
check("Renderer uebernimmt fps=0 vom Panel", re.TARGET_FPS, 0)

# Bei fps=0 darf run() nicht im Kreis zeichnen -- es soll zurueckkommen.
#
# In einem Faden mit Beitrittsfrist, NICHT direkt: Ignoriert der Renderer
# die Bildrate des Panels, laeuft run() endlos und der Test haengt, statt
# rot zu werden. Ein haengender Test meldet nichts -- er sieht aus wie ein
# langsamer. Also eine Frist, und die Ueberschreitung ist der Fehlschlag.
ein_stop = threading.Event()
te = threading.Thread(target=re.run, args=(ein_stop,), daemon=True)
te.start()
te.join(3.0)
if te.is_alive():
    bad("run() zeichnet trotz fps=0 im Kreis — Regel 7a nicht umgesetzt")
    ein_stop.set()
    te.join(2.0)
else:
    ok("run() kehrt bei fps=0 zurueck")
check("und hat nichts gezeichnet", eink.bilder, 0)

# Gegenprobe: dasselbe Panel mit Bildrate zeichnet sehr wohl.
schnell = ZaehlPanel(fps=20)
check("Renderer uebernimmt fps=20 vom Panel",
      NoisyRenderer(State(), schnell).TARGET_FPS, 20)

# Und die Uebersteuerung fuer Messungen bleibt moeglich.
check("target_fps uebersteuert das Panel",
      NoisyRenderer(State(), schnell, target_fps=5).TARGET_FPS, 5)

print("== app.py verdrahtet Panel und Renderer (B1, B2) ==")

notes = []
face, renderer, panel2 = app._try_face(notes)

if face is None:
    bad("_try_face liefert kein Gesicht")
else:
    ok("Gesicht vorhanden")

if renderer is None:
    bad("_try_face liefert keinen Renderer — B1 nicht behoben")
else:
    ok("Renderer vorhanden (B1)")

if panel2 is None:
    bad("_try_face liefert kein Panel — B2 nicht behoben")
else:
    ok("Panel wird zurueckgegeben (B2)")

# B2 im Kern: Der Renderer muss GENAU DAS Panel haben, das geoeffnet wurde
# -- nicht ein selbstgebautes. Identitaet, nicht Gleichheit.
if renderer is not None and panel2 is not None:
    ok("Renderer hat das geoeffnete Panel") \
        if renderer.panel is panel2 \
        else bad("Renderer hat ein ANDERES Panel — B2 besteht weiter")

# Und Gesicht und Renderer muessen sich denselben Zustand teilen, sonst
# zeichnet der Renderer ein anderes Gesicht als das gesetzte.
if face is not None and renderer is not None:
    ok("Gesicht und Renderer teilen den Zustand") \
        if face.state is renderer.state \
        else bad("zwei getrennte Zustaende — das Gesicht wird nicht gezeigt")

print("== Ein Ausdruck wirkt auf das Bild (B1 vollstaendig) ==")

# Die eigentliche Probe auf die Kette: Wenn das Gesicht einen Ausdruck
# setzt, muss sich das gezeichnete Bild aendern. Vorher war das unmoeglich
# -- der Renderer existierte nicht.
p3 = ZaehlPanel()
st = State()
r3 = NoisyRenderer(st, p3, thermal_path="")

from chimera.agent.face import Face                          # noqa: E402
from chimera.mood.registry import Registry as MoodRegistry    # noqa: E402

moods = MoodRegistry.load(app.BUILTIN_MOODS)
f3 = Face(moods, st)

r3.show()
vorher = p3.last

vorhanden = moods.names()
if not vorhanden:
    bad("keine Moods geladen — Bibliothek leer?")
else:
    ok(f"Mood-Bibliothek geladen ({len(vorhanden)} Eintraege)")
    name = "ROCK" if "ROCK" in vorhanden else vorhanden[0]
    f3.set_by_name(name, hard=True)
    for _ in range(3):
        r3.show()
    ok(f"Ausdruck {name} veraendert das Bild") \
        if p3.last != vorher \
        else bad("Bild bleibt gleich — Ausdruck kommt nicht an")

    # Gegenprobe: Der Unterschied muss vom Ausdruck kommen, nicht davon,
    # dass jedes Bild anders ist. Also denselben Ausdruck noch einmal
    # setzen und pruefen, dass der Zustand denselben Mood traegt.
    vorm_mood = st.mood.get("name")
    f3.set_by_name(name, hard=True)
    check("Gegenprobe: derselbe Ausdruck bleibt derselbe",
          st.mood.get("name"), vorm_mood)

print("== Fehler beim Anzeigen werden gemeldet (B4) ==")


class Boeses:
    """Ein Gesicht, dessen Zustandsanzeige scheitert."""

    state = None

    def show_state(self, what):
        raise RuntimeError("Anzeige kaputt")


chi = app.Chimera(home=Path("/tmp"), session=None, registry=None,
                  toolbox=None, face=Boeses())

logs = []


class Fang(logging.Handler):
    def emit(self, record):
        logs.append(record)


h = Fang()
app.log.addHandler(h)
try:
    chi._on_state("denkt")          # darf nicht durchschlagen
    ok("_on_state reisst den Aufrufer nicht mit")
except Exception as exc:
    bad(f"_on_state wirft weiter: {exc}")
finally:
    app.log.removeHandler(h)

# B4: Der Fehler darf nicht schweigend verschwinden (Regel 8a).
laut = [r for r in logs if r.levelno >= logging.ERROR]
ok("und schreibt den Fehler ins Protokoll") if laut \
    else bad("Fehler verschwindet lautlos — B4 besteht weiter")

# Gegenprobe: ohne Gesicht passiert gar nichts, auch keine Meldung.
logs.clear()
h2 = Fang()
app.log.addHandler(h2)
app.Chimera(home=Path("/tmp"), session=None, registry=None,
            toolbox=None, face=None)._on_state("denkt")
app.log.removeHandler(h2)
check("Gegenprobe: ohne Gesicht keine Fehlermeldung",
      [r for r in logs if r.levelno >= logging.ERROR], [])

print("== start_display / stop_display ==")

p4 = ZaehlPanel(fps=25)
st4 = State()
chi4 = app.Chimera(home=Path("/tmp"), session=None, registry=None,
                   toolbox=None, face=None,
                   renderer=NoisyRenderer(st4, p4, thermal_path=""),
                   panel=p4)

check("start_display meldet Erfolg", chi4.start_display(), True)
time.sleep(0.6)
check("der Faden lebt", chi4._painter.is_alive(), True)
ok(f"es wird gezeichnet ({len(p4.bilder)} Bilder)") if p4.bilder \
    else bad("Faden laeuft, aber nichts wird gezeichnet")

# Zweimal starten darf keinen zweiten Faden erzeugen: SPI vertraegt keine
# zwei Schreiber (Regel 7).
erster = chi4._painter
chi4.start_display()
ok("zweimal starten gibt keinen zweiten Faden") \
    if chi4._painter is erster else bad("zweiter Renderer-Faden entstanden")

chi4.stop_display()
check("stop_display haelt an", chi4._painter, None)

# Gegenprobe: ein Panel ohne Bildrate bekommt keinen Faden.
chi5 = app.Chimera(home=Path("/tmp"), session=None, registry=None,
                   toolbox=None, face=None,
                   renderer=NoisyRenderer(State(), EInk()), panel=EInk())
check("Gegenprobe: fps=0 startet keinen Faden", chi5.start_display(), False)

# Und ohne Renderer erst gar nichts.
chi6 = app.Chimera(home=Path("/tmp"), session=None, registry=None,
                   toolbox=None)
check("Gegenprobe: ohne Renderer kein Start", chi6.start_display(), False)

print()
print(f"Ergebnis: {PASS} ok, {FAIL} fehlgeschlagen")
sys.exit(1 if FAIL else 0)
