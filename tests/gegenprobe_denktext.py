"""Gegenprobe: den Denktext-Rückweg wirklich brechen (15.11.2026).

Verfälscht je eine Stelle der Kette in einer **Kopie** des Quellbaums und
prüft, dass `tests/test_denktext_rueckweg.py` rot wird. Ohne diese Proben
wäre „grün" nur die Aussage, dass der Test sich selbst gefällt.

Aufruf: python3 tests/gegenprobe_denktext.py
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
TEST = HIER / "test_denktext_rueckweg.py"

MUTATIONEN = [
    ("gateway-vergisst-den-text",
     "chimera/provider/gateway.py",
     '        self.letzte_gedacht = str(a.get("gedacht") or "")',
     '        self.letzte_gedacht = ""'),
    ("registry-reicht-nicht-durch",
     "chimera/provider/registry.py",
     '                    gedacht=str(getattr(conn, "letzte_gedacht", "") or ""),',
     '                    gedacht="",'),
    ("agent-haengt-nicht-an",
     "chimera/agent/loop.py",
     '                if getattr(reply, "gedacht", ""):\n'
     '                    nachricht["gedacht"] = reply.gedacht',
     '                if False:\n'
     '                    nachricht["gedacht"] = reply.gedacht'),
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
    geprueft = 0
    for name, datei, alt, neu in MUTATIONEN:
        if alt == neu:
            print(f"  ---   {name}: Platzhalter, zählt nicht")
            continue
        geprueft += 1
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

    print(f"\n{rot}/{geprueft} Mutationen rot")
    return 0 if rot == geprueft else 1


if __name__ == "__main__":
    sys.exit(main())
