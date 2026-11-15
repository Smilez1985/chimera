"""Gegenprobe: Die Ankündigung der Vorschau auf der Avatar-Seite lügt.

Eine Verfälschung an einer Kopie von `anzeige.js` (`CHIMERA_ANZEIGE_JS`):
Die Bedingung in `vorschauText` wird vertauscht — ein Dauerzustand behauptet
„läuft einmal ganz", ein Ausdruck mit eigener Dauer „30 s Vorschau".

Warum das zählt: Genau diese Verwechslung ist der BONG-Fehler vom 15.11.2026
(13 s Animation, 30 s Vorschauzeit) — nur eine Ebene früher, in der Auskunft
an den Nutzer statt in der Standzeit.

Aufruf: python3 tests/gegenprobe_avatar_seite.py
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
JS = HIER / "js" / "avatar_seite.mjs"
QUELLE = ROOT / "rust/crates/tor/web/module/anzeige/anzeige.js"

MUTATION = ('  if (!eintrag || !eintrag.name) return "";\n'
            '  if (eintrag.dauerzustand) {',
            '  if (!eintrag || !eintrag.name) return "";\n'
            '  if (!eintrag.dauerzustand) {')

def lauf(datei: Path) -> int:
    env = dict(os.environ, CHIMERA_ANZEIGE_JS=str(datei))
    p = subprocess.run([os.environ.get("NODE", "node"), str(JS)],
                       capture_output=True, text=True, env=env, timeout=120)
    return p.returncode

def main() -> int:
    if not shutil.which(os.environ.get("NODE", "node")):
        print("uebersprungen: node fehlt -- nicht geprueft")
        return 0
    print("== Grundlauf (unverändert, muss grün sein)")
    if lauf(QUELLE) != 0:
        print("GEGENPROBE UNBRAUCHBAR: schon die echte Datei ist rot")
        return 2
    print("  ok    unverändert grün")

    with tempfile.TemporaryDirectory() as tmp:
        ziel = Path(tmp) / "anzeige.js"
        text = QUELLE.read_text(encoding="utf-8")
        alt, neu = MUTATION
        if alt not in text:
            print("  FAIL  Stelle nicht gefunden in anzeige.js")
            return 1
        ziel.write_text(text.replace(alt, neu, 1), encoding="utf-8")
        rc = lauf(ziel)
        if rc != 0:
            print(f"  ok    vertauschte Bedingung -- Test wurde rot (rc {rc})")
            print("\n1/1 Verfälschungen rot")
            return 0
        print("  FAIL  vertauschte Bedingung -- Test blieb GRÜN")
        print("\n0/1 Verfälschungen rot")
        return 1

if __name__ == "__main__":
    sys.exit(main())
