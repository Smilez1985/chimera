"""Gegenprobe zur Agentenschleife (15.11.2026, nach dem Pi-Deploy 05:00).

Prüft die vier Zusagen, die an diesem Tag dazukamen — je eine Verfälschung
in einer **Kopie** des Quellbaums (``CHIMERA_SRC``), und
``tests/test_agent.py`` muss rot werden:

1. Ein **nacktes** JSON-Objekt wird als Werkzeugaufruf erkannt.
2. Ein **fremder** Name im JSON bleibt Antwort (kein Werkzeug startet).
3. Die Rüge sagt, dass der Rückfall **ausgeführt** wurde.
4. Am Deckel gibt es **eine** Wrap-up-Runde ohne Werkzeuge, und ihr Text ist
   das Ergebnis.

Aufruf: python3 tests/gegenprobe_schleife.py
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
TEST = HIER / "test_agent.py"
LOOP = "chimera/agent/loop.py"

MUTATIONEN = [
    # 1. Die nackte Form wieder abschalten (der Stand vor dem Fix).
    ("nackte-form-ignoriert",
     LOOP,
     "    if bekannt:\n        nackt = _als_aufruf(_json_objekt(text))",
     "    if False:\n        nackt = _als_aufruf(_json_objekt(text))"),
    # 2. Jeden Namen durchlassen -- dann startet jede JSON-Antwort ein
    #    Werkzeug.
    ("fremder-name-erlaubt",
     LOOP,
     'if (nackt is not None and nackt["name"] in bekannt',
     'if (nackt is not None and True'),
    # 3. Die falsche Rüge (der Stand vor dem Fix).
    ("ruege-sagt-nicht-ausgefuehrt",
     LOOP,
     '"content": RUEGE_AUSGEFUEHRT})',
     '"content": RUEGE_NICHT_AUSGEFUEHRT})'),
    # 4a. Der Wrap-up-Runde die Werkzeuge lassen.
    ("wrapup-mit-werkzeugen",
     LOOP,
     '            versuch["werkzeuge"] = []          # leer = keine Schnittstelle',
     '            pass'),
    # 4b. Die Wrap-up-Runde gar nicht erst machen.
    ("wrapup-fehlt",
     LOOP,
     "        abschluss = self._wrapup(denken, steps, kosten, anbieter, modell)",
     '        abschluss = ""'),
    # 4c. Der Deckel von acht (der Stand vor dem Fix).
    ("deckel-acht",
     LOOP,
     "MAX_UMLAEUFE = 30",
     "MAX_UMLAEUFE = 8"),
]


def lauf(src: Path) -> int:
    env = dict(os.environ, CHIMERA_SRC=str(src))
    p = subprocess.run([sys.executable, str(TEST)], capture_output=True,
                       text=True, env=env, timeout=600)
    return p.returncode


def main() -> int:
    print("== Grundlauf (unverfälscht, muss grün sein)")
    with tempfile.TemporaryDirectory() as tmp:
        kopie = Path(tmp) / "src"
        shutil.copytree(SRC, kopie)
        if lauf(kopie) != 0:
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
            if lauf(kopie) != 0:
                rot += 1
                print(f"  rot   {name}")
            else:
                print(f"  GRÜN  {name} — die Zusage ist nicht geprüft!")

    print(f"\n{rot}/{len(MUTATIONEN)} Mutationen rot")
    return 0 if rot == len(MUTATIONEN) else 1


if __name__ == "__main__":
    sys.exit(main())
