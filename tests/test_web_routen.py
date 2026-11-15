"""Abgleich: Jede Route, die ein Web-Modul ruft, bedient das Gateway auch.

Warum dieser Test: Am 13.11.2026 schickte der Dienst `freigaben_lesen`, das
Gateway kannte nur `freigabe_lesen` — die Erinnerung hätte nie geklingelt, und
alle Tests waren grün, weil die Attrappe auf jeden Namen antwortete. Derselbe
Fehler kann zwischen einem Modul (JavaScript) und dem Gateway (Rust) passieren:
Ein Name wird auf einer Seite umbenannt, die andere merkt es erst, wenn jemand
im Browser auf den Knopf drückt.

Geprüft wird zweierlei, je Aufruf `<modul>/<weg>` aus `web/module/*/*.js`:

1. **Der Verteiler kennt das Modul** — `starts_with("/api/<modul>/")` steht in
   `web.rs`. Fehlt es, landet der Aufruf bei „nicht gefunden" (404).
2. **Der Weg ist irgendwo im Gateway benannt** — der Name steht als Zeichenkette
   in `web.rs`. Ein umbenannter Weg (oder ein Tippfehler im Modul) fällt damit
   auf, ohne dass man jede Route einzeln verdrahten muss.

Die zweite Prüfung ist absichtlich grob: Sie kann einen Namen übersehen, der
zufällig auch als JSON-Schlüssel vorkommt. Sie kann aber nicht *still* grün
sein, wenn ein Weg nirgends steht — und genau das ist der gefährliche Fall.

Aufruf: python3 tests/test_web_routen.py
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

HIER = Path(__file__).resolve().parent
ROOT = Path(os.environ.get("CHIMERA_ROOT_TEST") or HIER.parent)
WEB_RS = ROOT / "rust/crates/tor/src/web.rs"
MODULE = ROOT / "rust/crates/tor/web/module"

#: Aufrufe, die kein „weg" im Verteiler sind: die Moduldateien selbst.
KEINE_ROUTEN = ("/api/module", "/api/login", "/api/logout", "/api/einrichtung")

PASS = 0
FAIL = 0


def check(name: str, ist, soll) -> None:
    global PASS, FAIL
    if ist == soll:
        PASS += 1
        print(f"  ok    {name}")
    else:
        FAIL += 1
        print(f"  FAIL  {name} -- erwartet {soll!r}, bekam {ist!r}")


def aufrufe(text: str) -> set[tuple[str, str]]:
    return set(re.findall(r"/api/([a-z-]+)/([a-z0-9_-]+)", text))


def main() -> int:
    print("=== Web-Module gegen Gateway-Routen ===")
    if not WEB_RS.is_file() or not MODULE.is_dir():
        print(f"  FAIL  Pfad fehlt: {WEB_RS} / {MODULE}")
        return 1
    web = WEB_RS.read_text(encoding="utf-8")

    dateien = sorted(MODULE.glob("*/*.js"))
    check("Module gefunden", bool(dateien), True)
    gesamt = 0
    for f in dateien:
        modul = f.parent.name
        text = f.read_text(encoding="utf-8")
        for m, weg in sorted(aufrufe(text)):
            if f"/api/{m}/{weg}" in KEINE_ROUTEN:
                continue
            gesamt += 1
            check(f"{modul}: Verteiler kennt /api/{m}/",
                  f'starts_with("/api/{m}/")' in web, True)
            check(f"{modul}: /api/{m}/{weg} ist im Gateway benannt",
                  f'"{weg}"' in web, True)

    # Ein Test, der nichts gefunden hat, wäre der stille Erfolg: Er prüft dann
    # nur sich selbst. Deshalb muss die Menge plausibel groß sein und der
    # Parser an einem Beispiel nachweislich greifen.
    check("mindestens 20 Aufrufe gefunden", gesamt >= 20, True)
    probe = aufrufe('chimera.api("/api/chat/senden", {}); chimera.api(`/api/anzeige/bild?seit=1`)')
    check("Parser sieht zwei Aufrufe im Beispiel", len(probe), 2)
    check("Parser nimmt den Weg ohne Abfrageteil",
          ("anzeige", "bild") in probe, True)

    print(f"\nErgebnis: {PASS} ok, {FAIL} fehlgeschlagen ({gesamt} Aufrufe)")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
