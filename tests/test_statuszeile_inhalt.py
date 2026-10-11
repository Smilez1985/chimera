#!/usr/bin/env python3
"""Was steht in der Statuszeile, wenn niemand etwas meldet? (DESIGN §5, Regel 7c)

Am Geraet (smilez, 11.10.2026): "Statusleiste sehe ich nicht". Die Zeile
war angeschlossen, aber es meldete nie jemand etwas -- nur Agentenzustaende,
und ohne Sprachmodell laeuft der Agent nie. Dazu Pillows Bitmapschrift
(rund 10 px) und ein Grau, das nach dem Dimmen im Schwarz verschwand.

Geprueft wird die WIRKUNG im ausgegebenen Bild, nicht die Anwesenheit:

* build-Pfad (``_try_zeile_und_led``): ohne jede Meldung steht der Name des
  Ausdrucks unten im Bild -- gelesen aus dem Zustand des Renderers.
* Meldungen verdraengen den Grundinhalt, Zuruecknehmen bringt ihn zurueck.
* Die Schrift ist gross genug: Glyphen hoeher als 12 px.
* ``anbieter_melden``: ohne Anbieter steht "kein Sprachmodell", mit wieder
  der Grundinhalt.
* Dienst: prueft die Anbieter beim Start und meldet es der Zeile.
* Taste: die LED-Quittung wechselt hell/dunkel (nicht nur "heller").

Gegenproben in tests/gegenprobe_statuszeile.py.
"""

import os
import sys
import threading
import time
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

from PIL import Image  # noqa: E402

from chimera import app  # noqa: E402
from chimera.display import statusline as slmod  # noqa: E402
from chimera.display.led import LedVerwalter  # noqa: E402
from chimera.display.panel import NullPanel  # noqa: E402
from chimera.render.avatar import NoisyRenderer, State  # noqa: E402

class MerkPanel(NullPanel):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.letztes = None
        self.leds = []

    def show(self, img):
        self.letztes = img.copy() if img is not None else None
        return super().show(img)

    def led(self, r, g, b):
        self.leds.append((r, g, b))

def zeilen_pixel(bild, oben=240, farbe=None, toleranz=45):
    """Bildpunkte im unteren Rand, die nicht (fast) schwarz sind -- oder,
    mit ``farbe``, die dieser Farbe aehneln."""
    n = 0
    for y in range(oben, bild.height):
        for x in range(0, bild.width):
            p = bild.getpixel((x, y))
            if farbe is None:
                if max(p) > 60:
                    n += 1
            elif all(abs(p[i] - farbe[i]) < toleranz for i in range(3)):
                n += 1
    return n

def glyphen_hoehe(bild, oben=240):
    """Hoehe des Textes im unteren Rand: erste bis letzte Zeile mit hellen Punkten."""
    zeilen = [y for y in range(oben, bild.height)
              if any(max(bild.getpixel((x, y))) > 100 for x in range(bild.width))]
    return (zeilen[-1] - zeilen[0] + 1) if zeilen else 0

print("== Grundinhalt ueber den build-Pfad ==")
mp = MerkPanel(240, 280)
r = NoisyRenderer(State(), mp)
sl, ld = app._try_zeile_und_led(r, mp, [])
check("Zeile angelegt", sl is not None, True)
check("ohne Meldung: Grundtext = Name des Ausdrucks", sl.text(0) if sl else None, "IDLE")
check("ohne Meldung: Quelle leerlauf", sl.quelle(0) if sl else None, "leerlauf")
r.show()
grund_n = zeilen_pixel(mp.letztes)
check("ohne Meldung steht etwas im unteren Rand (Bild)", grund_n > 30, True)
h = glyphen_hoehe(mp.letztes)
check(f"Schrift gross genug (Glyphen {h} px > 12 px)", h > 12, True)

r.state.mood_name = "CHILL"
check("folgt dem Zustand des Renderers (keine zweite Quelle)", sl.text(0), "CHILL")

print("== Meldungen verdraengen den Grundinhalt ==")
sl.melden("agentenstatus", "denkt nach", jetzt_ms=1000)
check("Meldung gewinnt", sl.text(1001), "denkt nach")
sl.zuruecknehmen("agentenstatus")
check("zurueckgenommen: wieder Grundtext", sl.text(1002), "CHILL")
sl.melden("antwort", "kurz", jetzt_ms=2000, laufzeit_ms=100)
check("abgelaufene Meldung: wieder Grundtext", sl.text(2200), "CHILL")

print("== Puffer: zeichnet nur bei Aenderung neu, aber dann sicher ==")
ps = slmod.StatusLine(hoehe=40, grundtext=lambda: "IDLE")
b1 = Image.new("RGB", (240, 280), (0, 0, 0))
ps.zeichnen(b1, jetzt_ms=0)
streifen1 = ps._streifen
b2 = Image.new("RGB", (240, 280), (0, 0, 0))
ps.zeichnen(b2, jetzt_ms=1)
check("gleicher Text: Streifen wiederverwendet (kein Neuzeichnen)", ps._streifen is streifen1, True)
check("gleicher Text: gleiches Bild", b1.tobytes() == b2.tobytes(), True)
ps.melden("agentenstatus", "denkt nach", jetzt_ms=2)
b3 = Image.new("RGB", (240, 280), (0, 0, 0))
ps.zeichnen(b3, jetzt_ms=3)
check("neuer Text: neu gezeichnet (kein veralteter Text)",
      b3.crop((0, 240, 240, 280)).tobytes() != b1.crop((0, 240, 240, 280)).tobytes(), True)
