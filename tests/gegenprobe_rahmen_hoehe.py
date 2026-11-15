"""Gegenprobe zur Höhenkette im Rahmen.

Drei Verfälschungen, jede bricht eine andere Zusage aus
`tests/test_rahmen_hoehe.py`:

1. `#buehne` verliert `flex: 1` — die Fläche hat keine definite Höhe mehr,
   `height:100%` im Modul löst auf `auto` auf. **Genau der Fehler vom
   15.11.2026** (leerer Chatverlauf, Eingabe klebt oben).
2. `#buehne > *` verliert `min-height: 0` — die Fläche darf nicht mehr
   schrumpfen; ein langer Verlauf drückt die Eingabe aus dem Fenster.
3. `<main>` verliert `display:flex` — die Kette beginnt gar nicht erst.

Aufruf: python3 tests/gegenprobe_rahmen_hoehe.py
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).resolve().parent
ROOT = HIER.parent
TEST = HIER / "test_rahmen_hoehe.py"
RAHMEN = ROOT / "rust/crates/tor/web/rahmen.html"

VERFAELSCHUNGEN = [
    (
        "#buehne ohne flex: 1 (keine definite Höhe)",
        "  #buehne { flex: 1; min-height: 0; display: flex; flex-direction: column; }",
        "  #buehne { min-height: 0; display: flex; flex-direction: column; }",
    ),
    (
        "#buehne > * ohne min-height: 0 (darf nicht schrumpfen)",
        "  #buehne > * { flex: 1; min-height: 0; overflow: auto; }",
        "  #buehne > * { flex: 1; overflow: auto; }",
    ),
    (
        "main ohne display:flex (Kette beginnt nicht)",
        "  main { flex: 1; min-height: 0; overflow: auto; display: flex; flex-direction: column; }",
        "  main { flex: 1; min-height: 0; overflow: auto; }",
    ),
]

def lauf(wurzel: Path) -> int:
    env = dict(os.environ, CHIMERA_ROOT_TEST=str(wurzel))
    p = subprocess.run([sys.executable, str(TEST)], capture_output=True,
                       text=True, env=env, timeout=120)
    return p.returncode

def baum(ziel: Path) -> None:
    """Eine Baumkopie mit nur den zwei Dateien, die der Test liest."""
    (ziel / "rust/crates/tor/web/module/chat").mkdir(parents=True)
    (ziel / "tests").mkdir(parents=True)
    (ziel / "rust/crates/tor/web/rahmen.html").write_text(
        RAHMEN.read_text(encoding="utf-8"), encoding="utf-8")
    (ziel / "rust/crates/tor/web/module/chat/chat.js").write_text(
        (ROOT / "rust/crates/tor/web/module/chat/chat.js").read_text(encoding="utf-8"),
        encoding="utf-8")

def main() -> int:
    print("== Grundlauf (unveraendert, muss gruen sein)")
    if lauf(ROOT) != 0:
        print("GEGENPROBE UNBRAUCHBAR: schon der echte Baum ist rot")
        return 2
    print("  ok    unveraendert gruen")

    text = RAHMEN.read_text(encoding="utf-8")
    rot = 0
    with tempfile.TemporaryDirectory() as tmp:
        for i, (name, alt, neu) in enumerate(VERFAELSCHUNGEN, 1):
            if alt not in text:
                print(f"  FAIL  Stelle {i} nicht gefunden in rahmen.html")
                return 1
            wurzel = Path(tmp) / f"baum-{i}"
            baum(wurzel)
            (wurzel / "rust/crates/tor/web/rahmen.html").write_text(
                text.replace(alt, neu, 1), encoding="utf-8")
            rc = lauf(wurzel)
            if rc != 0:
                rot += 1
                print(f"  ok    {i}/{len(VERFAELSCHUNGEN)} {name} -- Test wurde rot")
            else:
                print(f"  FAIL  {i}/{len(VERFAELSCHUNGEN)} {name} -- Test blieb gruen")
    print(f"\n{rot}/{len(VERFAELSCHUNGEN)} Verfaelschungen rot")
    return 0 if rot == len(VERFAELSCHUNGEN) else 1

if __name__ == "__main__":
    sys.exit(main())
