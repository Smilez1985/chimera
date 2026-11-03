#!/usr/bin/env python3
"""LED-Takt messen: getrennte Faeden gegen einen gemeinsamen Takt.

Gemessen wird die CPU-Zeit des eigenen Prozesses (/proc/self/stat, Felder
14+15) ueber 20 s -- unabhaengig davon, wie ausgelastet das Geraet sonst
ist. Die Schreibfunktion der Leitungen ist eine Leerfunktion, damit der
Takt gemessen wird und nicht der Bus.

    python3 tools/pwm-vergleich.py <pfad/softpwm.py> einzel 50 50 50

`gruppe` setzt eine `softpwm.py` mit `SoftPWMGruppe` voraus -- die Fassung
wurde am 3.11.2026 gemessen und verworfen (Begruendung und Zahlen:
docs/research/LED-TAKT.md); mit dem heutigen `softpwm.py` gibt es sie
nicht mehr, `einzel` laeuft aber weiter.
"""

from __future__ import annotations

import importlib.util
import os
import sys
import time


def laden(pfad: str, name: str):
    spec = importlib.util.spec_from_file_location(name, pfad)
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


def cpu() -> float:
    felder = open("/proc/self/stat", encoding="ascii").read().split()
    return (int(felder[13]) + int(felder[14])) / os.sysconf("SC_CLK_TCK")


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    pfad, art = sys.argv[1], sys.argv[2]
    tast = [float(x) for x in sys.argv[3:]] or [50.0, 50.0, 50.0]
    sekunden = 20

    m = laden(pfad, "pwmmodul")
    if art == "einzel":
        objekte = [m.SoftPWM(lambda v: None, frequenz_hz=60, aktiv_low=True)
                   for _ in tast]
        for o, tg in zip(objekte, tast):
            o.start(tg)
        start = lambda: None                      # noqa: E731
        stop = lambda: [o.stop() for o in objekte]  # noqa: E731
    else:
        gruppe = m.SoftPWMGruppe(frequenz_hz=60)
        for tg in tast:
            gruppe.kanal(lambda v: None, aktiv_low=True, tastgrad=tg)
        start = gruppe.start
        stop = gruppe.stop

    start()
    a = cpu()
    t0 = time.monotonic()
    time.sleep(sekunden)
    b = cpu()
    d = time.monotonic() - t0
    stop()
    print(f"{art:8s} {str(tast):18s} {b - a:6.3f} s CPU in {d:.1f} s "
          f"= {(b - a) / d * 100:5.2f} % eines Kerns")
    return 0


if __name__ == "__main__":
    sys.exit(main())
