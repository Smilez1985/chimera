"""Gegenprobe zur Haltezeit des Agentengesichts (15.11.2026).

Verfälscht je eine Zusage in einer **Kopie** des Quellbaums (``CHIMERA_SRC``)
und prüft, dass ``tests/test_gesicht_haltezeit.py`` rot wird.

Aufruf: python3 tests/gegenprobe_gesicht_haltezeit.py
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
TEST = HIER / "test_gesicht_haltezeit.py"
FACE = "chimera/agent/face.py"
AVATAR = "chimera/render/avatar.py"

MUTATIONEN = [
    # 15.11.2026: Ein endlicher Ausdruck läuft ganz — die Modellangabe darf
    # ihn verlängern, nie abschneiden (smilez: „bong friert mitten in der
    # mood Animation ein, das muss ganz laufen").
    ("modell-kuerzt-animation",
     FACE,
     "            return max(wert, eigene)",
     "            return wert"),
    ("dauer-des-moods-ignoriert",
     FACE,
     "        if dauer is None:\n            return eigene",
     "        if dauer is None:\n            return 0.0"),
    # Endlose Ausdrücke sperren nicht: Zustände lösen sie ab, danach gelten
    # sie wieder (smilez: „Rock … brauchen keine harte Laufzeit").
    ("endlos-sperrt",
     FACE,
     "        if self._haelt_bis is None:\n            return False",
     "        if self._haelt_bis is None:\n            return True"),
    # Ein laufender Ausdruck muss Zustände abwehren, solange er läuft.
    ("frist-ignoriert",
     FACE,
     '        elif what != "wartet" and self._haelt():',
     "        elif False:"),
    ("reflex-gebremst",
     FACE,
     "        if what in HARD_STATES:\n"
     "            # Ein Schreck ist ein Reflex und bricht die Haltezeit.\n"
     "            self._haelt_bis = 0.0",
     "        if False:\n            pass"),
    ("ablauf-vergisst-zurueck",
     AVATAR,
     "            rueckruf(zurueck)",
     "            rueckruf(None)"),
    ("ablauf-prueft-nicht",
     AVATAR,
     "    if jetzt < bis:\n        return False",
     "    if False:\n        return False"),
    # 15.11.2026, zweiter Fund am Pi: Nach einem Zug stand wieder WORK.
    # Die Mutation lässt den Tätigkeitsausdruck als stehendes Gesicht zu.
    ("ablauf-setzt-taetigkeit",
     FACE,
     "        if name and self.moods.find(name) and name not in STATE_ANSPRUCH:",
     "        if name and self.moods.find(name):"),
    # Ohne Ruheausdruck bleibt das Gesicht auf dem abgelaufenen Zug stehen.
    ("kein-ruhemood",
     FACE,
     '        for candidate in STATE_MOODS.get("wartet", ()):',
     "        for candidate in ():"),
]


def lauf(src: Path) -> tuple[int, str]:
    env = dict(os.environ, CHIMERA_SRC=str(src))
    p = subprocess.run([sys.executable, str(TEST)], capture_output=True,
                       text=True, env=env, timeout=300)
    return p.returncode, p.stdout + p.stderr


def main() -> int:
    print("== Grundlauf (unverfälscht, muss grün sein)")
    with tempfile.TemporaryDirectory() as tmp:
        kopie = Path(tmp) / "src"
        shutil.copytree(SRC, kopie)
        rc, aus = lauf(kopie)
        if rc != 0:
            print(aus[-2000:])
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
            rc, _ = lauf(kopie)
            if rc != 0:
                rot += 1
                print(f"  rot   {name}")
            else:
                print(f"  GRÜN  {name} — die Zusage ist nicht geprüft!")

    print(f"\n{rot}/{len(MUTATIONEN)} Mutationen rot")
    return 0 if rot == len(MUTATIONEN) else 1


if __name__ == "__main__":
    sys.exit(main())
