#!/usr/bin/env python3
"""Gegenprobe zu test_bildrate.py (Regel 9): je eine Zusage verfälschen.

M1 ist der alte Zustand bis 3.11.2026: keine Ruhe-Bildrate, immer 15
Bilder/s — genau so lief der Dienst mit 29,7 % eines Kerns im Leerlauf.
M2 der Gegenpol: nie volle Rate (dann wäre das Gesicht beim Sprechen zäh).
"""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TEST = REPO / "tests" / "test_bildrate.py"
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

DATEI = "chimera/render/avatar.py"

print("=== Gegenprobe Ruhe-Bildrate ===")

rc, aus = lauf(REPO / "src")
ok("unverändert grün") if rc == 0 else bad("unverändert schon rot — nicht aussagekräftig")

# M1: Alter Zustand — immer volle Bildrate, die Ruhe gibt es nicht.
mutation("immer-volle-rate", DATEI,
         "        jetzt = time.monotonic()\n        if jetzt < self._wach_bis:\n"
         "            return True\n        if self.is_blinking:",
         "        jetzt = time.monotonic()\n        if True:\n"
         "            return True\n        if self.is_blinking:",
         "Ruhe: 1–5 Bilder in 1,2 s (nicht 15/s)")

# M2: Gegenpol — nie volle Rate, auch beim Sprechen nicht.
mutation("nie-volle-rate", DATEI,
         "        if str(rd.get(\"name\", \"\")).upper() in (\"TALK\", \"SPEAK\"):\n"
         "            return True",
         "        if str(rd.get(\"name\", \"\")).upper() in (\"TALK\", \"SPEAK\"):\n"
         "            return False",
         "beim Sprechen: volle Rate")

# M3: Ruhe-Rate nicht gekappt — dann wäre sie schneller als das Panel.
mutation("ruhe-nicht-gekappt", DATEI,
         "self.RUHE_FPS = max(0, min(int(ruhe_fps), self.TARGET_FPS))",
         "self.RUHE_FPS = max(0, int(ruhe_fps))",
         "zu hohe Ruhe-Rate wird gekappt")

# M4: Blinzeln wieder in Bildern (der alte Zustand) — bei 2 Bildern/s wäre
# ein Drei-Bilder-Blinzeln 1,5 s lang.
mutation("blinzeln-in-bildern", DATEI,
         "                self.blink_ende = jetzt + random.uniform(BLINK_DAUER_MIN,\n"
         "                                                         BLINK_DAUER_MAX)",
         "                self.blink_ende = jetzt + random.uniform(3, 7) / 15.0 * 5",
         "Dauer in Sekunden (0,20–0,47 s)")

# M5: Kein Vorlauf — bei 2 Bildern/s ist das Blinzeln halb vorbei, bevor
# die Schleife es merkt.
mutation("ohne-vorlauf", DATEI,
         "                and jetzt + BLINK_VORLAUF >= self.naechstes_blinzeln):",
         "                and jetzt >= self.naechstes_blinzeln):",
         "kurz vor dem Blinzeln: volle Rate")


# M6: Ruhe 0 zeichnet trotzdem — dann läuft die Schleife heiß, statt zu warten.
mutation("ruhe-null-zeichnet", DATEI,
         "                if frame_time <= 0:",
         "                if False:",
         "Ruhe 0: während des Laufs kein Bild")

# M7: Die Ruhe schlaeft ueber den Blinzelbeginn hinweg -- bei 0,5 s
# Bildabstand waere ein Blinzeln von 0,3 s halb vorbei, bevor es ein Bild gibt.
mutation("ruhe-ignoriert-blinzeln", DATEI,
         "                if (not self.is_blinking and self.naechstes_blinzeln\n"
         "                        is not None):",
         "                if False:",
         "geplantes Blinzeln weckt die Schleife (4–12 Bilder)")

print(f"\nErgebnis: {PASS} ok, {FAIL} fehlgeschlagen")
sys.exit(0 if FAIL == 0 else 1)
