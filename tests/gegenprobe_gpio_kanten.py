#!/usr/bin/env python3
"""Gegenprobe zu test_gpio_kanten.py (Regel 9): je eine Zusage verfälschen.

M1 ist der alte Zustand: keine Kanten, kein Ereignispuffer — die Taste wurde
im Takt abgefragt (200 ioctls je Sekunde, 1,3 % eines Kerns am Pi).
"""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TEST = REPO / "tests" / "test_gpio_kanten.py"
PASS = FAIL = 0

def ok(m):
    global PASS; PASS += 1; print(f"  ok    {m}")

def bad(m):
    global FAIL; FAIL += 1; print(f"  FAIL  {m}")

def lauf(src: Path) -> tuple[int, str]:
    env = dict(os.environ, PYTHONPATH=str(src), CHIMERA_SRC=str(src))
    r = subprocess.run([sys.executable, str(TEST)], env=env,
                       capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr

def mutation(name, datei, alt, neu, erwartet):
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
            bad(f"{name}: Test blieb grün")
        elif f"FAIL  {erwartet}" in aus:
            ok(f"{name}: rot bei '{erwartet}'")
        else:
            bad(f"{name}: rot, aber nicht bei '{erwartet}'")
            for zeile in aus.splitlines():
                if "FAIL" in zeile:
                    print("        " + zeile.strip())

DATEI = "chimera/displays/gpio.py"

print("=== Gegenprobe Kantenereignisse ===")

rc, aus = lauf(REPO / "src")
ok("unverändert grün") if rc == 0 else bad("unverändert schon rot — nicht aussagekräftig")

# M1: Alter Zustand — kein Ereignispuffer, also keine Kanten vom Kernel.
mutation("kein-ereignispuffer", DATEI,
         "            anfrage.event_buffer_size = 16",
         "            anfrage.event_buffer_size = 0",
         "Ereignispuffer angefragt")

# M2: Falsches Bit — das ist das Ausgangsflag, der Kernel liefe in EINVAL.
mutation("falsches-kantenflag", DATEI,
         "FLAG_EDGE_RISING = 1 << 4",
         "FLAG_EDGE_RISING = 1 << 3",
         "Kantenflag steigend")

# M3: Flanken-IDs vertauscht — jede Taste käme als Loslassen an.
mutation("flanken-vertauscht", DATEI,
         "EREIGNIS_FALLEND = 2",
         "EREIGNIS_FALLEND = 1",
         "fallende Flanke ist 2")

# M4: Filter weg — jedes Ereignis gilt als das gesuchte.
mutation("ohne-filter", DATEI,
         "            if offset is not None and ereignis.offset != offset:\n"
         "                self._puffer.append((ereignis.offset, art))\n"
         "                continue",
         "            if False:\n"
         "                self._puffer.append((ereignis.offset, art))\n"
         "                continue",
         "fremde Leitung wird gefiltert")

# M5: Fremde Ereignisse werden verworfen statt aufgehoben.
mutation("puffer-verworfen", DATEI,
         "            if offset is not None and ereignis.offset != offset:\n"
         "                self._puffer.append((ereignis.offset, art))\n"
         "                continue",
         "            if offset is not None and ereignis.offset != offset:\n"
         "                continue",
         "ohne Filter kommt sie")

# M6: Kante auf einem Ausgang wird nicht abgewiesen.
mutation("kante-auf-ausgang", DATEI,
         "        ohne_eingang = [o for o in kanten if o not in eingaenge]",
         "        ohne_eingang = []",
         "Kante auf einem Ausgang — erwartet ValueError, bekam keinen")

# M7: Ohne Kanten still nichts liefern (der Fehler, der niemandem auffällt).
mutation("ohne-kanten-still", DATEI,
         '        if not self._kanten:\n'
         '            raise RuntimeError("keine Kanten angefordert "',
         '        if False:\n'
         '            raise RuntimeError("keine Kanten angefordert "',
         "ohne Kanten — erwartet RuntimeError, bekam keinen")

print(f"\nErgebnis: {PASS} ok, {FAIL} fehlgeschlagen")
sys.exit(0 if FAIL == 0 else 1)