frisch = slmod.StatusLine(hoehe=40, grundtext=lambda: "IDLE")
frisch.melden("agentenstatus", "denkt nach", jetzt_ms=2)
b4 = Image.new("RGB", (240, 280), (0, 0, 0))
frisch.zeichnen(b4, jetzt_ms=3)
check("Puffer zeichnet genau wie ungepuffert", b3.tobytes() == b4.tobytes(), True)
ps.zuruecknehmen("agentenstatus")
b5 = Image.new("RGB", (240, 280), (0, 0, 0))
ps.zeichnen(b5, jetzt_ms=4)
check("zurueck zum alten Text: wieder wie vorher", b5.tobytes() == b1.tobytes(), True)
b6 = Image.new("RGB", (240, 280), (9, 9, 9))
ps.zeichnen(b6, jetzt_ms=5)
check("Puffer zeichnet nur den unteren Rand", b6.getpixel((120, 100)), (9, 9, 9))

print("== Grundtext robust ==")
def kaputt():
    raise RuntimeError("kaputt")
s2 = slmod.StatusLine(hoehe=40, grundtext=kaputt)
check("kaputter Grundtext: leer statt Absturz", s2.text(0), None)
bild = Image.new("RGB", (240, 280), (5, 5, 5))
s2.zeichnen(bild, jetzt_ms=0)
check("kaputter Grundtext: nichts gezeichnet", bild.getpixel((120, 260)), (5, 5, 5))
s3 = slmod.StatusLine(hoehe=40, grundtext=lambda: "")
check("leerer Grundtext: keine Zeile", s3.text(0), None)
s4 = slmod.StatusLine(hoehe=40)
check("ohne Grundtext: wie bisher leer", s4.text(0), None)

print("== Anbieterausfall ==")
class Reg:
    def __init__(self, n): self.n = n
    def available(self): return [object()] * self.n

chi = app.Chimera.__new__(app.Chimera)
chi.statusline = slmod.StatusLine(hoehe=40, grundtext=lambda: "IDLE")
chi.registry = Reg(0)
check("ohne Anbieter: rc False", app.Chimera.anbieter_melden(chi, jetzt_ms=0), False)
check("ohne Anbieter: Zeile nennt es", chi.statusline.text(1), "kein Sprachmodell")
check("ohne Anbieter: Quelle anbieter_weg", chi.statusline.quelle(1), "anbieter_weg")
bild = Image.new("RGB", (240, 280), (0, 0, 0))
chi.statusline.zeichnen(bild, jetzt_ms=1)
check("ohne Anbieter: Warnfarbe im Bild",
      zeilen_pixel(bild, farbe=slmod.STILE["anbieter_weg"].vordergrund) > 20, True)
chi.registry = Reg(1)
check("Anbieter wieder da: rc True", app.Chimera.anbieter_melden(chi, jetzt_ms=10), True)
check("Anbieter wieder da: Grundtext zurueck", chi.statusline.text(11), "IDLE")

class Kaputt:
    def available(self): raise RuntimeError("Netz weg")
chi.registry = Kaputt()
check("Pruefung wirft: gilt als nicht erreichbar", app.Chimera.anbieter_melden(chi, jetzt_ms=20), False)
check("Pruefung wirft: Zeile nennt es", chi.statusline.text(21), "kein Sprachmodell")

print("== Dienst meldet den Anbieter ==")
import chimera.__main__ as cm  # noqa: E402

class Geraet:
    def __init__(self):
        self.registry = Reg(0)
        self.renderer = None
        self.notes = []
        self.gemeldet = threading.Event()
    def start_display(self): return False
    def paint_once(self): pass
    def stop_display(self): pass
    def status(self): return ""
    def anbieter_melden(self):
        self.gemeldet.set()
        return False

g = Geraet()
stop = threading.Event()
erg = []
t = threading.Thread(target=lambda: erg.append(cm.dienst(g, stop=stop, env={})), daemon=True)
t.start()
check("Dienst prueft den Anbieter beim Start", g.gemeldet.wait(2), True)
stop.set()
t.join(2)
check("Dienst endet danach normal (rc 0)", erg, [0])

print("== Taste: Quittung wechselt hell/dunkel ==")
chi2 = app.Chimera.__new__(app.Chimera)
chi2.led = LedVerwalter()
chi2.statusline = None
chi2.face = None
GLOW = (15, 90, 110)
t0 = int(time.monotonic() * 1000)
app.Chimera._on_taste(chi2, True)
farben = {chi2.led.farbe(t0 + dt, glow=GLOW) for dt in range(0, app.TASTE_QUITTUNG_MS, 20)}
check("Quittung: weiss kommt vor", (255, 255, 255) in farben, True)
check("Quittung: dunkel kommt vor (Wechsel, nicht nur heller)", (0, 0, 0) in farben, True)
check("Quittung lang genug fuer mehrere Blitze (>= 600 ms)", app.TASTE_QUITTUNG_MS >= 600, True)
check("nach der Quittung: Grundzustand", chi2.led.quelle(t0 + app.TASTE_QUITTUNG_MS + 500), None)

print()
print(f"Ergebnis: {PASS} ok, {FAIL} fehlgeschlagen")
sys.exit(1 if FAIL else 0)
