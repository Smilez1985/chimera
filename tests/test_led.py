#!/usr/bin/env python3
"""Tests fuer die LED (DESIGN Regel 7c/7d) und ihre Verdrahtung.

Zwei Ebenen, wie bei test_display_wiring.py:

* der Verwalter selbst: Prioritaet, Verdraengen, Ablauf, Muster als reine
  Funktion der Zeit, Grundzustand = gedimmter Glow
* die VERBINDUNGEN: ``build()`` legt Statuszeile und LED an und gibt sie
  dem Renderer; ``renderer.show()`` setzt die LED auf das Panel;
  ``_on_state`` erreicht Zeile UND LED; die Taste quittiert per LED.

Die Statuszeile war gebaut und getestet, aber nie angeschlossen -- kein
Test hat das gesehen, weil keiner ``build()`` mit einem hohen Panel
aufrief. Genau das tut diese Datei.

Gegenproben in tests/gegenprobe_led.py.
"""

import os
import sys
from pathlib import Path

SRC = Path(os.environ.get("CHIMERA_SRC") or Path(__file__).resolve().parent.parent / "src")
sys.path.insert(0, str(SRC))

PASS = FAIL = 0


def ok(m):
    global PASS
    PASS += 1
    print(f"  ok    {m}")


def bad(m):
    global FAIL
    FAIL += 1
    print(f"  FAIL  {m}")


def check(m, got, want):
    ok(m) if got == want else bad(f"{m} — erwartet {want!r}, bekam {got!r}")


from chimera.display import led as ledmod  # noqa: E402
from chimera.display.led import LedVerwalter, MUSTER  # noqa: E402

GLOW = (100, 200, 50)

print("== Verwalter ==")
v = LedVerwalter()
check("ohne Meldung: gedimmter Glow", v.farbe(0, glow=GLOW), MUSTER["gedimmt"](0, GLOW))
check("ohne Meldung: keine Quelle", v.quelle(0), None)

v.melden("hoert", jetzt_ms=0)
check("hoert: blau, fest", v.farbe(10, glow=GLOW), (0, 90, 255))

v.melden("hitze", jetzt_ms=5, laufzeit_ms=1000)
check("hoehere Prioritaet gewinnt (hitze vor hoert)", v.quelle(10), "hitze")
check("nach Ablauf zurueck zu hoert", v.quelle(2000), "hoert")

v.melden("hoert", jetzt_ms=3000, farbe=(1, 2, 3))
check("Update derselben Quelle verdraengt (ein Platz je Quelle)", v.farbe(3001, glow=GLOW), (1, 2, 3))
check("zuruecknehmen", v.zuruecknehmen("hoert"), True)
check("nach Zuruecknahme: Grundzustand", v.quelle(3002), None)

# Glow-Quellen: None-Farbe heisst "Glow des Gesichts".
v2 = LedVerwalter()
v2.melden("agentenstatus", jetzt_ms=0)
# Puls bei t = halbe Periode (800 ms von 1600) = volle Helligkeit: dann
# muss genau der Glow herauskommen -- keine Formel, ein bekannter Punkt.
check("agentenstatus nutzt den Glow (Pulsspitze = Glow)", v2.farbe(800, glow=GLOW), GLOW)
check("agentenstatus mit anderem Glow folgt ihm", v2.farbe(800, glow=(10, 20, 30)), (10, 20, 30))

try:
    v2.melden("gibtsnicht", jetzt_ms=0)
    bad("unbekannte Quelle haette KeyError geben muessen")
except KeyError:
    ok("unbekannte Quelle wird abgelehnt, nicht geraten")
try:
    v2.melden("hoert", jetzt_ms=0, muster="disko")
    bad("unbekanntes Muster haette KeyError geben muessen")
except KeyError:
    ok("unbekanntes Muster wird abgelehnt")

print("== Muster: reine Funktionen der Zeit (Regel 7d) ==")
for name, f in MUSTER.items():
    a, b = f(1234, (200, 100, 50)), f(1234, (200, 100, 50))
    check(f"{name}: gleiche Zeit, gleiches Ergebnis", a, b)
check("blink: an in der ersten Haelfte", MUSTER["blink"](100, (9, 9, 9)), (9, 9, 9))
check("blink: aus in der zweiten Haelfte", MUSTER["blink"](500, (9, 9, 9)), (0, 0, 0))
_p = [MUSTER["puls"](t, (200, 200, 200))[0] for t in range(0, 1600, 100)]
check("puls: aendert sich ueber die Zeit", len(set(_p)) > 3, True)
check("puls: nie ganz aus", min(_p) > 0, True)

print("== Abstandsregel (Regel 7c) ==")
from chimera.arbiter import Arbiter  # noqa: E402
check("Katalog haelt Abstaende >= 10", Arbiter.abstaende_pruefen(ledmod.QUELLEN), [])
check("jede Quelle hat eine Darstellung", sorted(ledmod.DARSTELLUNG), sorted(ledmod.QUELLEN))

print("== anwenden: nur bei Aenderung ==")


class MerkPanel:
    width, height, fps = 240, 280, 15

    def __init__(self):
        self.leds = []
        self.bilder = 0

    def led(self, r, g, b):
        self.leds.append((r, g, b))

    def show(self, img):
        self.bilder += 1


