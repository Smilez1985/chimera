"""Gegenprobe zu `tests/test_mood_ablage.py` (GLOBAL: jeder Regressionstest
braucht eine Gegenprobe, die rot wird).

Jede Zusage aus DESIGN 3.3b wird in einer **Kopie** des Quellbaums
verfaelscht; der Test muss an der erwarteten Stelle rot werden. Der echte
Baum bleibt unberuehrt (`CHIMERA_SRC` zeigt auf die Kopie).

Die Kopie liegt unter `/var/tmp`, nicht unter `/tmp`: dort ist es tmpfs und
zaehlt gegen den Arbeitsspeicher (GLOBAL, "Rechner ohne viel RAM").

Aufruf: python3 tests/gegenprobe_mood_ablage.py
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
TEST = HIER / "test_mood_ablage.py"

ABLAGE = "chimera/mood/ablage.py"
REG = "chimera/mood/registry.py"

MUTATIONEN = [
    ("eingebauter-ueberschreibbar",
     ABLAGE,
     '''    if vorhanden is not None and vorhanden.protected:''',
     '''    if False:''',
     "eingebauter Name abgelehnt"),
    ("name-ungeprueft",
     ABLAGE,
     '''NAME_RE = re.compile(r"^[A-Z0-9_-]{1,24}$")''',
     '''NAME_RE = re.compile(r"^.+$")''',
     "Name abgelehnt: 'a/b'"),
    ("ohne-vorbild-durchgelassen",
     ABLAGE,
     '''    if not roh and not felder:''',
     '''    if False:''',
     "ohne Vorbild und Felder abgelehnt"),
    ("nicht-gespeichert",
     ABLAGE,
     '''    registry.save(pfad, nur_eigene=True)
    return eintrag, bericht''',
     '''    return eintrag, bericht''',
     "Datei geschrieben"),
    ("ganze-bibliothek-in-die-datei",
     ABLAGE,
     '''    registry.save(pfad, nur_eigene=True)
    return eintrag, bericht''',
     '''    registry.save(pfad)
    return eintrag, bericht''',
     "nur der eigene steht in der Datei"),
    ("loeschen-ohne-schutz",
     ABLAGE,
     '''    if eintrag.protected:
        raise AblageFehler(f"{ziel} ist eingebaut und wird nicht gelöscht")''',
     '''    if False:
        raise AblageFehler(f"{ziel} ist eingebaut und wird nicht gelöscht")''',
     "Loeschen eingebauter abgelehnt"),
    ("tiefe-unbegrenzt",
     ABLAGE,
     "MAX_TIEFE = 6",
     "MAX_TIEFE = 60",
     "zu tief abgelehnt"),
    ("herkunft-geht-verloren",
     ABLAGE,
     '''        reg.add(eintrag.mood, origin=eintrag.origin)''',
     '''        reg.add(eintrag.mood, origin="builtin")''',
     "Herkunft ueberlebt"),
    ("prune-schuetzt-nicht",
     REG,
     '''        removable = [e for e in self._by_id.values() if not e.protected]''',
     '''        removable = list(self._by_id.values())''',
     "Eingebautes bleibt"),
    ("vorbild-wird-angefasst",
     ABLAGE,
     '''        roh = copy.deepcopy(eintrag.mood)''',
     '''        roh = eintrag.mood''',
     "Vorbild behaelt seinen Namen"),
]


def kopiere(ziel: Path) -> None:
    shutil.copytree(SRC, ziel, dirs_exist_ok=True)


def lauf(cwd: Path) -> tuple[int, str]:
    env = dict(os.environ, CHIMERA_SRC=str(cwd), PYTHONDONTWRITEBYTECODE="1")
    r = subprocess.run([sys.executable, str(TEST)], cwd=str(HIER),
                       env=env, capture_output=True, text=True, timeout=300)
    return r.returncode, r.stdout + r.stderr


def main() -> int:
    if not TEST.exists():
        print(f"FEHLT: {TEST}")
        return 2

    print("== Grundlauf (unverfaelscht) muss gruen sein")
    rc, out = lauf(SRC)
    if rc != 0:
        print(out[-2000:])
        print("ABBRUCH: Der unveraenderte Lauf ist schon rot — dann misst "
              "keine Mutation etwas.")
        return 2
    print("  ok    gruen (rc=0)")

    gut = schlecht = 0
    for name, datei, alt, neu, punkt in MUTATIONEN:
        td = Path(tempfile.mkdtemp(prefix="gegenprobe-mood-", dir="/var/tmp"))
        baum = td / "src"
        kopiere(baum)
        ziel = baum / datei
        text = ziel.read_text(encoding="utf-8")
        if alt not in text:
            print(f"  FAIL  {name}: Muster steht nicht in {datei} — "
                  "Mutation wirkt nicht (dann prueft der Test die Stelle nicht)")
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
