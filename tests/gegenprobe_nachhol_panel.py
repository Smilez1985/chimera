"""Gegenprobe zum Nachholen einer belegten Anzeige (15.11.2026).

Verfälscht je eine Zusage in einer **Kopie** des Quellbaums
(``CHIMERA_SRC``) und prüft, dass ``tests/test_nachhol_panel.py`` rot wird.
Ohne Gegenprobe beweist ein grüner Test nichts — er könnte die kaputte
Fassung genauso gut durchwinken.

Aufruf: python3 tests/gegenprobe_nachhol_panel.py
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
TEST = HIER / "test_nachhol_panel.py"
NACHHOL = "chimera/displays/nachhol.py"
FASSADE = "chimera/display/panel.py"
BASIS = "chimera/displays/base.py"

#: (Name, Datei, alt, neu) — jede Mutation kehrt genau eine Zusage um.
MUTATIONEN = [
    ("kein-nachholen",
     FASSADE,
     "        return NachholPanel(typ, quelle, exc, profil=prof)",
     "        p = NullPanel(); p.hinweis = str(exc); return p"),
    ("auch-defekt-nachholen",
     FASSADE,
     "        if not isinstance(exc, OSError):",
     "        if False:"),
    ("bereit-immer-wahr",
     NACHHOL,
     "        return self._echt is not None",
     "        return True"),
    ("abstand-ignoriert",
     NACHHOL,
     "        if jetzt < self._naechster:\n            return None",
     "        if False:\n            return None"),
    ("plan-laeuft-ins-leere",
     NACHHOL,
     "            i = min(self._versuche, len(self._abstaende)) - 1",
     "            i = self._versuche if self._versuche < len(self._abstaende) "
     "else len(self._abstaende) - 1"),
    ("letztes-bild-vergessen",
     NACHHOL,
     "            self._letztes = image",
     "            pass"),
    ("licht-nicht-nachgezogen",
     NACHHOL,
     "            if self._licht is not None:\n                echt.backlight(self._licht)",
     "            if False:\n                echt.backlight(self._licht)"),
    ("nullpanel-bereit",
     BASIS,
     "    bereit = False\n",
     "    bereit = True\n"),
    ("hinweis-bleibt-stehen",
     NACHHOL,
     '        self._echt = echt\n        self.hinweis = ""',
     '        self._echt = echt'),
]


def baum_kopie(ziel: Path) -> Path:
    kopie = ziel / "src"
    shutil.copytree(SRC, kopie)
    return kopie


def lauf(src: Path) -> tuple[int, str]:
    env = dict(os.environ, CHIMERA_SRC=str(src))
    p = subprocess.run([sys.executable, str(TEST)], capture_output=True,
                       text=True, env=env, timeout=600)
    return p.returncode, p.stdout + p.stderr


def main() -> int:
    print("== Grundlauf (unverfälscht, muss grün sein)")
    with tempfile.TemporaryDirectory() as tmp:
        kopie = baum_kopie(Path(tmp))
        rc, aus = lauf(kopie)
        if rc != 0:
            print(aus[-2000:])
            print("GEGENPROBE UNBRAUCHBAR: schon der unverfälschte Baum ist rot")
            return 2
        print("  ok    unverfälscht grün")

    rot = 0
    for name, datei, alt, neu in MUTATIONEN:
        with tempfile.TemporaryDirectory() as tmp:
            kopie = baum_kopie(Path(tmp))
            ziel = kopie / datei
            text = ziel.read_text(encoding="utf-8")
            if alt not in text:
                print(f"  ???   {name}: Stelle nicht gefunden in {datei}")
                continue
            ziel.write_text(text.replace(alt, neu, 1), encoding="utf-8")
            rc, aus = lauf(kopie)
            if rc != 0:
                rot += 1
                print(f"  rot   {name}")
            else:
                print(f"  GRÜN  {name} — die Zusage ist nicht geprüft!")

    print(f"\n{rot}/{len(MUTATIONEN)} Mutationen rot")
    return 0 if rot == len(MUTATIONEN) else 1


if __name__ == "__main__":
    sys.exit(main())
