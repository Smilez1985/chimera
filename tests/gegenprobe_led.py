#!/usr/bin/env python3
"""Gegenprobe zu test_led.py (Regel 9): Je eine Zusage wird in einer KOPIE
des Quellbaums verfaelscht; der Test muss rot werden, am erwarteten Punkt.

Besonders M1: der alte Zustand -- Statuszeile wird nicht an den Renderer
gegeben. Genau so lief Chimera bis 11.10.2026, und kein Test sah es.
"""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TEST = REPO / "tests" / "test_led.py"
PASS = FAIL = 0


def ok(m):
    global PASS
    PASS += 1
    print(f"  ok    {m}")


def bad(m):
    global FAIL
    FAIL += 1
    print(f"  FAIL  {m}")


def lauf(src: Path) -> tuple[int, str]:
    env = dict(os.environ, PYTHONPATH=str(src), CHIMERA_SRC=str(src))
    r = subprocess.run([sys.executable, str(TEST)], env=env, capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


def mutation(name: str, datei: str, alt: str, neu: str, erwartet: str) -> None:
    with tempfile.TemporaryDirectory() as d:
        src = Path(d) / "src"
        shutil.copytree(REPO / "src", src)
        ziel = src / datei
        text = ziel.read_text(encoding="utf-8")
        if text.count(alt) != 1:
            bad(f"{name}: Muster {text.count(alt)}x in {datei} (erwartet genau 1)")
            return
        ziel.write_text(text.replace(alt, neu), encoding="utf-8")
        rc, aus = lauf(src)
        if rc == 0:
            bad(f"{name}: Test blieb gruen")
        elif f"FAIL  {erwartet}" in aus:
            ok(f"{name}: rot bei '{erwartet}'")
        else:
            bad(f"{name}: rot, aber nicht bei '{erwartet}'")
            for z in aus.splitlines():
                if "FAIL" in z or "Error" in z:
                    print("        " + z.strip())


print("=== Gegenprobe LED und Verdrahtung ===")
rc, aus = lauf(REPO / "src")
if rc == 0:
    ok("unveraendert gruen")
else:
    bad("unveraendert schon rot -- Gegenprobe nicht aussagekraeftig")
    print(aus[-600:])

# M1: Statuszeile entsteht, wird aber nicht an den Renderer gegeben (alter Zustand).
mutation("zeile-nicht-angeschlossen", "chimera/app.py",
         "            renderer.statusline = statusline\n", "",
         "Statuszeile haengt am Renderer (dasselbe Exemplar)")

# M2: Renderer setzt die LED nicht.
mutation("renderer-ohne-led", "chimera/render/avatar.py",
         "                self.led.anwenden(self.panel, jetzt_ms,\n                                  glow=tuple(self.current_glow_color))",
         "                pass",
         "renderer.show(): LED gesetzt (hoert = blau)")

# M3: Zustand erreicht nur das Gesicht, nicht Zeile/LED.
mutation("zustand-nur-gesicht", "chimera/app.py",
         "    if statusline is not None:\n        statusline.melden(\"agentenstatus\", text, jetzt_ms=jetzt, laufzeit_ms=30_000)",
         "    if False:\n        pass",
         "hoert: Zeile")

# M4: kein Netz -- Zustand ohne Laufzeit leuchtet ewig.
mutation("zustand-ohne-laufzeit", "chimera/app.py",
         "        led.melden(led_quelle, jetzt_ms=jetzt, laufzeit_ms=30_000)",
         "        led.melden(led_quelle, jetzt_ms=jetzt, laufzeit_ms=None)",
         "Netz: Zustand verfaellt nach 30 s")

# M5: Muster mit eigener Uhr (Regel 7d verletzt): puls liest time.time().
mutation("muster-eigene-uhr", "chimera/display/led.py",
         "    phase = (t_ms % periode_ms) / periode_ms",
         "    import time as _tt; phase = ((int(_tt.time() * 1000)) % periode_ms) / periode_ms",
         "agentenstatus nutzt den Glow (Pulsspitze = Glow)")

# M6: anwenden setzt bei jedem Bild, auch ohne Aenderung.
mutation("led-jedes-bild", "chimera/display/led.py",
         "        if f != self._letzte:",
         "        if True:",
         "gleiche Farbe zweimal: ein led()-Aufruf")

# M7: Taste quittiert nicht.
mutation("taste-stumm", "chimera/app.py",
         "            self.led.melden(\"taste\", jetzt_ms=int(_t.monotonic() * 1000), laufzeit_ms=300)",
         "            pass",
         "Tastendruck: LED-Quelle taste")

print()
print(f"Ergebnis: {PASS} ok, {FAIL} fehlgeschlagen")
sys.exit(1 if FAIL else 0)