mp = MerkPanel()
v3 = LedVerwalter()
v3.anwenden(mp, 0, glow=GLOW)
v3.anwenden(mp, 66, glow=GLOW)
check("gleiche Farbe zweimal: ein led()-Aufruf", len(mp.leds), 1)
v3.melden("hoert", jetzt_ms=100)
v3.anwenden(mp, 133, glow=GLOW)
check("neue Farbe: zweiter Aufruf", mp.leds[-1], (0, 90, 255))
v3.aus(mp)
check("aus: LED dunkel", mp.leds[-1], (0, 0, 0))

print("== Verdrahtung: build() -> Renderer -> Panel ==")
from chimera import app  # noqa: E402
from chimera.render.avatar import NoisyRenderer, State  # noqa: E402

# _try_zeile_und_led mit hohem Panel (Whisplay-Masse): beide entstehen und
# haengen am Renderer -- dieselben Exemplare, nicht Kopien.
from chimera.display.panel import NullPanel  # noqa: E402
np_hoch = NullPanel(240, 280)
r = NoisyRenderer(State(), np_hoch)
notes = []
sl, ld = app._try_zeile_und_led(r, np_hoch, notes)
check("hohes Panel: Statuszeile angelegt", sl is not None, True)
check("Statuszeile haengt am Renderer (dasselbe Exemplar)", r.statusline is sl, True)
check("Statuszeilenhoehe = Hoehe - Breite", sl.hoehe if sl else None, 40)
check("LED haengt am Renderer (dasselbe Exemplar)", r.led is ld, True)
check("keine Fehlernotizen", notes, [])

np_quadrat = NullPanel(240, 240)
r2 = NoisyRenderer(State(), np_quadrat)
sl2, ld2 = app._try_zeile_und_led(r2, np_quadrat, [])
check("quadratisches Panel: keine Statuszeile", sl2, None)
check("quadratisches Panel: LED trotzdem", ld2 is not None, True)
check("ohne Renderer: nichts", app._try_zeile_und_led(None, np_hoch, []), (None, None))

# renderer.show() setzt die LED auf das Panel
mp2 = MerkPanel()
r3 = NoisyRenderer(State(), mp2)
r3.led = LedVerwalter()
r3.led.melden("hoert", jetzt_ms=0)
r3.show()
check("renderer.show(): Bild ausgegeben", mp2.bilder, 1)
check("renderer.show(): LED gesetzt (hoert = blau)", mp2.leds[-1] if mp2.leds else None, (0, 90, 255))

print("== Zustand -> Zeile UND LED ==")
sl4 = sl
ld4 = LedVerwalter()
app.zustand_melden("hoert", statusline=sl4, led=ld4, jetzt_ms=1000)
check("hoert: Zeile", sl4.text(1001), "hoert zu")
check("hoert: LED", ld4.quelle(1001), "hoert")
app.zustand_melden("spricht", statusline=sl4, led=ld4, jetzt_ms=2000)
check("spricht verdraengt hoert auf der LED", ld4.quelle(2001), "spricht")
check("spricht: Zeile", sl4.text(2001), "spricht")
app.zustand_melden("wartet", statusline=sl4, led=ld4, jetzt_ms=3000)
# Seit dem Grundinhalt (DESIGN §5) ist die Zeile nach "wartet" nicht leer,
# sondern zeigt den Namen des Ausdrucks -- entscheidend ist, dass der
# Agentenzustand weg ist.
check("wartet: Agentenzustand zurueckgenommen (Grundinhalt)", sl4.quelle(3001), "leerlauf")
check("wartet: LED im Grundzustand", ld4.quelle(3001), None)
app.zustand_melden("denkt", statusline=sl4, led=ld4, jetzt_ms=4000)
check("Netz: Zustand verfaellt nach 30 s", ld4.quelle(4000 + 30_001), None)

print("== Taste quittiert per LED ==")


class TastenPanel(MerkPanel):
    def bei_taste(self, cb):
        self.cb = cb


chi = app.Chimera.__new__(app.Chimera)
chi.led = LedVerwalter()
chi.statusline = None
chi.face = None
import time as _time
_t0 = int(_time.monotonic() * 1000)
app.Chimera._on_taste(chi, True)
check("Tastendruck: LED-Quelle taste", chi.led.quelle(_t0 + 50), "taste")
# Die Quittung blinkt (blink_schnell); ein einzelner Zeitpunkt waere je nach
# Phase hell oder dunkel. Darum das ganze Fenster abtasten.
_fenster = {chi.led.farbe(_t0 + dt, glow=GLOW) for dt in range(0, app.TASTE_QUITTUNG_MS, 20)}
check("Tastendruck: weiss im Quittungsfenster", (255, 255, 255) in _fenster, True)
check("Tastendruck: nach der Quittung vorbei", chi.led.quelle(_t0 + 2000), None)
app.Chimera._on_taste(chi, False)
ok("Loslassen: kein Fehler")

print()
print(f"Ergebnis: {PASS} ok, {FAIL} fehlgeschlagen")
sys.exit(1 if FAIL else 0)
