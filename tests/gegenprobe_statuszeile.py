#!/usr/bin/env python3
"""Gegenprobe zu test_statuszeile_inhalt.py (Regel 9): Je eine Zusage wird in
einer KOPIE des Quellbaums verfaelscht; der Test muss rot werden, am
erwarteten Punkt.

M1 ist der alte Zustand: kein Grundinhalt -- genau so lief Chimera bis
11.10.2026 am Geraet, und die Zeile blieb unsichtbar.
"""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TEST = REPO / "tests" / "test_statuszeile_inhalt.py"
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
    env = dict(os.environ, PYTHONPATH=str(src), CHIMERA_SRC=str(src),
               PYTHONDONTWRITEBYTECODE="1")
    r = subprocess.run([sys.executable, str(TEST)], env=env, capture_output=True,
                       text=True, timeout=300)
    return r.returncode, r.stdout + r.stderr

def mutation(name: str, datei: str, alt: str, neu: str, erwartet: str, *,
             roh: bool = False) -> None:
    """``erwartet`` ist der Name der Pruefung, die rot werden muss -- oder,
    mit ``roh=True``, ein Text, der in der Ausgabe stehen muss (Absturz)."""
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
        treffer = (erwartet in aus) if roh else (f"FAIL  {erwartet}" in aus)
        if rc == 0:
            bad(f"{name}: Test blieb gruen")
        elif treffer:
            ok(f"{name}: rot bei '{erwartet}'")
        else:
            bad(f"{name}: rot, aber nicht bei '{erwartet}'")
            for z in aus.splitlines():
                if "FAIL" in z or "Error" in z:
                    print("        " + z.strip())

print("=== Gegenprobe Statuszeilen-Inhalt ===")
rc, aus = lauf(REPO / "src")
if rc == 0:
    ok("unveraendert gruen")
else:
    bad("unveraendert schon rot -- Gegenprobe nicht aussagekraeftig")
    print(aus[-800:])

# M1: alter Zustand -- build gibt der Zeile keinen Grundinhalt.
mutation("kein-grundtext", "chimera/app.py",
         "                grundtext=lambda: getattr(zustand, \"mood_name\", \"\") or \"\")",
         "                grundtext=None)",
         "ohne Meldung: Grundtext = Name des Ausdrucks — erwartet 'IDLE', bekam None")

# M2: alte Schrift -- Pillows Bitmapschrift (rund 10 px).
mutation("kleine-schrift", "chimera/display/statusline.py",
         "        self._schrift = schrift if schrift is not None else _schrift_laden(\n"
         "            max(10, int(self.hoehe * 0.45)))",
         "        self._schrift = schrift",
         "Schrift gross genug")

# M3: Grundtext als zweite Quelle -- fester Text statt Zustand des Renderers.
mutation("grundtext-fest", "chimera/app.py",
         "                grundtext=lambda: getattr(zustand, \"mood_name\", \"\") or \"\")",
         "                grundtext=lambda: \"IDLE\")",
         "folgt dem Zustand des Renderers (keine zweite Quelle)")

# M4: Grundtext ueberstimmt Meldungen (Rueckfall-Logik verdreht).
mutation("grundtext-gewinnt", "chimera/display/statusline.py",
         "        if g is not None or self._grundtext is None:\n            return g",
         "        if self._grundtext is None:\n            return g",
         "Meldung gewinnt")

# M5: Anbieterausfall wird nicht gemeldet.
mutation("anbieter-stumm", "chimera/app.py",
         "                self.statusline.melden(\"anbieter_weg\", \"kein Sprachmodell\", jetzt_ms=jetzt)",
         "                pass",
         "ohne Anbieter: Zeile nennt es")

# M6: Dienst prueft den Anbieter nicht.
mutation("dienst-ohne-pruefung", "chimera/__main__.py",
         "        if melden is not None:\n            melden()\n        while",
         "        while",
         "Dienst prueft den Anbieter beim Start")

# M7: Taste wieder fest weiss (nur "heller", kein Wechsel).
mutation("taste-fest", "chimera/display/led.py",
         "    \"taste\":        ((255, 255, 255), \"blink_schnell\"),",
         "    \"taste\":        ((255, 255, 255), \"fest\"),",
         "Quittung: dunkel kommt vor (Wechsel, nicht nur heller)")

# M8: Quittung wieder 300 ms (ein Blitz).
mutation("taste-kurz", "chimera/app.py",
         "TASTE_QUITTUNG_MS = 720",
         "TASTE_QUITTUNG_MS = 300",
         "Quittung lang genug fuer mehrere Blitze (>= 600 ms)")

# M9: kaputter Grundtext reisst das Zeichnen mit.
mutation("grundtext-ungefangen", "chimera/display/statusline.py",
         "        try:\n            text = self._grundtext()\n        except Exception:\n"
         "            # Ein kaputter Grundtext darf kein Bild aufhalten (Regel 8a:\n"
         "            # sichtbar wird es daran, dass die Zeile leer bleibt).\n"
         "            return None",
         "        text = self._grundtext()",
         "RuntimeError: kaputt", roh=True)

# M10: Puffer prueft den Text nicht -- ein alter Streifen bleibt stehen.
mutation("puffer-veraltet", "chimera/display/statusline.py",
         "            if self._streifen is None or self._streifen_schluessel != schluessel:",
         "            if self._streifen is None:",
         "neuer Text: neu gezeichnet (kein veralteter Text)")

# M11: kein Puffer -- jedes Bild neu (Wirkung gleich, aber teuer).
mutation("ohne-puffer", "chimera/display/statusline.py",
         "            if self._streifen is None or self._streifen_schluessel != schluessel:",
         "            if True:",
         "gleicher Text: Streifen wiederverwendet (kein Neuzeichnen)")

print()
print(f"Ergebnis: {PASS} ok, {FAIL} fehlgeschlagen")
sys.exit(1 if FAIL else 0)
