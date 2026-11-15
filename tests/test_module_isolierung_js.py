"""JS-Wächter: alle Web-Module teilen sich EINEN Namensraum.

Befund smilez (15.11.2026): *„der Reiter Einstellungen ist vorhanden, aber
leer"*. Die Modulskripte sind klassische Skripte — sie laufen alle im selben
globalen Bereich, wie mehrere `<script>`-Blöcke einer Seite. `anzeige.js`
deklariert `const STIL`, `einstellungen.js` tat es auch: ein SyntaxError, der
das **ganze** Skript tötet. `customElements.define` lief nie, der Reiter blieb
leer und **stumm** (die Datei wurde ja geladen, `onerror` feuerte nicht).

`tests/js/module_isolierung.mjs` fasst deshalb alle Module zu einem Skript
zusammen und prüft, dass danach jedes Element definiert ist. Dieser Rahmen
nimmt den Test in die CI-Schleife mit.

Ohne `node` **übersprungen**, nicht grün.

Aufruf: python3 tests/test_module_isolierung_js.py
Gegenprobe: python3 tests/gegenprobe_module_isolierung.py
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

HIER = Path(__file__).resolve().parent
JS = HIER / "js" / "module_isolierung.mjs"

def main() -> int:
    node = shutil.which("node")
    print("=== Module im gemeinsamen Namensraum (JS) ===")
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
