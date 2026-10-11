#!/usr/bin/env python3
"""Tests fuer SoftPWM (src/chimera/displays/softpwm.py).

Gemessen werden die Schreibzugriffe auf die Leitung -- ohne GPIO, ueber
eine Funktion, die mitzaehlt. Zusagen:

* 0 % und 100 %: der Pegel wird gesetzt und dann NICHT mehr laufend neu
  geschrieben (vorher: je Periode ein Schreibzugriff, 1000/s bei 1 kHz;
  gemessen 4,8 % eines Kerns am chimera-pi fuer ein Backlight auf 100 %)
* aktiv_low: 100 % heisst Leitung unten
* Wechsel des Tastgrads weckt den Faden sofort
* Zwischenwerte takten (beide Pegel kommen vor)
* stop setzt den Endpegel und beendet den Faden

Gegenprobe: die alte Schleife (Takt auch bei festem Pegel) -- dann muss
"kein Dauerschreiben" rot werden.
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


from chimera.displays.softpwm import SoftPWM  # noqa: E402


class Leitung:
    def __init__(self):
        self.werte = []
        self.lock = threading.Lock()

    def __call__(self, v):
        with self.lock:
            self.werte.append(v)

    def anzahl(self):
        with self.lock:
            return len(self.werte)

    def letzter(self):
        with self.lock:
            return self.werte[-1] if self.werte else None


print("== fester Pegel: einmal setzen, nicht takten ==")
l = Leitung()
p = SoftPWM(l, frequenz_hz=1000, aktiv_low=True)
p.start(100)
time.sleep(0.05)
check("100 % aktiv_low: Leitung unten", l.letzter(), 0)
n1 = l.anzahl()
time.sleep(0.2)
n2 = l.anzahl()
check("100 %: kein Dauerschreiben (0 Schreibzugriffe in 200 ms)", n2 - n1, 0)

p.setze_tastgrad(0)
time.sleep(0.05)
check("Wechsel auf 0 % weckt sofort: Leitung oben (aktiv_low)", l.letzter(), 1)
n3 = l.anzahl()
time.sleep(0.2)
check("0 %: kein Dauerschreiben", l.anzahl() - n3, 0)

print("== Zwischenwert taktet ==")
p.setze_tastgrad(50)
time.sleep(0.1)
with l.lock:
    neu = l.werte[n3:]
check("50 %: beide Pegel kommen vor", sorted(set(neu)), [0, 1])
check("50 %: es wird getaktet (> 20 Wechsel in 100 ms bei 1 kHz)", len(neu) > 20, True)

print("== gleicher Tastgrad weckt nicht ==")
p.setze_tastgrad(100)
time.sleep(0.05)
n4 = l.anzahl()
p.setze_tastgrad(100)
time.sleep(0.05)
check("erneut 100 %: kein Schreibzugriff", l.anzahl() - n4, 0)

print("== stop ==")
p.stop(endpegel_an=False)
check("stop: Endpegel aus (aktiv_low = oben)", l.letzter(), 1)
check("stop: Faden beendet", p._faden, None)

l2 = Leitung()
p2 = SoftPWM(l2, frequenz_hz=100, aktiv_low=False)
p2.start(100)
time.sleep(0.03)
check("aktiv_high 100 %: Leitung oben", l2.letzter(), 1)
p2.stop(endpegel_an=False)
check("aktiv_high stop aus: Leitung unten", l2.letzter(), 0)

print()
print(f"Ergebnis: {PASS} ok, {FAIL} fehlgeschlagen")
sys.exit(1 if FAIL else 0)
