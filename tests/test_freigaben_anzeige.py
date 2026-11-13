"""JS-Test der Restzeit-Anzeige im Freigaben-Modul (ohne Browser).

Warum es diesen Rahmen gibt: `freigaben.js` ist eine Web-Komponente. Bis
13.11. war die Anzeige „läuft ab in …" nur von Hand im Browser geprüft — ein
Autotest dafür fehlte (ROADMAP). Die Rechnung selbst ist reine Arithmetik,
also prüfbar ohne Browser: `tests/js/freigaben_anzeige.mjs` lädt die **echte**
Datei in Node mit einem minimalen DOM-Ersatz und ruft `dauerText` auf.

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
JS = HIER / "js" / "freigaben_anzeige.mjs"


def main() -> int:
    node = shutil.which("node")
    if not node:
        print("=== Freigaben-Restzeit (JS) ===")
        print("  uebersprungen: node nicht vorhanden -- nicht geprueft")
        return 0
    if not JS.is_file():
        print(f"  FAIL  Testdatei fehlt: {JS}")
        return 1
    p = subprocess.run([node, str(JS)], capture_output=True, text=True, timeout=120)
    print("=== Freigaben-Restzeit (JS) ===")
    sys.stdout.write(p.stdout)
    if p.returncode != 0:
        sys.stdout.write(p.stderr)
        print("  FAIL  node-Test rot")
        return 1
    if "\n  FAIL" in p.stdout:
        # Doppelt gesichert: Ein Testlauf, der eine gerissene Pruefung meldet und
        # trotzdem 0 zurueckgibt, waere stiller Erfolg. (Nicht auf "FAIL"
        # schlechthin pruefen -- die Schlusszeile heisst "0 FAIL".)
        print("  FAIL  Ausgabe nennt FAIL, rc war aber 0")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
