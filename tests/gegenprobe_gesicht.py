"""Gegenprobe zu test_gesicht_zustand.py (DESIGN Regel 4d).

Stellt je einen alten oder falschen Zustand her; der Test muss rot werden.
Eine Mutation, bei der er gruen bleibt, ist eine Luecke im Test.

Aufruf:  python3 tests/gegenprobe_gesicht.py     (Ergebnis: "0 gruen" ist gut)
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEST = ROOT / "tests" / "test_gesicht_zustand.py"

GRUEN = 0


def lauf():
    r = subprocess.run([sys.executable, str(TEST)], cwd=ROOT, capture_output=True, text=True, timeout=300)
    return r.returncode == 0


def text_mutation(name, datei, alt, neu):
    global GRUEN
    pfad = ROOT / datei
    orig = pfad.read_text(encoding="utf-8")
    if orig.count(alt) < 1:
        print(f"MUSTER FEHLT: {name}")
        GRUEN += 1
        return
    pfad.write_text(orig.replace(alt, neu, 1), encoding="utf-8")
    try:
        if lauf():
            print(f"GRUEN (schlecht): {name}")
            GRUEN += 1
        else:
            print(f"rot (gut): {name}")
    finally:
        pfad.write_text(orig, encoding="utf-8")


def json_mutation(name, aendern):
    global GRUEN
    pfad = ROOT / "data" / "moods-builtin.json"
    orig = pfad.read_text(encoding="utf-8")
    d = json.loads(orig)
    aendern({m["name"]: m for m in d["moods"]}, d)
    pfad.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        if lauf():
            print(f"GRUEN (schlecht): {name}")
            GRUEN += 1
        else:
            print(f"rot (gut): {name}")
    finally:
        pfad.write_text(orig, encoding="utf-8")


# 1. spricht zeigt wieder den Ausdruck mit Ohr
text_mutation("spricht-zeigt-ohr", "src/chimera/agent/face.py",
              '"spricht": ("SPEAK",)', '"spricht": ("LISTEN",)')
# 2. hoert zeigt etwas ohne Ohr
text_mutation("hoert-ohne-ohr", "src/chimera/agent/face.py",
              '"hoert": ("LISTEN",)', '"hoert": ("IDLE",)')
# 3. Ruhezustand ohne Ausdruck
text_mutation("wartet-ohne-ausdruck", "src/chimera/agent/face.py",
              '"wartet": ("IDLE",)', '"wartet": ("GIBTS_NICHT",)')
# 4. Name in der Tabelle, den es nicht gibt (der FOCUS-Fehler)
text_mutation("name-fehlt", "src/chimera/agent/face.py",
              '"arbeitet": ("WORK", "CURIOUS")', '"arbeitet": ("FOCUS", "CURIOUS")')
# 5. SPEAK bekommt ein Ohr
json_mutation("speak-mit-ohr", lambda m, d: m["SPEAK"]["accessory"].update(type=["big_ear"]))
# 6. SPEAK schaut zur Seite
json_mutation("speak-blick-zur-seite", lambda m, d: m["SPEAK"]["eyes"].update(look_offset=7))
# 7. SPEAK bekommt den alten starren Mund
json_mutation("speak-starrer-mund", lambda m, d: m["SPEAK"]["mouth"].update(style="line"))
# 8. TALK gibt es wieder
json_mutation("talk-wieder-da", lambda m, d: d["moods"].append({**m["LISTEN"], "name": "TALK"}))
# 9. Mundphase ohne Halten (jedes Bild eine neue Phase)
text_mutation("halten-ignoriert", "src/chimera/render/avatar.py",
              "halte = max(1, int(self.SPEAK_HALTE))", "halte = 1")
# 10. Mundphase haengt nicht am Kreis (bleibt in der ersten Phase)
text_mutation("kreis-offen", "src/chimera/render/avatar.py",
              "% n]", "% 1]")
# 11. 'offen' sieht aus wie 'zu'
text_mutation("offen-wie-zu", "src/chimera/render/avatar.py",
              "draw.ellipse([cx - 10, my + 1, cx + 10, my + 22], fill=EYE_COLOR)",
              "draw.line([cx - 8, my + 8, cx + 8, my + 8], fill=EYE_COLOR, width=3)")
# 12. Agentenschleife meldet kein wartet mehr
text_mutation("loop-ohne-wartet", "src/chimera/agent/loop.py",
              "        finally:\n            self._state(\"wartet\")", "        finally:\n            pass")

print(f"== {GRUEN} gruen ==")
sys.exit(1 if GRUEN else 0)
