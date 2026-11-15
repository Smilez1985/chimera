"""Gegenprobe der selbsttaetigen Aktionen (15.11.2026).

Verfaelscht je eine Zusage in einer **Kopie** des Quellbaums (``CHIMERA_SRC``)
und prueft, dass ``tests/test_ambiente.py`` rot wird:

1. Ohne Ruhe wird nicht gehandelt (laufender Auftrag, laufender Ausdruck).
2. Der Mindestabstand gilt.
3. Derselbe Ausdruck wiederholt sich nicht sofort.
4. Der Zufall ist gedeckelt.
5. Das Fenster haengt an der Stunde.
6. Der Dienst ruft den Takt auch wirklich (Verdrahtung, nicht nur Modul).

Aufruf: python3 tests/gegenprobe_ambiente.py
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
TEST = HIER / "test_ambiente.py"
AMB = "chimera/agent/ambiente.py"
MAIN = "chimera/__main__.py"

MUTATIONEN = [
    ("ruhe-ignoriert",
     AMB,
     "        if not frei or haelt:\n            return None",
     "        if False:\n            return None"),
    ("abstand-ignoriert",
     AMB,
     "        if (self._letzter is not None\n"
     "                and jetzt - self._letzter < MIN_ABSTAND_S):\n"
     "            return None",
     "        if False:\n            return None"),
    ("sperre-ignoriert",
     AMB,
     "        erlaubt = [n for n in namen if alter[n] >= SPERRE_JE_AUSDRUCK_S]",
     "        erlaubt = list(namen)"),
    ("nur-ein-kandidat",
     AMB,
     "        if len(erlaubt) < 2 and len(namen) > 1:",
     "        if False:"),
    ("gaeste-ignoriert",
     AMB,
     "    gaeste = tuple(n for n in GAST.get((von, bis), {}) if n not in namen)\n"
     "    return tuple(namen) + gaeste",
     "    return tuple(namen)"),
    ("gewicht-ignoriert",
     AMB,
     "        gewichte = [gewicht(n, stunde) for n in erlaubt]",
     "        gewichte = [1.0 for n in erlaubt]"),
    ("wiederholung-erlaubt",
     AMB,
     "        if len(namen) > 1 and self._letzter_name in namen:\n"
     "            namen = [n for n in namen if n != self._letzter_name]",
     "        if False:\n            pass"),
    ("zufall-ignoriert",
     AMB,
     "        if self._zufall() > CHANCE:\n            return None",
     "        if False:\n            return None"),
    ("fenster-ignoriert",
     AMB,
     "    h = int(stunde) % 24",
     "    h = 12"),
    ("takt-nicht-verdrahtet",
     MAIN,
     "            if ambiente is not None:\n"
     "                try:\n"
     "                    ambiente()",
     "            if False:\n"
     "                try:\n"
     "                    ambiente()"),
]


def lauf(src: Path) -> int:
    env = dict(os.environ, CHIMERA_SRC=str(src))
    p = subprocess.run([sys.executable, str(TEST)], capture_output=True,
                       text=True, env=env, timeout=600)
    return p.returncode


def main() -> int:
    print("== Grundlauf (unveraendert, muss gruen sein)")
    with tempfile.TemporaryDirectory() as tmp:
        kopie = Path(tmp) / "src"
        shutil.copytree(SRC, kopie)
        if lauf(kopie) != 0:
            print("GEGENPROBE UNBRAUCHBAR: schon der unveraenderte Baum ist rot")
            return 2
        print("  ok    unveraendert gruen")

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
                print(f"  GRUEN  {name} — die Zusage ist nicht geprueft!")

    print(f"\n{rot}/{len(MUTATIONEN)} Mutationen rot")
    return 0 if rot == len(MUTATIONEN) else 1


if __name__ == "__main__":
    sys.exit(main())
