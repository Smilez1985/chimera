"""Gegenprobe: Werkzeugkennung im Protokoll wirklich messen (15.11.2026).

Verfälscht je eine Stelle in einer **Kopie** des Quellbaums und prüft, dass
`tests/test_protokoll_werkzeuge.py` rot wird.

Aufruf: python3 tests/gegenprobe_protokoll_werkzeuge.py
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
TEST = HIER / "test_protokoll_werkzeuge.py"
ABL = "chimera/ablage.py"

MUTATIONEN = [
    ("aufruf-nicht-geschrieben",
     ABL,
     '        if namen:\n            eintrag["werkzeuge"] = namen',
     '        if False:\n            eintrag["werkzeuge"] = namen'),
    ("ergebnis-nicht-geschrieben",
     ABL,
     '        if m.get("tool_name"):\n            eintrag["werkzeug"] = str(m["tool_name"])',
     '        if False:\n            eintrag["werkzeug"] = str(m["tool_name"])'),
    ("denktext-nicht-geschrieben",
     ABL,
     '        if m.get("gedacht"):\n            eintrag["gedacht"] = str(m["gedacht"])',
     '        if False:\n            eintrag["gedacht"] = str(m["gedacht"])'),
    ("abspielen-vergisst-aufrufe",
     ABL,
     '            if e.get("werkzeuge"):\n                m["tool_calls"] = [',
     '            if False:\n                m["tool_calls"] = ['),
    ("halbpaar-wird-behalten",
     ABL,
     "        if ergebnisse >= len(aufrufe):",
     "        if True:"),
]


def lauf(src: Path) -> int:
    env = dict(os.environ, CHIMERA_SRC=str(src))
    p = subprocess.run([sys.executable, str(TEST)], capture_output=True,
                       text=True, env=env, timeout=600)
    return p.returncode


def main() -> int:
    print("== Grundlauf (unverändert, muss grün sein)")
    with tempfile.TemporaryDirectory() as tmp:
        kopie = Path(tmp) / "src"
        shutil.copytree(SRC, kopie)
        if lauf(kopie) != 0:
            print("GEGENPROBE UNBRAUCHBAR: schon der unveränderte Baum ist rot")
            return 2
        print("  ok    unverändert grün")

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
            if lauf(kopie) != 0:
                rot += 1
                print(f"  rot   {name}")
            else:
                print(f"  GRÜN  {name} — die Zusage ist nicht geprüft!")

    print(f"\n{rot}/{len(MUTATIONEN)} Mutationen rot")
    return 0 if rot == len(MUTATIONEN) else 1


if __name__ == "__main__":
    sys.exit(main())
