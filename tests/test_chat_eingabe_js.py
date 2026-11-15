"""JS-Test der Eingabehöhe im Chat-Modul (ohne Browser).

Befund smilez (15.11.2026): *„die prompt Eingabe klebt oben, den Text kann man
nicht mehr lesen … den prompt Bereich manipulierbar, dynamisch nach oben
vergrösserbar machen."*

Die Höhe des Eingabefelds ist eine Rechnung mit drei bzw. vier Zahlen
(`eingabeHoehe`, `griffHoehe`). `tests/js/chat_eingabe.mjs` prüft sie an der
**echten** `chat.js` in Node — dieser Rahmen nimmt den Test nur in die
CI-Schleife (`for t in tests/test_*.py`) mit.

Ohne `node` ist der Test **übersprungen**, nicht grün.

Aufruf: python3 tests/test_chat_eingabe_js.py
Gegenprobe: python3 tests/gegenprobe_chat_eingabe.py
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

HIER = Path(__file__).resolve().parent
JS = HIER / "js" / "chat_eingabe.mjs"

def main() -> int:
    node = shutil.which("node")
    print("=== Chat-Eingabe (JS) ===")
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
