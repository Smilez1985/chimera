"""Gegenprobe: Die Vorschau und das Zeichnen erfundener Formen brechen.

Zwei Verfälschungen an einer **Kopie** des Baums (`CHIMERA_ROOT_TEST`):

1. Die Vorschau schreibt in falscher Größe (`breite` ignoriert) — dann ist
   „Panelgröße" nur ein Wort in der Hilfe.
2. Eine der vier Ebenen erfundener Formen wird nicht mehr gezeichnet. Genau
   das war der Zustand bis 15.11.2026: `draw_free_shapes` stand da, hatte aber
   keinen Aufrufer — geprüft, abgelegt, nie gezeigt.

Aufruf: python3 tests/gegenprobe_vorschau.py
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
TEST = HIER / "test_vorschau.py"

MUTATIONEN = [
    ("vorschau-ignoriert-die-groesse",
     "tools/vorschau.py",
     "    panel = NullPanel(width=breite, height=hoehe)",
     "    panel = NullPanel(width=240, height=280)"),
    ("front-ebene-nicht-gezeichnet",
     "src/chimera/render/avatar.py",
     '        # Layer 11b: erfundene Formen ganz vorn\n'
     '        self.draw_free_shapes(draw, formen, "front", cx, cy, base_r)',
     '        # Layer 11b entfernt'),
]


def lauf(wurzel: Path) -> int:
    env = dict(os.environ, CHIMERA_ROOT_TEST=str(wurzel))
    p = subprocess.run([sys.executable, str(TEST)], capture_output=True,
                       text=True, env=env, timeout=300)
    return p.returncode


def kopiere(ziel: Path) -> None:
    for teil in ("tools", "src", "data"):
        if (ROOT / teil).exists():
            shutil.copytree(ROOT / teil, ziel / teil)


def main() -> int:
    print("== Grundlauf (unverändert, muss grün sein)")
    with tempfile.TemporaryDirectory() as tmp:
        w = Path(tmp)
        kopiere(w)
        if lauf(w) != 0:
            print("GEGENPROBE UNBRAUCHBAR: schon der unveränderte Baum ist rot")
            return 2
        print("  ok    unverändert grün")

    rot = 0
    for name, datei, alt, neu in MUTATIONEN:
        with tempfile.TemporaryDirectory() as tmp:
            w = Path(tmp)
            kopiere(w)
            ziel = w / datei
            text = ziel.read_text()
            if alt not in text:
                print(f"  FEHLT {name}: Stelle nicht gefunden in {datei}")
                return 2
            ziel.write_text(text.replace(alt, neu, 1))
            if lauf(w) == 0:
                print(f"  GRUEN (schlecht): {name}")
            else:
                rot += 1
                print(f"  rot (gut): {name}")

    print(f"\n== {rot} von {len(MUTATIONEN)} Verfälschungen machen den Test rot")
    return 0 if rot == len(MUTATIONEN) else 1


if __name__ == "__main__":
    sys.exit(main())
