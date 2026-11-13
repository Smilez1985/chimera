"""Gegenprobe zu `tests/test_freigabe_erinnerung.py` (Regel 9).

Jede Zusage der Erinnerung wird in einer **Kopie** des Quellbaums verfaelscht;
der Test muss an der erwarteten Stelle rot werden. Der echte Baum bleibt
unberuehrt (`CHIMERA_SRC` zeigt auf die Kopie).

Warum eine ganze Kopie und nicht nur eine Datei: Die Verdrahtung liegt in
`__main__.py` (der Dienst ruft `erinnere` im Takt) — eine Mutation dort muss
den Test genauso umwerfen wie eine in der Rechnung.

Aufruf: python3 tests/gegenprobe_freigabe_erinnerung.py
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
TEST = HIER / "test_freigabe_erinnerung.py"

MODUL = "chimera/freigabe_erinnerung.py"
DIENST = "chimera/__main__.py"

# Je Mutation: Name, Datei, Muster, Ersatz, Pruefpunkt in der Testausgabe.
MUTATIONEN = [
    (
        "erster-tick-klingelt-sofort",
        MODUL,
        "                self._faellig[name] = jetzt + abstand",
        "                self._faellig[name] = jetzt",
        "kurz vor dem Abstand still",
    ),
    (
        "geschlossenes-wird-nicht-vergessen",
        MODUL,
        "        for name in list(self._faellig):\n            if name not in offen:\n                del self._faellig[name]",
        "        pass",
        "neu geoeffnet: erst still",
    ),
    (
        "mindestabstand-ignoriert",
        MODUL,
        "                abstand = max(ABSTAND_MIN, roh)",
        "                abstand = roh",
        "zu kurz wird auf das Minimum gehoben",
    ),
    (
        "aplay-fehler-verschluckt",
        MODUL,
        '    if getattr(r, "returncode", 0) != 0:',
        "    if False:",
        "aplay-Fehler wird gemeldet",
    ),
    (
        "leere-liste-spielt-trotzdem",
        MODUL,
        "    if not names:\n        return \"\"",
        "    if False:\n        return \"\"",
        "weiterhin ein Ton",
    ),
    (
        "dienst-ruft-nicht",
        DIENST,
        "            if erinnern is not None:\n                erinnern()",
        "            if False:\n                erinnern()",
        "Dienst ruft die Erinnerung im Takt",
    ),
]


def lauf(quelle: Path | None) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    if quelle is not None:
        env["CHIMERA_SRC"] = str(quelle / "src")
    return subprocess.run(
        [sys.executable, str(TEST)], capture_output=True, text=True,
        timeout=180, env=env,
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

    print("=== Gegenprobe Freigabe-Erinnerung ===")

    basis = lauf(None)
    if basis.returncode == 0:
        ok("unveraendert gruen")
    else:
        bad("unveraendert schon rot -- Gegenprobe nicht aussagekraeftig")
        print(basis.stdout[-800:])

    with tempfile.TemporaryDirectory() as tmp:
        kopie = Path(tmp) / "baum"
        shutil.copytree(SRC, kopie / "src")
        for name, datei, muster, ersatz, pruefpunkt in MUTATIONEN:
            ziel = kopie / "src" / datei
            original = ziel.read_text(encoding="utf-8")
            if muster not in original:
                bad(f"{name}: Muster nicht gefunden")
                continue
            ziel.write_text(original.replace(muster, ersatz, 1), encoding="utf-8")
            try:
                p = lauf(kopie)
            finally:
                ziel.write_text(original, encoding="utf-8")
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
