"""Gegenprobe zum Status-Werkzeug (`tests/test_agent.py`, Regel 9).

Zwei Zusagen stehen hier zur Prüfung, beide in einer **Kopie** des
Quellbaums verfälscht (`CHIMERA_SRC`), der echte Baum bleibt unberührt:

1. Der Agent fragt die Werte über **eine** Operation (`status_lesen`) und
   schickt nichts weiter mit — der Op-Name ist schon einmal verrutscht
   (`freigaben_lesen` gegen `freigabe_lesen`, 13.11.) und alle Tests blieben
   grün.
2. „Nicht lesbar" bleibt „nicht lesbar": Ein fehlender Wert darf nicht als
   Ruhe erscheinen (Regel 10g / GLOBAL: leere Ausgabe ist ein Verdachtsfall).

Aufruf: python3 tests/gegenprobe_status_werkzeug.py
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

TOOLS = "chimera/agent/tools.py"

# Je Mutation: Name, Datei, Muster, Ersatz, Prüfpunkt in der Testausgabe.
MUTATIONEN = [
    (
        "op-name-verrutscht",
        TOOLS,
        'a = gateway.anfragen({"op": "status_lesen"})',
        'a = gateway.anfragen({"op": "status"})',
        "die Op heisst status_lesen",
    ),
    (
        "argumente-mitgeschickt",
        TOOLS,
        'a = gateway.anfragen({"op": "status_lesen"})',
        'a = gateway.anfragen({"op": "status_lesen", "ausfuehrlich": True})',
        "das Werkzeug schickt nichts weiter mit",
    ),
    (
        "warnstufe-verschluckt",
        TOOLS,
        'marke = "" if stufe in (None, "", "ok") else f" ({stufe})"',
        'marke = ""',
        "eine Warnstufe wird benannt",
    ),
    (
        "nicht-lesbar-als-null",
        TOOLS,
        'teile.append(f"- {z.get(\'titel\')}: {z.get(\'text\')}{marke}")',
        'teile.append(f"- {z.get(\'titel\')}: {z.get(\'wert\') if z.get(\'wert\') is not None else 0}{marke}")',
        "'nicht lesbar' bleibt 'nicht lesbar'",
    ),
    (
        "leere-liste-als-ruhe",
        TOOLS,
        "        if not zeilen:\n            # Leere Ausgabe ist ein Verdachtsfall, keine Auskunft (GLOBAL).\n            return \"Der Dienst hat keine Messwerte geliefert (leere Liste).\"",
        "        if not zeilen:\n            return \"Alles in Ordnung.\"",
        "leere Liste wird als Verdacht gemeldet",
    ),
]


def lauf(quelle: Path | None) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    if quelle is not None:
        env["CHIMERA_SRC"] = str(quelle / "src")
    return subprocess.run(
        [sys.executable, str(TEST)], capture_output=True, text=True, timeout=300, env=env
    )


def kopie(ziel: Path) -> None:
    shutil.copytree(SRC, ziel / "src")


def main() -> int:
    pass_ = fail = 0

    def ok(m: str) -> None:
        nonlocal pass_
        pass_ += 1
        print(f"  ok    {m}")

    def bad(m: str) -> None:
        nonlocal fail
        fail += 1
        print(f"  FAIL  {m}")

    print("=== Gegenprobe Status-Werkzeug ===")

    unveraendert = lauf(None)
    if unveraendert.returncode == 0:
        ok("unveraendert gruen")
    else:
        bad("unveraendert rot -- die Gegenprobe misst nichts")
        print(unveraendert.stdout[-2000:])
        return 1

    for name, datei, muster, ersatz, pruefpunkt in MUTATIONEN:
        with tempfile.TemporaryDirectory() as td:
            baum = Path(td)
            kopie(baum)
            ziel = baum / "src" / datei
            text = ziel.read_text(encoding="utf-8")
            if muster not in text:
                bad(f"{name}: Muster fehlt ({muster[:50]!r})")
                continue
            ziel.write_text(text.replace(muster, ersatz, 1), encoding="utf-8")
            lauf_ = lauf(baum)
            if lauf_.returncode == 0:
                bad(f"{name}: blieb gruen (die Zusage ist unbewacht)")
            elif pruefpunkt in lauf_.stdout and "FAIL" in lauf_.stdout:
                ok(f"{name}: rot bei {pruefpunkt!r}")
            else:
                bad(f"{name}: rot, aber nicht am Prüfpunkt {pruefpunkt!r}")
                print(lauf_.stdout[-1500:])

    print(f"\nErgebnis: {pass_} ok, {fail} FAIL")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
