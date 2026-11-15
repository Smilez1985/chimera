"""Gegenprobe: den Anzeigespiegel wirklich brechen.

Verfälscht je eine Zusage in einer **Kopie** des Quellbaums und prüft, dass
`tests/test_anzeigespiegel.py` rot wird. Ohne diese Proben wäre „grün" nur die
Aussage, dass der Test sich selbst gefällt — beim Spiegeln besonders
gefährlich, weil ein stiller Fehlschlag (nichts geschrieben, Zähler steht)
genau wie „kein neues Bild" aussieht.

Aufruf: python3 tests/gegenprobe_anzeigespiegel.py
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
TEST = HIER / "test_anzeigespiegel.py"

SPIEGEL = "chimera/display/spiegel.py"

MUTATIONEN = [
    ("gleiches-bild-wird-wieder-veroeffentlicht",
     SPIEGEL,
     "if (bild is self._zuletzt or bild == self._zuletzt) and \\\n"
     "                (breite, hoehe) == self._zuletzt_groesse:\n"
     "            return False",
     "if False:\n"
     "            return False"),
    ("falsche-laenge-wird-angenommen",
     SPIEGEL,
     "if len(bild) != erwartet:",
     "if False and len(bild) != erwartet:"),
    ("zaehler-steht",
     SPIEGEL,
     "        self.zaehler += 1\n        try:",
     "        try:"),
    ("datei-fuer-andere-gesperrt",
     SPIEGEL,
     "os.chmod(neu, 0o644)",
     "os.chmod(neu, 0o600)"),
    ("abschalter-vergessen",
     SPIEGEL,
     "if not self.aktiv or not bild or not breite or not hoehe:",
     "if not bild or not breite or not hoehe:"),
    ("nicht-atomar-geschrieben",
     SPIEGEL,
     "        os.replace(neu, self.pfad)",
     "        pass  # direkt geschrieben, ohne Umbenennen\n"
     "        with open(self.pfad, 'wb') as f:\n"
     "            f.write(daten)"),
    ("renderer-veroeffentlicht-nicht",
     "chimera/render/avatar.py",
     "                self.spiegel.zeige(getattr(self.panel, \"bild_bytes\", None),\n"
     "                                   self.WIDTH, self.HEIGHT)",
     "                pass"),
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
            print(f"  FAIL  Mutation {name} ändert nichts")
            return 2
        with tempfile.TemporaryDirectory() as tmp:
            kopie = Path(tmp) / "src"
            shutil.copytree(SRC, kopie)
            ziel = kopie / datei
            text = ziel.read_text()
            if alt not in text:
                print(f"  FEHLT {name}: Stelle nicht gefunden in {datei}")
                return 2
            ziel.write_text(text.replace(alt, neu, 1))
            geprueft += 1
            if lauf(kopie) == 0:
                print(f"  GRUEN (schlecht): {name}")
            else:
                rot += 1
                print(f"  rot (gut): {name}")

    print(f"\n== {rot} von {geprueft} Verfälschungen machen den Test rot")
    if rot != geprueft:
        print("GEGENPROBE UNVOLLSTÄNDIG")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
