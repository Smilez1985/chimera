"""Gegenprobe zu `tests/js/freigaben_restzeit.mjs` (Regel 9).

Drei Zusagen der Restzeit-Anzeige werden in einer Kopie des Moduls
verfaelscht; der JS-Test muss an der erwarteten Stelle rot werden. Die echte
Datei bleibt unberuehrt (CHIMERA_FREIGABEN_JS zeigt auf die Kopie).

Ohne `node` ist die Gegenprobe **uebersprungen**, nicht gruen.

Aufruf: python3 tests/gegenprobe_freigaben_restzeit.py
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).resolve().parent
JS_MODUL = HIER.parent / "rust" / "crates" / "tor" / "web" / "module" / "freigaben" / "freigaben.js"
HARNESS = HIER / "js" / "freigaben_restzeit.mjs"

# Je Mutation: Name, Muster, Ersatz, Pruefpunkt im JS-Test.
MUTATIONEN = [
    (
        "sekunden-schwelle-verschoben",
        "if (s < 90) return `läuft ab in ${s} s`;",
        "if (s < 30) return `läuft ab in ${s} s`;",
        "89 s übrig",
    ),
    (
        "abgelaufen-ignoriert",
        "if (s <= 0) return \"abgelaufen\";",
        "if (s <= 0) return `läuft ab in ${-s} s`;",
        "genau jetzt",
    ),
    (
        "unbefristet-als-abgelaufen",
        "if (!bis) return \"unbefristet\";",
        "if (!bis) return \"abgelaufen\";",
        "ohne Ende",
    ),
    (
        "restzeit-nicht-angezeigt",
        '"offen \u2014 " + this.dauerText(e.bis, jetzt)',
        '"offen"',
        "Karte zeigt die Restzeit",
    ),
]


def lauf(quelle: Path | None) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    if quelle is not None:
        env["CHIMERA_FREIGABEN_JS"] = str(quelle)
    return subprocess.run(
        ["node", str(HARNESS)], capture_output=True, text=True, timeout=120, env=env
    )


def main() -> int:
    if not shutil.which("node"):
        print("=== Gegenprobe Freigaben-Restzeit ===")
        print("  uebersprungen: node nicht vorhanden -- nicht geprueft")
        return 0

    pass_ = fail = 0

    def ok(m: str) -> None:
        nonlocal pass_
        pass_ += 1
        print(f"  ok    {m}")

    def bad(m: str) -> None:
        nonlocal fail
        fail += 1
        print(f"  FAIL  {m}")

    print("=== Gegenprobe Freigaben-Restzeit ===")

    basis = lauf(None)
    if basis.returncode == 0:
        ok("unveraendert gruen")
    else:
        bad("unveraendert schon rot -- Gegenprobe nicht aussagekraeftig")
        print(basis.stdout[-800:])

    original = JS_MODUL.read_text(encoding="utf-8")
    with tempfile.TemporaryDirectory() as tmp:
        for name, muster, ersatz, pruefpunkt in MUTATIONEN:
            if muster not in original:
                bad(f"{name}: Muster nicht gefunden")
                continue
            kopie = Path(tmp) / f"{name}.js"
            kopie.write_text(original.replace(muster, ersatz, 1), encoding="utf-8")
            p = lauf(kopie)
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
