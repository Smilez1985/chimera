"""Gegenprobe zur Gesichtsanweisung im Prompt (tests/test_agent.py, letzter
Abschnitt).

Jede Zusage in einer Kopie des Quellbaums verfaelschen; der Test muss an der
erwarteten Stelle rot werden. Der echte Baum bleibt unberuehrt.

Aufruf: python3 tests/gegenprobe_gesicht_prompt.py
"""

from __future__ import annotations

import os
import re
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
    ("anweisung-immer",
     LOOP,
     '''        if getattr(self.tools, "face", None) is not None:
            text += GESICHT_TEMPLATE''',
     '''        if True:
            text += GESICHT_TEMPLATE''',
     "ohne Gesicht keine Anweisung"),
    ("zustand-im-systemprompt",
     LOOP,
     '''        if getattr(self.tools, "face", None) is not None:
            text += GESICHT_TEMPLATE''',
     '''        if getattr(self.tools, "face", None) is not None:
            text += GESICHT_TEMPLATE + str(getattr(getattr(self.tools.face, "state", None), "mood_name", ""))''',
     "Systemprompt aendert sich mit dem Ausdruck nicht"),
    ("zeile-im-nutzertext",
     LOOP,
     '''        self.history.append({"role": "user", "content": prompt})''',
     '''        self.history.append({"role": "user", "content": prompt + "\\n\\n" + (self._gesicht_hinweis() or "")})''',
     "kein Beiwerk im Nutzertext"),
    ("kurzform-gross",
     LOOP,
     '''        kurz = re.sub(r"[^a-z0-9]+", "_", name.strip().lower()).strip("_")''',
     '''        kurz = re.sub(r"[^A-Z0-9]+", "_", name.strip().upper()).strip("_")''',
     "Kurzform klein"),
    ("kein-werkzeug-verweis",
     LOOP,
     '''- Namen finden: moods (optional mit "suche"). Eigenen löschen:''',
     '''- Namen finden: nachsehen. Eigenen löschen:''',
     "Optionen knapp: moods"),
]


def kopiere(ziel: Path) -> None:
    shutil.copytree(SRC, ziel, dirs_exist_ok=True)


def lauf(cwd: Path) -> tuple[int, str]:
    env = dict(os.environ, CHIMERA_SRC=str(cwd), PYTHONDONTWRITEBYTECODE="1")
    r = subprocess.run([sys.executable, str(TEST)], cwd=str(HIER),
                       env=env, capture_output=True, text=True, timeout=600)
    return r.returncode, r.stdout + r.stderr


def main() -> int:
    if not TEST.exists():
        print(f"FEHLT: {TEST}")
        return 2

    print("== Grundlauf (unverfaelscht) muss gruen sein")
    rc, out = lauf(SRC)
    if rc != 0:
        print(out[-2000:])
        print("ABBRUCH: Der unveraenderte Lauf ist schon rot.")
        return 2
    print("  ok    gruen (rc=0)")

    gut = schlecht = 0
    for name, datei, alt, neu, punkt in MUTATIONEN:
        td = Path(tempfile.mkdtemp(prefix="gegenprobe-gesicht-", dir="/var/tmp"))
        baum = td / "src"
        kopiere(baum)
        ziel = baum / datei
        text = ziel.read_text(encoding="utf-8")
        if alt not in text:
            print(f"  FAIL  {name}: Muster steht nicht in {datei}")
            schlecht += 1
            shutil.rmtree(td, ignore_errors=True)
            continue
        ziel.write_text(text.replace(alt, neu, 1), encoding="utf-8")
        rc, out = lauf(baum)
        getroffen = re.search(r"FAIL\s+" + re.escape(punkt), out) is not None
        if rc != 0 and getroffen:
            print(f"  ok    {name} -> rot an \"{punkt}\"")
            gut += 1
        else:
            print(f"  FAIL  {name}: nicht rot an \"{punkt}\" (rc={rc})")
            for z in out.splitlines():
                if "FAIL" in z:
                    print("        " + z.strip())
            schlecht += 1
        shutil.rmtree(td, ignore_errors=True)

    print()
    print(f"Gegenprobe: {gut}/{len(MUTATIONEN)} rot, {schlecht} gruen geblieben")
    return 0 if schlecht == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
