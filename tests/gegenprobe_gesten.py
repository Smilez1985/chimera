#!/usr/bin/env python3
"""Gegenprobe zu test_gesten.py (Regel 9): je eine Zusage verfälschen.

Jede Mutation bricht genau eine Geste — bleibt der Test dabei grün, prüft er
die Zusage nicht.
"""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TEST = REPO / "tests" / "test_gesten.py"
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

DATEI = "chimera/display/gesten.py"

print("=== Gegenprobe Tastengesten ===")

rc, aus = lauf(REPO / "src")
ok("unverändert grün") if rc == 0 else bad("unverändert schon rot — nicht aussagekräftig")

# M1: Zwei Drücke gelten als einer.
mutation("doppelt-als-kurz", DATEI,
         "            elif klicks == 2:\n                ergebnis.append(DOPPELT)",
         "            elif klicks == 2:\n                ergebnis.append(KURZ)",
         "doppelt am Fensterende")

# M2: „halten" zu früh — schon bei der Kurzschwelle.
mutation("halten-zu-frueh", DATEI,
         "                and t >= self._unten_seit + self.halten_ab_s):",
         "                and t >= self._unten_seit + self.kurz_max_s):",
         "kurz vor der Schwelle noch nichts")

# M3: „lang" verschluckt — erst ab der Haltenschwelle.
mutation("lang-verschluckt", DATEI,
         "        if dauer >= self.kurz_max_s:",
         "        if dauer >= self.halten_ab_s:",
         "lang beim Loslassen")

# M4: Loslassen ohne Drücken wird als Klick gezählt.
mutation("loslassen-ohne-druecken", DATEI,
         "        if self._unten_seit is None:\n            return []",
         "        if self._unten_seit is None:\n"
         "            self._unten_seit = t - 0.1",
         "… und erzeugt später keinen Klick")

# M5: Der Klickzähler wird nicht zurückgesetzt — "kurz" feuert endlos.
mutation("zaehler-bleibt", DATEI,
         "            self._klick_frist = None\n"
         "            klicks, self._klicks = self._klicks, 0",
         "            klicks = self._klicks",
         "kurz wird nicht wiederholt")

# M6: Kein Ende des Haltens — Push-to-Talk hätte keinen Schluss.
mutation("kein-halten-ende", DATEI,
         "            return [HALTEN_ENDE]",
         "            return []",
         "Loslassen beendet das Halten (Push-to-Talk aus)")

# M7: Die Frist für das Klickfenster fehlt — "kurz" käme nie.
mutation("frist-ohne-fenster", DATEI,
         "        if self._klick_frist is not None:\n"
         "            faellig.append(self._klick_frist)",
         "        if self._klick_frist is not None:\n            pass",
         "nach kurzem Druck: Frist ist das Klickfenster")

print(f"\nErgebnis: {PASS} ok, {FAIL} fehlgeschlagen")
sys.exit(0 if FAIL == 0 else 1)
