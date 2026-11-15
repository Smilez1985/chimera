"""Gegenprobe zu den zwei neuen Zusagen vom 15.11.2026:

* **Das Fenster wird von Textaufrufen befreit** (`tests/test_verlauf_saeubern.py`,
  Quelle `chimera/ablage.py`).
* **Das Ruhegesicht ist das Agentengesicht** (`tests/test_ruhegesicht.py`,
  Quelle `chimera/agent/face.py`).

Jede Zusage in einer Kopie des Quellbaums verfälschen; der Test muss an der
erwarteten Stelle rot werden. Der echte Baum bleibt unberührt.

Aufruf: python3 tests/gegenprobe_gesicht_und_verlauf.py
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

ABLAGE = "chimera/ablage.py"
FACE = "chimera/agent/face.py"

MUTATIONEN = [
    # (Name, Datei, alt, neu, Testdatei, erwarteter roter Punkt)
    ("bereinigung-aus",
     ABLAGE,
     "    return ohne_textaufrufe(fenster)",
     "    return fenster",
     "test_verlauf_saeubern.py",
     "Aufruf weg"),
    ("ergebnis-bleibt",
     ABLAGE,
     '''        if rolle != "assistant" and TEXT_ERGEBNIS.match(inhalt):''',
     '''        if False:''',
     "test_verlauf_saeubern.py",
     "Ergebnis weg"),
    ("aufruf-bleibt-im-text",
     ABLAGE,
     '''        if rolle == "assistant" and TEXT_AUFRUF.search(inhalt):''',
     '''        if False:''',
     "test_verlauf_saeubern.py",
     "Text bleibt, Aufruf geht"),
    ("wartet-nimmt-idle",
     FACE,
     '''        if what == "wartet" and self._ruhegesicht():''',
     '''        if False:''',
     "test_ruhegesicht.py",
     "nach wartet steht weiter CHAOS"),
    ("agentenwahl-wird-nicht-gemerkt",
     FACE,
     '''        self._agent_mood = str(mood.get("name") or "")''',
     '''        self._agent_mood = ""''',
     "test_ruhegesicht.py",
     "nach wartet steht weiter CHAOS"),
    ("geloeschter-ausdruck-klebt",
     FACE,
     '''        if not name or self.moods.find(name) is None:''',
     '''        if not name:''',
     "test_ruhegesicht.py",
     "gelöschter Ausdruck -> IDLE"),
]

def lauf(test: str, cwd: Path) -> tuple[int, str]:
    env = dict(os.environ, CHIMERA_SRC=str(cwd), PYTHONDONTWRITEBYTECODE="1")
    r = subprocess.run([sys.executable, str(HIER / test)], cwd=str(HIER),
                       env=env, capture_output=True, text=True, timeout=300)
    return r.returncode, r.stdout + r.stderr

def main() -> int:
    print("== Grundlauf (unverfaelscht) muss gruen sein")
    for test in ("test_verlauf_saeubern.py", "test_ruhegesicht.py"):
        rc, out = lauf(test, SRC)
        if rc != 0:
            print(out[-1200:])
            print(f"ABBRUCH: {test} ist schon unverfaelscht rot.")
            return 2
    print("  ok    beide gruen (rc=0)")

    gut = schlecht = 0
    for name, datei, alt, neu, test, punkt in MUTATIONEN:
        td = Path(tempfile.mkdtemp(prefix="gp-gv-", dir="/var/tmp"))
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
        rc, out = lauf(test, baum)
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
