"""Gegenprobe zu den Anzeigefeldern (Regel „Anzeigefelder").

Vier Zusagen werden in einer Kopie des Baums verfaelscht; ``tests/test_anzeigefelder.py``
muss an der genannten Stelle rot werden:

  1. Bänder überschneiden sich nicht.
  2. Beim Platzmangel weicht das Unwichtigere (nicht das Wichtigere).
  3. Ein zu langer Text wird gekürzt, nicht abgeschnitten.
  4. Ein zu kleiner Bereich ist ein Fehler, kein stilles Ergebnis.

Aufruf: python3 tests/gegenprobe_anzeigefelder.py
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).resolve().parent
ROOT = HIER.parent
LAYOUT = ROOT / "src" / "chimera" / "display" / "layout.py"
FELD = ROOT / "src" / "chimera" / "display" / "feld.py"
TEST = HIER / "test_anzeigefelder.py"

MUTATIONEN = [
    ("baender-ueberlappen", LAYOUT,
     "        oben += wunsch[i]",
     "        oben += 0",
     "keine Lücke, keine Überschneidung"),
    ("falsches-feld-weicht", LAYOUT,
     "    reihenfolge = sorted(range(len(liste)), key=lambda i: (-liste[i].prioritaet, liste[i].name))",
     "    reihenfolge = sorted(range(len(liste)), key=lambda i: (liste[i].prioritaet, liste[i].name))",
     "bei 36 bleibt nur das wichtige"),
    ("text-wird-abgeschnitten", FELD,
     "        if self._breite(text, schrift) <= platz:\n            return text",
     "        return text",
     "langer Text endet mit Auslassungszeichen"),
    ("zu-klein-ist-kein-fehler", LAYOUT,
     "        raise Platzfehler(",
     "        return [], []  # noqa\n        raise Platzfehler(  # noqa",
     "zu kleiner Bereich wurde stillschweigend hingenommen"),
]


def lauf(datei: Path, inhalt: str) -> subprocess.CompletedProcess:
    with tempfile.TemporaryDirectory() as tmp:
        baum = Path(tmp) / "projekt"
        shutil.copytree(ROOT / "src", baum / "src")
        (baum / "tests").mkdir(exist_ok=True)
        shutil.copy(TEST, baum / "tests" / "test_anzeigefelder.py")
        ziel = baum / datei.relative_to(ROOT)
        ziel.write_text(inhalt, encoding="utf-8")
        return subprocess.run([sys.executable, str(baum / "tests" / "test_anzeigefelder.py")],
                              capture_output=True, text=True, timeout=300)


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

    print("=== Gegenprobe Anzeigefelder ===")

    basis = lauf(LAYOUT, LAYOUT.read_text(encoding="utf-8"))
    if basis.returncode == 0:
        ok("unveraendert gruen")
    else:
        bad("unveraendert schon rot -- Gegenprobe nicht aussagekraeftig")
        print(basis.stdout[-800:])

    for name, datei, muster, ersatz, pruefpunkt in MUTATIONEN:
        original = datei.read_text(encoding="utf-8")
        if muster not in original:
            bad(f"{name}: Muster nicht gefunden")
            continue
        p = lauf(datei, original.replace(muster, ersatz, 1))
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
