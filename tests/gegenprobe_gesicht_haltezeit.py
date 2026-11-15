"""Gegenprobe zur Haltezeit des Agentengesichts (15.11.2026).

Verfälscht je eine Zusage in einer **Kopie** des Quellbaums (``CHIMERA_SRC``)
und prüft, dass ``tests/test_gesicht_haltezeit.py`` rot wird.

Aufruf: python3 tests/gegenprobe_gesicht_haltezeit.py
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).resolve().parent
ROOT = HIER.parent
SRC = ROOT / "src"
TEST = HIER / "test_gesicht_haltezeit.py"
FACE = "chimera/agent/face.py"
AVATAR = "chimera/render/avatar.py"

MUTATIONEN = [
    ("dauer-ignoriert",
     FACE,
     "            return max(0.0, wert)",
     "            return 0.0"),
    ("dauer-des-moods-ignoriert",
     FACE,
     '            return max(0.0, float(mood.get("dauer_s") or 0))',
     "            return 0.0"),
    ("frist-ignoriert",
     FACE,
     '        elif what != "wartet" and self._haelt():',
     "        elif False:"),
    ("ablosung-ignoriert",
     FACE,
     "        if self._haelt_bis is None:\n            return True",
     "        if self._haelt_bis is None:\n            return False"),
    ("reflex-gebremst",
     FACE,
     "        if what in HARD_STATES:\n"
     "            # Ein Schreck ist ein Reflex und bricht die Haltezeit.\n"
     "            self._haelt_bis = 0.0",
     "        if False:\n            pass"),
    ("wartet-blockiert",
     FACE,
     '        elif what != "wartet" and self._haelt():',
     "        elif self._haelt():"),
    ("ablauf-vergisst-zurueck",
     AVATAR,
     "            rueckruf(zurueck)",
     "            rueckruf(None)"),
    ("ablauf-prueft-nicht",
     AVATAR,
     "    if jetzt < bis:\n        return False",
     "    if False:\n        return False"),
]


def lauf(src: Path) -> tuple[int, str]:
    env = dict(os.environ, CHIMERA_SRC=str(src))
    p = subprocess.run([sys.executable, str(TEST)], capture_output=True,
                       text=True, env=env, timeout=300)
    return p.returncode, p.stdout + p.stderr


def main() -> int:
    print("== Grundlauf (unverfälscht, muss grün sein)")
    with tempfile.TemporaryDirectory() as tmp:
        kopie = Path(tmp) / "src"
        shutil.copytree(SRC, kopie)
        rc, aus = lauf(kopie)
        if rc != 0:
            print(aus[-2000:])
            print("GEGENPROBE UNBRAUCHBAR: schon der unverfälschte Baum ist rot")
            return 2
        print("  ok    unverfälscht grün")

    rot = 0
    for name, datei, alt, neu in MUTATIONEN:
        with tempfile.TemporaryDirectory() as tmp:
            kopie = Path(tmp) / "src"
            shutil.copytree(SRC, kopie)
            ziel = kopie / datei
            text = ziel.read_text(encoding="utf-8")
            if alt not in text:
                print(f"  ???   {name}: Stelle nicht gefunden in {datei}")
                continue
            ziel.write_text(text.replace(alt, neu, 1), encoding="utf-8")
            rc, _ = lauf(kopie)
            if rc != 0:
                rot += 1
                print(f"  rot   {name}")
            else:
                print(f"  GRÜN  {name} — die Zusage ist nicht geprüft!")

    print(f"\n{rot}/{len(MUTATIONEN)} Mutationen rot")
    return 0 if rot == len(MUTATIONEN) else 1


if __name__ == "__main__":
    sys.exit(main())
