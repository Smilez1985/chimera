"""JS-Test der Einstellungsseite (ohne Browser).

Was die Seite **behauptet**, bevor jemand klickt, ist eine Rechnung: Wie ein
Kanal aussieht (an/aus samt eingestellter Lautstärke) und ob die drei
Kennwortfelder überhaupt abschickbar sind. `tests/js/einstellungen_seite.mjs`
prüft beides an der **echten** `einstellungen.js`.

Der Python-Rahmen nimmt den Test nur in die CI-Schleife mit. Ohne `node` ist
der Test **übersprungen**, nicht grün.

Aufruf: python3 tests/test_einstellungen_seite_js.py
Gegenprobe: python3 tests/gegenprobe_einstellungen_seite.py
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

HIER = Path(__file__).resolve().parent
JS = HIER / "js" / "einstellungen_seite.mjs"

def main() -> int:
    node = shutil.which("node")
    print("=== Einstellungsseite (JS) ===")
    if not node:
        print("  uebersprungen: node nicht vorhanden -- nicht geprueft")
        return 0
    if not JS.is_file():
        print(f"  FAIL  Testdatei fehlt: {JS}")
        return 1
    p = subprocess.run([node, str(JS)], capture_output=True, text=True,
                       timeout=120)
    sys.stdout.write(p.stdout)
    if p.returncode != 0:
        sys.stdout.write(p.stderr)
        print("  FAIL  node-Test rot")
        return 1
    if "\n  FAIL" in p.stdout:
        print("  FAIL  Ausgabe nennt FAIL, rc war aber 0")
        return 1
    return 0

if __name__ == "__main__":
    sys.exit(main())
