"""Gegenprobe: Die Eingabehöhe nimmt den Text nicht mehr ernst.

Zwei Verfälschungen an einer Kopie von `chat.js` (`CHIMERA_CHAT_JS`):

1. **`eingabeHoehe` ignoriert den Inhalt** — dann bleibt das Feld auf der
   gezogenen Höhe stehen und langer Text wird abgeschnitten statt sichtbar.
2. **`griffHoehe` rechnet die Ziehrichtung falsch** — dann macht Ziehen nach
   oben die Eingabe kleiner; der Griff wäre ein Bedienelement ohne Sinn.

Ohne `node` übersprungen (nicht grün).

Aufruf: python3 tests/gegenprobe_chat_eingabe.py
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
JS = HIER / "js" / "chat_eingabe.mjs"
QUELLE = ROOT / "rust/crates/tor/web/module/chat/chat.js"

VERFAELSCHUNGEN = [
    (
        "Inhalt wird ignoriert (Text abgeschnitten)",
        "  const braucht = Number.isFinite(inhalt) && inhalt > 0 ? inhalt : 0;\n"
        "  return Math.round(Math.min(Math.max(unten, braucht), grenze));",
        "  return Math.round(unten);",
    ),
    (
        "Ziehrichtung umgedreht (oben = kleiner)",
        "  const roh = start - (Number.isFinite(dy) ? dy : 0);",
        "  const roh = start + (Number.isFinite(dy) ? dy : 0);",
    ),
]

def lauf(datei: Path) -> int:
    env = dict(os.environ, CHIMERA_CHAT_JS=str(datei))
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

    rot = 0
    text = QUELLE.read_text(encoding="utf-8")
    with tempfile.TemporaryDirectory() as tmp:
        for i, (name, alt, neu) in enumerate(VERFAELSCHUNGEN, 1):
            if alt not in text:
                print(f"  FAIL  Stelle {i} nicht gefunden in chat.js")
                return 1
            ziel = Path(tmp) / f"chat-{i}.js"
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
