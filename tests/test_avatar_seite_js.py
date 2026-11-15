"""JS-Test der Avatar-Seite (ohne Browser).

Wie beim Bild (tests/test_anzeige_bild_js.py): `anzeige.js` ist eine
Web-Komponente, aber was schiefgehen kann, ist eine Rechnung — was die Seite
**vor** dem Klick über eine Vorschau behauptet. Diese Ankündigung prüft
`tests/js/avatar_seite.mjs` an der echten Datei.

Dieser Python-Rahmen existiert nur, damit die CI-Schleife
(`for t in tests/test_*.py`) den JS-Test mitnimmt. Ohne `node` ist der Test
**übersprungen**, nicht grün.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

HIER = Path(__file__).resolve().parent
ROOT = Path(os.environ.get("CHIMERA_ROOT_TEST") or HIER.parent)
JS = HIER / "js" / "avatar_seite.mjs"

def main() -> int:
    node = shutil.which("node")
    print("=== Avatar-Seite (JS) ===")
    if not node:
        print("  uebersprungen: node nicht vorhanden -- nicht geprueft")
        return 0
    if not JS.is_file():
        print(f"  FAIL  Testdatei fehlt: {JS}")
        return 1
    env = dict(os.environ,
               CHIMERA_ANZEIGE_JS=str(ROOT / "rust/crates/tor/web/module/anzeige/anzeige.js"))
    p = subprocess.run([node, str(JS)], capture_output=True, text=True,
                       timeout=120, env=env)
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
