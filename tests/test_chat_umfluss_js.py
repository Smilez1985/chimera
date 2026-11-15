"""JS-Test des Umflusses im Chat-Modul (ohne Browser).

Warum es diesen Rahmen gibt: Seit dem 15.11. liegt das gespiegelte Gesicht
**fest** über dem Verlauf (DESIGN, Regel „Anzeigespiegel"); der Text scrollt
darunter durch und weicht ihm aus. Welche Blase ausweichen muss, ist eine
Rechnung mit vier Zahlen — `tests/js/chat_umfluss.mjs` prüft sie an der
**echten** `chat.js` in Node.

Der Python-Rahmen existiert nur, damit die CI-Schleife
(`for t in tests/test_*.py`) den JS-Test mitnimmt.

Ohne `node` ist der Test **übersprungen**, nicht grün.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

HIER = Path(__file__).resolve().parent
JS = HIER / "js" / "chat_umfluss.mjs"


def main() -> int:
    node = shutil.which("node")
    print("=== Chat-Umfluss (JS) ===")
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
