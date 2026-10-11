#!/usr/bin/env python3
"""Gegenprobe zu test_displays.py (Regel 9): Je eine Zusage des Treiber-
pakets wird in einer KOPIE des Quellbaums verfaelscht; der Test laeuft gegen
die Kopie und muss rot werden -- und zwar am erwarteten Pruefpunkt.

Eine Mutation, die die Datei nicht veraendert (Muster fehlt), ist selbst ein
Fehler: sonst „faengt" der Test eine Mutation, die nie stattfand.

Aufruf: python3 tests/gegenprobe_displays.py   (braucht kein PYTHONPATH)
"""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TEST = REPO / "tests" / "test_displays.py"
PASS = FAIL = 0


def ok(m):
    global PASS
    PASS += 1
    print(f"  ok    {m}")


def bad(m):
    global FAIL
    FAIL += 1
    print(f"  FAIL  {m}")


def lauf(src: Path) -> tuple[int, str]:
    env = dict(os.environ, PYTHONPATH=str(src), CHIMERA_SRC=str(src))
    env.pop("CHIMERA_ROOT", None)
    env.pop("CHIMERA_ANZEIGE", None)
    r = subprocess.run([sys.executable, str(TEST)], env=env, capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


def mutation(name: str, datei: str, alt: str, neu: str, erwartet: str) -> None:
    with tempfile.TemporaryDirectory() as d:
        src = Path(d) / "src"
        shutil.copytree(REPO / "src", src)
        ziel = src / datei
        text = ziel.read_text(encoding="utf-8")
        if text.count(alt) != 1:
            bad(f"{name}: Muster {alt!r} {text.count(alt)}x in {datei} (erwartet genau 1)")
            return
        ziel.write_text(text.replace(alt, neu), encoding="utf-8")
        rc, aus = lauf(src)
        if rc == 0:
            bad(f"{name}: Test blieb gruen")
        elif f"FAIL  {erwartet}" in aus:
            ok(f"{name}: rot bei '{erwartet}'")
        else:
            bad(f"{name}: rot, aber nicht bei '{erwartet}'")
            for z in aus.splitlines():
                if "FAIL" in z:
                    print("        " + z.strip())


print("=== Gegenprobe Treiberpaket ===")
rc, aus = lauf(REPO / "src")
if rc == 0:
    ok("unveraendert gruen")
else:
    bad("unveraendert schon rot -- Gegenprobe nicht aussagekraeftig")
    print(aus[-800:])

# M1: „eingerichtet" waehlt doch (die Haltung vor smilez' Entscheidung).
mutation("eingerichtet-waehlt", "chimera/displays/erkennen.py",
         'elif klasse == "eindeutig" and treffer is True:',
         'elif klasse in ("eindeutig", "eingerichtet") and treffer is True:',
         "eingerichtet waehlt nicht")

# M2: Pflicht verletzt wird ignoriert -> falsche Kennung waehlt trotzdem.
mutation("pflicht-ignoriert", "chimera/displays/erkennen.py",
         "if pflicht_da and pflicht_ok is False:\n            continue",
         "if False:\n            continue",
         "falsche Kennung: Rueckfall")

# M3: Mehrdeutig wird geraten -- erster Kandidat gewinnt, obwohl CHIMERA_ANZEIGE
#     unbekannt ist.
mutation("einstellung-geraten", "chimera/displays/erkennen.py",
         "return Befund(None, f\"CHIMERA_ANZEIGE={einstellung!r} ist kein bekanntes Modul \"",
         "return Befund(next(iter(profile)), f\"CHIMERA_ANZEIGE={einstellung!r} ist kein bekanntes Modul \"",
         "unbekannte Einstellung waehlt nichts")

# M4: Die Fassade verschluckt den Grund -- Defekt sieht aus wie „keine".
mutation("fassade-ohne-grund", "chimera/display/panel.py",
         'p.hinweis = f"Anzeige {typ} ({quelle}) nicht zu öffnen: {exc}"',
         'p.hinweis = ""',
         "defekte Anzeige: Grund steht da")

# M5: Die Fassade liest state/anzeige nicht mehr (nur noch die Umgebung).
mutation("fassade-ohne-state", "chimera/display/panel.py",
         'wert = pfad.read_text(encoding="utf-8").strip()',
         'wert = ""',
         "state/anzeige: Modul geoeffnet")

# M6: Ausdruecklich verlangtes Modul faellt still auf NullPanel zurueck.
mutation("fassade-schluckt-explizit", "chimera/display/panel.py",
         'if kind != "auto":\n            raise',
         'if False:\n            raise',
         "ausdruecklich verlangtes Modul: Fehler schlaegt durch")

# M7: Registry prueft nicht mehr, dass typ == Ordnername.
mutation("registry-ohne-typpruefung", "chimera/displays/registry.py",
         "if p.typ != o.name:",
         "if False:",
         "falscher typ: Modul uebersprungen")

print()
print(f"Ergebnis: {PASS} ok, {FAIL} fehlgeschlagen")
sys.exit(1 if FAIL else 0)
