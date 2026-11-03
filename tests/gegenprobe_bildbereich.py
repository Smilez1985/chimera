#!/usr/bin/env python3
"""Gegenprobe zu test_bildbereich.py (Regel 9): je eine Zusage verfälschen.

M1 ist der alte Zustand: immer das ganze Bild übertragen. Genau so lief
Chimera bis 3.11.2026 — 572 `write()` je Sekunde im Leerlauf, und kein Test
sah es.
"""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TEST = REPO / "tests" / "test_bildbereich.py"
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


print("=== Gegenprobe geänderte Bereiche ===")

rc, aus = lauf(REPO / "src")
ok("unverändert grün") if rc == 0 else bad("unverändert schon rot — nicht aussagekräftig")

# M1: Alter Zustand — der Vergleich fällt weg, es geht immer alles raus.
mutation("voller-rahmen-immer", "chimera/displays/base.py",
         "    if alt == neu:\n        return []",
         "    if True:\n        return [(0, 0, breite, hoehe)]",
         "gleiche Bilder: kein Rechteck")

# M2: Spalten als Byte-Offset (die Achse über beide Bytes fehlt) — das Fenster
# landet an der doppelten Stelle und ist doppelt so breit.
mutation("spalten-in-bytes", "chimera/displays/base.py",
         "anders[oben:unten + 1].any(axis=(0, 2))",
         "anders[oben:unten + 1].any(axis=0)",
         "ein Punkt: genau ein Rechteck, 1×1")

# M3: Alle geänderten Zeilen in EINEN Streifen — überträgt die Lücken mit.
mutation("ein-streifen", "chimera/displays/base.py",
         "        if y == streifen[-1][-1] + 1:",
         "        if True:",
         "zwei Streifen: zwei Rechtecke, je eigener Spanne")

# M4: Der Ausschnitt ignoriert die Spalte — schreibt die falschen Bildpunkte.
mutation("ausschnitt-ohne-x", "chimera/displays/base.py",
         "        return a[y:y + h, x * 2:(x + w) * 2].tobytes()",
         "        return a[y:y + h, 0:(w) * 2].tobytes()",
         "Ausschnitt mitten im Bild")

# M5: Alter Zustand im Panel — kein Vergleich, jedes Bild geht voll raus.
mutation("panel-immer-voll", "chimera/displays/whisplay/panel.py",
         "        if letztes is not None and len(letztes) == len(rgb):",
         "        if False:",
         "gleiches Bild nochmal: KEIN Schreibaufruf")

print(f"\nErgebnis: {PASS} ok, {FAIL} fehlgeschlagen")
sys.exit(0 if FAIL == 0 else 1)
