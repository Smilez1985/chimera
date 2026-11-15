"""Gegenprobe zu den Werkzeugaufrufen über die Schnittstelle statt über Text
(`tests/test_agent.py`, Abschnitt "Werkzeugaufrufe", smilez 15.11.2026).

Jede Zusage in einer Kopie des Quellbaums verfaelschen; der Test muss an der
erwarteten Stelle rot werden.

Aufruf: python3 tests/gegenprobe_werkzeug_weg.py
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
    ("prompt-mit-werkzeugliste",
     LOOP,
     '''        if self._nativ:
            # Die Werkzeuge gehen als Schnittstelle mit; eine zweite''',
     '''        if False:
            # Die Werkzeuge gehen als Schnittstelle mit; eine zweite''',
     "nativ: keine Werkzeugliste"),
    ("textaufruf-wird-ausgefuehrt",
     LOOP,
     '''            if self._nativ:
                if CALL_RE.search(text):''',
     '''            if False:
                if CALL_RE.search(text):''',
     "Textaufruf: nichts ausgeführt"),
    ("ruege-fehlt",
     LOOP,
     '''                        self.history.append({"role": "user",
                                             "content": RUEGE_TEXT_AUFTRAG})''',
     '''                        pass''',
     "Textaufruf: Rüge im Verlauf"),
    ("rueckfall-ausgeschaltet",
     LOOP,
     '''            call = CALL_RE.search(text)
            if not call:''',
     '''            call = None
            if not call:''',
     "Rückfall: Textaufruf wird ausgeführt"),
    ("zweiter-textaufruf-durchgereicht",
     LOOP,
     '''                    text = reste or NICHT_AUSGEFUEHRT''',
     '''                    pass''',
     "zweiter Textaufruf: kein TOOL im Antworttext"),
]


def lauf(cwd: Path) -> tuple[int, str]:
    env = dict(os.environ, CHIMERA_SRC=str(cwd), PYTHONDONTWRITEBYTECODE="1")
    r = subprocess.run([sys.executable, str(TEST)], cwd=str(HIER),
                       env=env, capture_output=True, text=True, timeout=600)
    return r.returncode, r.stdout + r.stderr


def main() -> int:
    print("== Grundlauf (unverfaelscht) muss gruen sein")
    rc, out = lauf(SRC)
    if rc != 0:
        print(out[-1500:])
        print("ABBRUCH: Der unveraenderte Lauf ist schon rot.")
        return 2
    print("  ok    gruen (rc=0)")

    gut = schlecht = 0
    for name, datei, alt, neu, punkt in MUTATIONEN:
        td = Path(tempfile.mkdtemp(prefix="gp-weg-", dir="/var/tmp"))
        baum = td / "src"
        shutil.copytree(SRC, baum, dirs_exist_ok=True)
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
