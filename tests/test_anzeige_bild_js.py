"""JS-Test der Bildrechnung im Anzeige-Modul (ohne Browser).

Warum es diesen Rahmen gibt: `anzeige.js` ist eine Web-Komponente. Was daran
schiefgehen kann, ist aber keine Frage von Pixeln auf dem Schirm, sondern
Rechnung: den 32-Byte-Kopf deuten und RGB565 nach RGBA wandeln. Beides prüft
`tests/js/anzeige_bild.mjs` an der **echten** Datei, mit einem minimalen
DOM-Ersatz in Node.

Dieser Python-Rahmen existiert nur, damit die vorhandene CI-Schleife
(`for t in tests/test_*.py`) den JS-Test mitnimmt, ohne dass eine zweite
Werkzeugkette mit eigener Ansteuerung entsteht.

Ohne `node` ist der Test **übersprungen**, nicht grün: Eine fehlende
Voraussetzung ist kein Beweis.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

HIER = Path(__file__).resolve().parent
JS = HIER / "js" / "anzeige_bild.mjs"


def main() -> int:
    node = shutil.which("node")
    print("=== Anzeigespiegel-Bild (JS) ===")
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
        # Doppelt gesichert: Eine Ausgabe, die eine gerissene Prüfung meldet
        # und trotzdem 0 zurückgibt, wäre stiller Erfolg.
        print("  FAIL  Ausgabe nennt FAIL, rc war aber 0")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
