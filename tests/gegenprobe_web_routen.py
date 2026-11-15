"""Gegenprobe: den Modul-Routen-Abgleich wirklich brechen.

Zwei Verfälschungen an einer **Kopie** des Repo-Ausschnitts:

1. Ein Weg wird im Gateway umbenannt (`"bild"` → `"bild_neu"`) — genau der
   Fehler, der am 13.11. die Erinnerung stumm gemacht hat (`freigaben_lesen`
   gegen `freigabe_lesen`).
2. Der Verteiler verliert den Zweig für ein Modul — dann landet jeder Aufruf
   des Moduls bei „nicht gefunden".

Beide müssen `tests/test_web_routen.py` rot machen. Sonst prüft der Test nur
sich selbst.

Aufruf: python3 tests/gegenprobe_web_routen.py
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
TEST = HIER / "test_web_routen.py"

MUTATIONEN = [
    ("weg-umbenannt-im-gateway",
     '("GET", "bild") => {', '("GET", "bild_neu") => {'),
    ("verteiler-verliert-zweig",
     '        (_, p) if p.starts_with("/api/anzeige/") => anzeige_api(z, a, &p["/api/anzeige/".len()..]),\n',
     ''),
]


def lauf(wurzel: Path) -> int:
    env = dict(os.environ, CHIMERA_ROOT_TEST=str(wurzel))
    p = subprocess.run([sys.executable, str(TEST)], capture_output=True,
                       text=True, env=env, timeout=300)
    return p.returncode


def kopiere(ziel: Path) -> None:
    """Nur, was der Test liest — der ganze Baum waere unnoetig teuer."""
    (ziel / "rust/crates/tor").mkdir(parents=True, exist_ok=True)
    shutil.copytree(ROOT / "rust/crates/tor/web/module",
                    ziel / "rust/crates/tor/web/module")
    (ziel / "rust/crates/tor/src").mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / "rust/crates/tor/src/web.rs",
                 ziel / "rust/crates/tor/src/web.rs")


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
    for name, alt, neu in MUTATIONEN:
        with tempfile.TemporaryDirectory() as tmp:
            w = Path(tmp)
            kopiere(w)
            ziel = w / "rust/crates/tor/src/web.rs"
            text = ziel.read_text()
            if alt not in text:
                print(f"  FEHLT {name}: Stelle nicht gefunden")
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
