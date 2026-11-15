"""Gegenprobe: Der Socket-Weg der Avatar-Operationen bricht.

Zwei Verfälschungen an einer **Kopie** des Baums (`CHIMERA_ROOT_TEST`):

1. Der Dienst bedient `avatar_lesen` nicht mehr — genau der Fehler vom
   13.11.2026 (`freigaben_lesen` gegen `freigabe_lesen`): alle Tests grün,
   die Funktion tot. Die Op-Namen-Prüfung muss das melden.
2. Die Sitzung gibt die Brücke nicht weiter (`avatar_bruecke` verschwindet) —
   dann kommt statt der Werte ein Grund, und die Tests, die Werte erwarten,
   müssen rot werden.

Aufruf: python3 tests/gegenprobe_avatar_socket.py
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
TEST = HIER / "test_avatar_socket.py"

MUTATIONEN = [
    ("dienst-kennt-avatar_lesen-nicht",
     "src/chimera/sitzung_socket.py",
     'elif op in ("avatar_lesen", "avatar_setzen", "ausdruecke",\n'
     '                            "vorschau"):',
     'elif op in ("avatar_setzen", "ausdruecke", "vorschau"):'),
    ("bruecke-nicht-durchgereicht",
     "src/chimera/sitzung_socket.py",
     'bruecke = getattr(self.session, "avatar_bruecke", None)',
     'bruecke = None'),
]

def lauf(wurzel: Path) -> int:
    env = dict(os.environ, CHIMERA_ROOT_TEST=str(wurzel))
    p = subprocess.run([sys.executable, str(TEST)], capture_output=True,
                       text=True, env=env, timeout=180)
    return p.returncode

def kopiere(ziel: Path) -> None:
    """Nur was der Test liest: die Quellen und die eine Rust-Datei.

    **Nicht** `rust/` als Ganzes: dort liegt `target/` mit rund 2 GB
    Übersetzungsstand, und ein Kopieren scheitert an Sonderdateien (am
    15.11. gemessen: `[Errno 22]` und ein Fehlerbericht über 350 000
    Zeichen). Ein Prüfbaum soll klein sein.
    """
    if (ROOT / "src").exists():
        shutil.copytree(ROOT / "src", ziel / "src")
    web = ROOT / "rust" / "crates" / "tor" / "src" / "web.rs"
    if web.is_file():
        ziel_web = ziel / "rust" / "crates" / "tor" / "src" / "web.rs"
        ziel_web.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(web, ziel_web)

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
            text = ziel.read_text(encoding="utf-8")
            if alt not in text:
                print(f"  FAIL  {name}: Stelle nicht gefunden in {datei}")
                continue
            ziel.write_text(text.replace(alt, neu, 1), encoding="utf-8")
            rc = lauf(w)
            if rc != 0:
                rot += 1
                print(f"  ok    {name} -- Test wurde rot (rc {rc})")
            else:
                print(f"  FAIL  {name} -- Test blieb GRÜN, die Prüfung misst nichts")

    print(f"\n{rot}/{len(MUTATIONEN)} Verfälschungen rot")
    return 0 if rot == len(MUTATIONEN) else 1

if __name__ == "__main__":
    sys.exit(main())
