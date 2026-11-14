"""JS-Test der Kennungs-Ableitung im Anbieter-Modul (ohne Browser).

Warum es diesen Rahmen gibt: `anbieter.js` ist eine Web-Komponente. Das Feld
„Kennung" war bis 14.11. ein Pflichtfeld vor dem Nutzer, obwohl es ein interner
Name ist (`config/geheim/<id>`) — der Nutzer tippte „DeepSeek" und bekam nur
„ist ungueltig". Seit dem Umbau bildet das Modul die Kennung aus der
Bezeichnung; `tests/js/anbieter_kennung.mjs` laedt die **echte** Datei in Node
und prueft die Umformung gegen dieselbe Regel wie `daten::id_gueltig`.

Dieser Python-Rahmen existiert nur, damit die vorhandene CI-Schleife
(`for t in tests/test_*.py`) den JS-Test mitnimmt, ohne dass eine zweite
Werkzeugkette mit eigener Ansteuerung entsteht.

Ohne `node` ist der Test **uebersprungen**, nicht gruen: Eine fehlende
Voraussetzung ist kein Beweis.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

HIER = Path(__file__).resolve().parent
JS = HIER / "js" / "anbieter_kennung.mjs"


def main() -> int:
    node = shutil.which("node")
    if not node:
        print("=== Kennung aus der Bezeichnung (JS) ===")
        print("  uebersprungen: node nicht vorhanden -- nicht geprueft")
        return 0
    if not JS.is_file():
        print(f"  FAIL  Testdatei fehlt: {JS}")
        return 1
    p = subprocess.run([node, str(JS)], capture_output=True, text=True, timeout=120)
    print("=== Kennung aus der Bezeichnung (JS) ===")
    sys.stdout.write(p.stdout)
    if p.returncode != 0:
        sys.stdout.write(p.stderr)
        print("  FAIL  node-Test rot")
        return 1
    if "  FAIL" in p.stdout:
        # Doppelt gesichert: eine gerissene Pruefung mit rc 0 waere stiller
        # Erfolg. (Nicht auf "FAIL" schlechthin pruefen -- die Schlusszeile
        # heisst "0 rot".)
        print("  FAIL  Ausgabe nennt FAIL, rc war aber 0")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
