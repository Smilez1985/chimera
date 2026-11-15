"""Gegenprobe: Die Avatar-Einstellungen und die Vorschau brechen.

Drei Verfälschungen an einer **Kopie** des Baums (`CHIMERA_ROOT_TEST`):

1. `setzen` nimmt jeden Wert an (die Prüfung fällt weg) — dann ist
   „ungültig ändert nichts" nur ein Satz in der Doku.
2. Die Vorschau rechnet `max(eigene, 30)` statt „eigene Dauer → einmal ganz".
   Genau das war der BONG-Fehler vom 15.11.2026: eine Animation mit 13 s
   stand 30 s still da, weil die Vorschauzeit dazukam.
3. Der Renderer nimmt die Haarfarbe der Einstellung nie an (die
   Kostüm-Bedingung wird zu `False`) — dann ist der Farbwähler wieder ein
   Bedienelement ohne Wirkung.

Aufruf: python3 tests/gegenprobe_einstellungen.py
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
TEST = HIER / "test_einstellungen.py"

MUTATIONEN = [
    ("setzen-ohne-pruefung",
     "src/chimera/render/einstellungen.py",
     '        geprueft = self._pruefen(feld, wert)\n'
     '        if geprueft is None:\n'
     '            return (False, f"{feld}: {wert!r} ungültig — nichts geändert")',
     '        geprueft = wert'),
    ("vorschau-rechnet-max-statt-einmal-ganz",
     "src/chimera/render/einstellungen.py",
     '    if eigene > 0:\n'
     '        return (None, f"eigene Dauer — läuft einmal ganz ({eigene:.0f} s)")\n'
     '    return (float(vorgabe), f"Dauerzustand — {float(vorgabe):.0f} s Vorschau")',
     '    if eigene > 0:\n'
     '        return (max(float(vorgabe), eigene), "verfälscht")\n'
     '    return (float(vorgabe), f"Dauerzustand — {float(vorgabe):.0f} s Vorschau")'),
    ("haarfarbe-wird-nie-uebernommen",
     "src/chimera/render/avatar.py",
     "            if not roh.get('style'):",
     "            if False:"),
]

def lauf(wurzel: Path) -> int:
    env = dict(os.environ, CHIMERA_ROOT_TEST=str(wurzel))
    p = subprocess.run([sys.executable, str(TEST)], capture_output=True,
                       text=True, env=env, timeout=300)
    return p.returncode

def kopiere(ziel: Path) -> None:
    for teil in ("src", "data"):
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
