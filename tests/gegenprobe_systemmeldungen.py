"""Gegenprobe zu tests/test_systemmeldungen.py (16.11.2026).

Jede Zusage in einer Kopie des Quellbaums verfälschen; der Test muss an der
erwarteten Stelle rot werden. Der echte Baum bleibt unberührt.

Aufruf: python3 tests/gegenprobe_systemmeldungen.py
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
TEST = HIER / "test_systemmeldungen.py"
# Zusätzlich: die Zusage „Hinweis steht nicht im Nutzertext" wird dort geprüft.
MITLAUF = [HIER / "test_session_bot.py", HIER / "test_agent.py"]

ABLAGE = "chimera/ablage.py"
ANTHROPIC = "chimera/provider/anthropic.py"
VERDICHTEN = "chimera/agent/verdichten.py"
LOOP = "chimera/agent/loop.py"
SESSION = "chimera/agent/session.py"

MUTATIONEN = [
    ("system-ohne-herkunft",
     ABLAGE,
     '''            quelle = str(m.get("_quelle") or "")
            if quelle:
                eintrag["quelle"] = quelle''',
     '''            quelle = ""''',
     "Herkunft der ersten Systemmeldung"),
    ("system-als-nachricht",
     ABLAGE,
     '''        if m.get("role") == "system":''',
     '''        if False:''',
     "Arten in Reihenfolge"),
    ("marker-bleibt-im-verlauf",
     ABLAGE,
     '''            m.pop("_quelle", None)''',
     '''            pass''',
     "kein _quelle im Verlauf"),
    ("abspielen-vergisst-system",
     ABLAGE,
     '''        elif art == "system":''',
     '''        elif art == "system-weg":''',
     "Fenster nach Neustart"),
    ("anthropic-laesst-system-stehen",
     ANTHROPIC,
     '''        if m.get("role") == "system":''',
     '''        if False:''',
     "keine Systemnachricht in messages"),
    ("anthropic-verliert-den-systemtext",
     ANTHROPIC,
     '''    teile = ([system.strip()] if system and system.strip() else []) + zeilen''',
     '''    teile = zeilen''',
     "Top-Level-system trägt alles"),
    ("verdichten-haelt-system-fuer-runde",
     VERDICHTEN,
     '''def _ist_rundenbeginn(m: dict) -> bool:
    if m.get("role") != "user":
        return False''',
     '''def _ist_rundenbeginn(m: dict) -> bool:
    if m.get("role") == "system":
        return True
    if m.get("role") != "user":
        return False''',
     "system ist kein Rundenbeginn"),
    ("kanal-im-nutzertext",
     SESSION,
     '''                result = self.agent.run(text, kanal=channel.hint(), **kwargs)''',
     '''                result = self.agent.run(f"{channel.hint()}\\n\\n{text}", **kwargs)''',
     "Auftrag bleibt rein"),
    ("gesicht-im-nutzertext",
     LOOP,
     '''        self.history.append({"role": "user", "content": prompt})''',
     '''        self.history.append({"role": "user", "content": prompt + "\\n\\n" + (self._gesicht_hinweis() or "")})''',
     "kein Beiwerk im Nutzertext"),
]


def kopiere(ziel: Path) -> None:
    shutil.copytree(SRC, ziel, dirs_exist_ok=True)


def lauf(cwd: Path) -> tuple[int, str]:
    env = dict(os.environ, CHIMERA_SRC=str(cwd), PYTHONDONTWRITEBYTECODE="1")
    rc = 0
    aus = ""
    for datei in [TEST] + MITLAUF:
        r = subprocess.run([sys.executable, str(datei)], cwd=str(HIER),
                           env=env, capture_output=True, text=True, timeout=600)
        rc = rc or r.returncode
        aus += r.stdout + r.stderr
    return rc, aus


def main() -> int:
    if not TEST.exists():
        print(f"FEHLT: {TEST}")
        return 2

    print("== Grundlauf (unverfälscht) muss grün sein")
    rc, out = lauf(SRC)
    if rc != 0:
        print(out[-2000:])
        print("ABBRUCH: Der unveränderte Lauf ist schon rot.")
        return 2
    print("  ok")

    rot = 0
    with tempfile.TemporaryDirectory() as td:
        for name, datei, alt, neu, zusage in MUTATIONEN:
            ziel = Path(td) / name
            kopiere(ziel)
            p = ziel / datei
            t = p.read_text(encoding="utf-8")
            if alt not in t:
                print(f"  FEHLER {name}: Fundstelle fehlt in {datei}")
                return 2
            p.write_text(t.replace(alt, neu), encoding="utf-8")
            rc, out = lauf(ziel)
            if rc == 0:
                print(f"  NICHT ROT {name}: {zusage} blieb grün")
                continue
            if f"FAIL  {zusage}" not in out:
                print(f"  FALSCH ROT {name}: rot, aber nicht an '{zusage}'")
                print("    " + "\n    ".join(
                    z for z in out.splitlines() if "FAIL" in z)[:600])
                continue
            print(f"  rot    {name} -> {zusage}")
            rot += 1

    print(f"\nGegenprobe: {rot}/{len(MUTATIONEN)} rot")
    return 0 if rot == len(MUTATIONEN) else 1


if __name__ == "__main__":
    sys.exit(main())
