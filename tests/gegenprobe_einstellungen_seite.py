"""Gegenprobe: Die Einstellungsseite sagt etwas Falsches über Lautstärke.

Zwei Verfälschungen an einer Kopie von `einstellungen.js`
(`CHIMERA_EINSTELLUNGEN_JS`):

1. **Im Aus wird „0 %" gezeigt** statt der eingestellten Lautstärke — genau
   die Auskunft, die den Nutzer glauben lässt, er hätte den Regler
   zugezogen. Am HAT ist „aus" 0 % am Regler, die Einstellung aber 80 %.
2. **Die Längenprüfung fällt weg** — ein Kennwort mit drei Zeichen ginge
   vorbei an der Vorprüfung; das Gateway lehnte es zwar ab, der Nutzer sähe
   den Grund aber erst nach dem Absenden.

Aufruf: python3 tests/gegenprobe_einstellungen_seite.py
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
JS = HIER / "js" / "einstellungen_seite.mjs"
QUELLE = ROOT / "rust/crates/tor/web/module/einstellungen/einstellungen.js"

VERFAELSCHUNGEN = [
    (
        "im Aus wird 0 % behauptet",
        '  return roh === null || roh === undefined ? "aus" : `aus · ${prozent} gilt beim Einschalten`;',
        '  return "aus · 0 %";',
    ),
    (
        "Längenprüfung des Kennworts entfällt",
        "  if (!neu || neu.length < PASSWORT_MIN) {",
        "  if (false) {",
    ),
]

def lauf(datei: Path) -> int:
    env = dict(os.environ, CHIMERA_EINSTELLUNGEN_JS=str(datei))
    p = subprocess.run([os.environ.get("NODE", "node"), str(JS)],
                       capture_output=True, text=True, env=env, timeout=120)
    return p.returncode

def main() -> int:
    if not shutil.which(os.environ.get("NODE", "node")):
        print("uebersprungen: node fehlt -- nicht geprueft")
        return 0
    print("== Grundlauf (unveraendert, muss gruen sein)")
    if lauf(QUELLE) != 0:
        print("GEGENPROBE UNBRAUCHBAR: schon die echte Datei ist rot")
        return 2
    print("  ok    unveraendert gruen")

    text = QUELLE.read_text(encoding="utf-8")
    rot = 0
    with tempfile.TemporaryDirectory() as tmp:
        for i, (name, alt, neu) in enumerate(VERFAELSCHUNGEN, 1):
            if alt not in text:
                print(f"  FAIL  Stelle {i} nicht gefunden in einstellungen.js")
                return 1
            ziel = Path(tmp) / f"einstellungen-{i}.js"
            ziel.write_text(text.replace(alt, neu, 1), encoding="utf-8")
            rc = lauf(ziel)
            if rc != 0:
                rot += 1
                print(f"  ok    {i}/{len(VERFAELSCHUNGEN)} {name} -- Test wurde rot")
            else:
                print(f"  FAIL  {i}/{len(VERFAELSCHUNGEN)} {name} -- Test blieb gruen")
    print(f"\n{rot}/{len(VERFAELSCHUNGEN)} Verfaelschungen rot")
    return 0 if rot == len(VERFAELSCHUNGEN) else 1

if __name__ == "__main__":
    sys.exit(main())
