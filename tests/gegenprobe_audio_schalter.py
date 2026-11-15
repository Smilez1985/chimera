"""Gegenprobe: Der Audio-Schalter verliert drei Zusagen.

Drei Verfälschungen an einer Baumkopie (`CHIMERA_SRC`), jede bricht eine
andere Zusage aus `tests/test_audio_schalter.py`:

1. **`-q` kommt an die lesenden Aufrufe zurück.** Am Pi gemessen (15.11.2026):
   `amixer -q … sget` endet mit rc 0 und gibt **nichts** aus — die Lautstärke
   wäre still „nicht messbar" und die Ablage bliebe leer. Genau dieser Fehler
   war am Gerät, deshalb steht er hier.
2. **`_amixer` verwirft die Ausgabe** — `sget` antwortet, der Wert
   kommt aber nie an: jede Messung ist leer (am Pi genau so gefunden).
3. **Einstellen schaltet ein** — ein Regler, der den stummen Lautsprecher
   hörbar macht, wäre ein Nebeneffekt, den niemand bestellt hat.

Aufruf: python3 tests/gegenprobe_audio_schalter.py
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
TEST = HIER / "test_audio_schalter.py"
QUELLE = "src/chimera/audio_schalter.py"

VERFAELSCHUNGEN = [
    (
        "-q an den lesenden Aufrufen (leere Ausgabe)",
        '["amixer", "-c", self.karte, "sget", REGLER[was]], lesen=True)',
        '["amixer", "-q", "-c", self.karte, "sget", REGLER[was]], lesen=True)',
    ),
    (
        "_amixer verwirft die Ausgabe (jede Messung leer)",
        '    return 0, (p.stdout or "")',
        '    return 0, ""',
    ),
    (
        "gemessene 0 % wird als Einstellung gemerkt",
        '                if gemessen and gemessen != "0%" and self._lautstaerke.get(was) != gemessen:',
        '                if gemessen and self._lautstaerke.get(was) != gemessen:',
    ),
    (
        "Einstellen schaltet ein",
        "        if not an:\n"
        "            return (True, f\"{was}: {zahl}% gemerkt (aus — gilt beim Einschalten)\")",
        "        if not an:\n"
        "            self.mikrofon(True) if was == \"mikrofon\" else self.lautsprecher(True)",
    ),
]

def lauf(src: Path) -> int:
    env = dict(os.environ, CHIMERA_SRC=str(src), PYTHONDONTWRITEBYTECODE="1")
    p = subprocess.run([sys.executable, str(TEST)], capture_output=True,
                       text=True, env=env, timeout=300)
    return p.returncode

def main() -> int:
    print("== Grundlauf (unveraendert, muss gruen sein)")
    if lauf(ROOT / "src") != 0:
        print("GEGENPROBE UNBRAUCHBAR: schon der echte Baum ist rot")
        return 2
    print("  ok    unveraendert gruen")

    text = (ROOT / QUELLE).read_text(encoding="utf-8")
    rot = 0
    with tempfile.TemporaryDirectory() as tmp:
        for i, (name, alt, neu) in enumerate(VERFAELSCHUNGEN, 1):
            if alt not in text:
                print(f"  FAIL  Stelle {i} nicht gefunden in {QUELLE}")
                return 1
            src = Path(tmp) / f"src-{i}"
            shutil.copytree(ROOT / "src/chimera", src / "chimera",
                            ignore=shutil.ignore_patterns("__pycache__"))
            (src / "chimera/audio_schalter.py").write_text(
                text.replace(alt, neu, 1), encoding="utf-8")
            rc = lauf(src)
            if rc != 0:
                rot += 1
                print(f"  ok    {i}/{len(VERFAELSCHUNGEN)} {name} -- Test wurde rot")
            else:
                print(f"  FAIL  {i}/{len(VERFAELSCHUNGEN)} {name} -- Test blieb gruen")
    print(f"\n{rot}/{len(VERFAELSCHUNGEN)} Verfaelschungen rot")
    return 0 if rot == len(VERFAELSCHUNGEN) else 1

if __name__ == "__main__":
    sys.exit(main())
