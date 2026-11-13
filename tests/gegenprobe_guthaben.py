"""Gegenprobe zum Guthaben-Werkzeug (Regel 9, ROADMAP „Guthaben je Anbieter").

Fuenf Zusagen der Textausgabe werden in einer Kopie von `tools.py`
verfaelscht; `tests/test_agent.py` muss an der erwarteten Stelle rot werden.
Die echte Datei bleibt unberuehrt.

Aufruf: python3 tests/gegenprobe_guthaben.py
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).resolve().parent
TOOLS = HIER.parent / "src" / "chimera" / "agent" / "tools.py"
AGENT_TEST = HIER / "test_agent.py"

# Je Mutation: Name, Muster, Ersatz, Pruefpunkt im Test.
MUTATIONEN = [
    (
        "punkt-statt-komma",
        'return s.replace(".", ",") if "." in s else s',
        "return s",
        "Betrag wird gesprochen geschrieben",
    ),
    (
        "waehrungen-zusammengefasst",
        'satz = f"{name}: " + ", ".join(teile)',
        'satz = f"{name}: " + ", ".join(teile[:1])',
        "zwei Waehrungen bleiben zwei Betraege",
    ),
    (
        "veraltet-verschwiegen",
        'if e.get("veraltet") and alter:',
        "if False:",
        "veraltet wird gesagt",
    ),
    (
        "fehler-als-null",
        'zeilen.append(f"{name}: keine Zahl -- {grund}")',
        'zeilen.append(f"{name}: 0")',
        "ohne Zahl steht der Fehler",
    ),
    (
        "ohne-anbieter-leer",
        'return "Es ist kein Anbieter eingetragen -- es gibt kein Guthaben abzufragen."',
        'return ""',
        "ohne Anbieter kommt ein Satz",
    ),
]


def lauf(inhalt: str) -> subprocess.CompletedProcess:
    """Den Agenten-Test gegen eine Kopie der Quellen laufen lassen.

    Die echte Datei bleibt unberuehrt: kopiert wird `src/`, die verfaelschte
    Fassung landet in der Kopie.
    """
    with tempfile.TemporaryDirectory() as tmp:
        baum = Path(tmp) / "projekt"
        shutil.copytree(TOOLS.parents[2], baum / "src")
        (baum / "src" / "chimera" / "agent" / "tools.py").write_text(inhalt, encoding="utf-8")
        (baum / "tests").mkdir(exist_ok=True)
        shutil.copy(AGENT_TEST, baum / "tests" / "test_agent.py")
        return subprocess.run(
            [sys.executable, str(baum / "tests" / "test_agent.py")],
            capture_output=True, text=True, timeout=300,
        )


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

    print("=== Gegenprobe Guthaben ===")

    original = TOOLS.read_text(encoding="utf-8")
    basis = lauf(original)
    if basis.returncode == 0:
        ok("unveraendert gruen")
    else:
        bad("unveraendert schon rot -- Gegenprobe nicht aussagekraeftig")
        print(basis.stdout[-800:])

    with tempfile.TemporaryDirectory() as tmp:
        for name, muster, ersatz, pruefpunkt in MUTATIONEN:
            if muster not in original:
                bad(f"{name}: Muster nicht gefunden")
                continue
            kopie = Path(tmp) / f"{name}.py"
            kopie.write_text(original.replace(muster, ersatz, 1), encoding="utf-8")
            p = lauf(kopie.read_text(encoding="utf-8"))
            if p.returncode == 0:
                bad(f"{name}: Test blieb gruen")
                continue
            treffer = [z for z in p.stdout.splitlines() if z.strip().startswith("FAIL")]
            if any(pruefpunkt in z for z in treffer):
                ok(f"{name}: rot bei '{pruefpunkt}'")
            else:
                bad(f"{name}: rot, aber nicht bei '{pruefpunkt}'")
                print("\n".join(treffer[:4]))

    print(f"\nErgebnis: {pass_} ok, {fail} FAIL")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
