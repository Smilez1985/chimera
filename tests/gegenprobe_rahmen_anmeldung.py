"""Gegenprobe: Der Rahmen verliert die Anmeldemaske und das Tab-Symbol.

Drei Verfälschungen an einer **Kopie** des Baums (`CHIMERA_ROOT_TEST`):

1. Die Masken liegen wieder IM Modulbereich — der Zustand bis 15.11.2026, in
   dem ein 401 ein Element zeigte, das nicht mehr im Dokument hing.
   (Zwei Schnitte, weil ein Nest erst durch Öffnen **und** Schließen
   entsteht — ein einzelner Austausch hätte nur eine doppelte id erzeugt und
   den Test zu Recht grün gelassen.)
2. `zeigeModul` leert wieder ganz `<main>` statt nur die Bühne.
3. Das Tab-Symbol fehlt.

Aufruf: python3 tests/gegenprobe_rahmen_anmeldung.py
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
TEST = HIER / "test_rahmen_anmeldung.py"
RAHMEN = "rust/crates/tor/web/rahmen.html"

#: Je Verfälschung: Name, dann eine Liste von (datei, alt, neu).
MUTATIONEN = [
    ("masken-wieder-im-modulbereich", [
        (RAHMEN, '<div id="buehne"></div>', '<div id="buehne">'),
        (RAHMEN, "  </main>", "  </div></main>"),
    ]),
    ("zeigeModul-leert-alles", [
        (RAHMEN, 'const buehne = $("buehne");', 'const buehne = $("inhalt");'),
    ]),
    ("kein-tab-symbol", [
        (RAHMEN, '<link rel="icon"', '<link rel="unbenutzt"'),
    ]),
]

def lauf(wurzel: Path) -> int:
    env = dict(os.environ, CHIMERA_ROOT_TEST=str(wurzel))
    p = subprocess.run([sys.executable, str(TEST)], capture_output=True,
                       text=True, env=env, timeout=120)
    return p.returncode

def kopiere(ziel: Path) -> None:
    datei = ziel / RAHMEN
    datei.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / RAHMEN, datei)

def main() -> int:
    print("== Grundlauf (unverändert, muss grün sein)")
    with tempfile.TemporaryDirectory() as tmp:
        w = Path(tmp)
        kopiere(w)
        if lauf(w) != 0:
            print("GEGENPROBE UNBRAUCHBAR: schon der unveränderte Baum ist rot")
            return 2
        print("  ok    unverändert grün")

    rot = 0
    for name, schnitte in MUTATIONEN:
        with tempfile.TemporaryDirectory() as tmp:
            w = Path(tmp)
            kopiere(w)
            alle_da = True
            for datei, alt, neu in schnitte:
                ziel = w / datei
                text = ziel.read_text(encoding="utf-8")
                if alt not in text:
                    print(f"  FAIL  {name}: Stelle nicht gefunden ({alt[:40]!r})")
                    alle_da = False
                    break
                ziel.write_text(text.replace(alt, neu, 1), encoding="utf-8")
            if not alle_da:
                continue
            rc = lauf(w)
            if rc != 0:
                rot += 1
                print(f"  ok    {name} -- Test wurde rot (rc {rc})")
            else:
                print(f"  FAIL  {name} -- Test blieb GRÜN, die Prüfung misst nichts")

    print(f"\n{rot}/{len(MUTATIONEN)} Verfälschungen rot")
    return 0 if rot == len(MUTATIONEN) else 1

if __name__ == "__main__":
    sys.exit(main())
