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

MUTATIONEN = [
    ("keine-haltezeit",
     FACE,
     "        self._haelt_bis = self._uhr() + HALT_S",
     "        self._haelt_bis = self._uhr()"),
    ("frist-ignoriert",
     FACE,
     '        elif what != "wartet" and self._uhr() < self._haelt_bis:',
     "        elif False:"),
    ("reflex-gebremst",
     FACE,
     "        if what in HARD_STATES:\n"
     "            # Ein Schreck ist ein Reflex und bricht die Haltezeit.\n"
     "            self._haelt_bis = 0.0",
     "        if False:\n            pass"),
    ("frist-verlaengert-nicht",
     FACE,
     "        self._haelt_bis = self._uhr() + HALT_S",
     "        self._haelt_bis = self._haelt_bis or (self._uhr() + HALT_S)"),
    ("wartet-blockiert",
     FACE,
     '        elif what != "wartet" and self._uhr() < self._haelt_bis:',
     "        elif self._uhr() < self._haelt_bis:"),
    ("haltedauer-null",
     FACE,
     "HALT_S = 5.0",
     "HALT_S = 0.0"),
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
