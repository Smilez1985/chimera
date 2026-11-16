"""Gegenprobe zur Selbstauskunft: jede Zusage muss wirklich brechen.

Verfälscht je eine Stelle in einer **Kopie** des Quellbaums und prüft, dass
`tests/test_selbstbild.py` rot wird. Eine Zusage ohne rote Gegenprobe ist
keine Zusage (GLOBAL: jeder Regressionstest braucht eine Gegenprobe).

Aufruf: python3 tests/gegenprobe_selbstbild.py
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
TEST = HIER / "test_selbstbild.py"
SB = "chimera/agent/selbstbild.py"
LP = "chimera/agent/loop.py"

MUTATIONEN = [
    ("erste-zeile-statt-titel",
     SB,
     '    m = re.match(r"\\*\\*(.+?)\\*\\*", zeile)',
     '    m = None'),
    ("grenze-ignoriert",
     SB,
     'if aktuell is not None and z.startswith("- ") and len(gesammelt) < je:',
     'if aktuell is not None and z.startswith("- "):'),
    ("ohne-markup",
     SB,
     'titel.append(_ohne_markup(text)[:120])',
     'titel.append(s)'),
    ("fehlt-verschwiegen",
     SB,
     '        zeilen.append("CHANGELOG.md: nicht lesbar — was gebaut ist, kann ich "\n'
     '                      "nicht sagen (nicht raten).")',
     '        pass'),
    ("ohne-wurzel-behauptet",
     SB,
     "    if w is None:",
     "    if False:"),
    ("prompt-ohne-verweis",
     LP,
     "        text += SELBST_TEMPLATE",
     "        text += \"\""),
    ("vorpruefung-kennt-es-nicht",
     LP,
     "self.guard = LoopGuard(guard, known_tools=toolbox.names())",
     "self.guard = LoopGuard(guard, known_tools=())"),
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
        print("  grün — die Probe misst den richtigen Baum")

    rot = gruen = 0
    for name, datei, alt, neu in MUTATIONEN:
        with tempfile.TemporaryDirectory() as tmp:
            kopie = Path(tmp) / "src"
            shutil.copytree(SRC, kopie)
            ziel = kopie / datei
            text = ziel.read_text(encoding="utf-8")
            if alt not in text:
                print(f"  UNBRAUCHBAR {name}: Stelle nicht gefunden in {datei}")
                gruen += 1
                continue
            ziel.write_text(text.replace(alt, neu, 1), encoding="utf-8")
            rc = lauf(kopie)
            if rc == 1:
                print(f"  rot   {name}")
                rot += 1
            else:
                print(f"  GRUEN {name} (rc={rc}) — die Zusage ist ungeprüft")
                gruen += 1

    print()
    print(f"{rot}/{len(MUTATIONEN)} Mutationen rot")
    return 0 if gruen == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
