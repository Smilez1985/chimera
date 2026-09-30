"""Tests für die Statuszeile (Regel 7c).

Ausgeführt mit:  PYTHONPATH=src python3 tests/test_statusline.py

Geprüft wird, dass die Zeile den gemeinsamen Verwalter benutzt und nicht
eine eigene Auflösung mitbringt -- das ist der Punkt der Regel.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from chimera.arbiter import Arbiter  # noqa: E402
from chimera.display.statusline import (  # noqa: E402
    QUELLEN,
    REIHENFOLGE,
    StatusLine,
)

OK = 0
BAD = 0


def pruefe(name: str, ist, soll) -> None:
    global OK, BAD
    if ist == soll:
        OK += 1
        print(f"  ok    {name}")
    else:
        BAD += 1
        print(f"  FEHL  {name}")
        print(f"        erwartet: {soll!r}")
        print(f"        bekommen: {ist!r}")


def wahr(name: str, bedingung) -> None:
    pruefe(name, bool(bedingung), True)


print("=== Statuszeile ===")

# --- Der Katalog hält die eigene Regel ein ---------------------------------

pruefe("Quellenkatalog hält die Abstandsregel ein",
       Arbiter.abstaende_pruefen(QUELLEN), [])
wahr("die Reihenfolge nennt jede Quelle",
     set(REIHENFOLGE) == set(QUELLEN))
pruefe("die Reihenfolge ist so lang wie der Katalog",
       len(REIHENFOLGE), len(QUELLEN))

# --- Grundverhalten --------------------------------------------------------

sl = StatusLine(hoehe=40)
pruefe("leer: kein Text", sl.text(0), None)

sl.melden("agentenstatus", "denkt nach", jetzt_ms=1000)
pruefe("einzige Meldung wird angezeigt", sl.text(1000), "denkt nach")

sl.melden("hitze", "zu heiss", jetzt_ms=1000)
pruefe("die wichtigere Quelle gewinnt", sl.text(1000), "zu heiss")
pruefe("und sie wird auch benannt", sl.quelle(1000), "hitze")

sl.zuruecknehmen("hitze")
pruefe("nach dem Zurücknehmen greift die darunter",
       sl.text(1000), "denkt nach")

# --- Unbekannte Quelle wird abgelehnt, nicht geraten ----------------------

try:
    sl.melden("erfunden", "x", jetzt_ms=0)
    wahr("unbekannte Quelle wird abgelehnt", False)
except KeyError as exc:
    wahr("unbekannte Quelle wird abgelehnt", True)
    wahr("die Meldung nennt die bekannten Quellen", "agentenstatus" in str(exc))

# --- Laufzeit und Erneuerung ----------------------------------------------

sl2 = StatusLine()
sl2.melden("antwort", "kurz da", jetzt_ms=0, laufzeit_ms=500)
pruefe("vor Ablauf sichtbar", sl2.text(499), "kurz da")
pruefe("nach Ablauf weg", sl2.text(500), None)

heiss = {"wert": True}
sl3 = StatusLine()
sl3.melden("hitze", "zu heiss", jetzt_ms=0, laufzeit_ms=1000,
           erneuern=lambda: heiss["wert"])
pruefe("solange heiss, bleibt die Warnung", sl3.text(60_000), "zu heiss")
heiss["wert"] = False
pruefe("kühlt es ab, verschwindet sie von selbst", sl3.text(60_000), None)

# --- Ein Platz je Quelle ---------------------------------------------------

sl4 = StatusLine()
sl4.melden("agentenstatus", "hört zu", jetzt_ms=0)
sl4.melden("agentenstatus", "denkt nach", jetzt_ms=10)
sl4.melden("agentenstatus", "antwortet", jetzt_ms=20)
pruefe("nur die jüngste Meldung der Quelle gilt",
       sl4.text(30), "antwortet")

# --- Der Katalog passt zu Chimera, nicht zur Vorlage ----------------------
#
# HATFaces hat Quellen für Gateway-Befehle und Plugin-Hinweise. Beides gibt
# es hier nicht -- übernommen wurde das Modell, nicht die Liste.
wahr("kein Gateway-Befehl im Katalog",
     not any("node" in q or "gateway" in q for q in QUELLEN))
wahr("dafür der Anbieterausfall, den nur Chimera hat",
     "anbieter_weg" in QUELLEN)

# --- Zeichnen --------------------------------------------------------------

try:
    from PIL import Image
    hat_pillow = True
except ImportError:
    hat_pillow = False

if hat_pillow:
    sl5 = StatusLine(hoehe=40)
    bild = Image.new("RGB", (240, 280), (10, 10, 10))

    unveraendert = sl5.zeichnen(bild, jetzt_ms=0)
    wahr("ohne Meldung wird das Bild zurückgegeben", unveraendert is bild)
    pruefe("und nichts gezeichnet",
           bild.getpixel((120, 260)), (10, 10, 10))

    sl5.melden("hitze", "zu heiss", jetzt_ms=0)
    sl5.zeichnen(bild, jetzt_ms=0)
    wahr("mit Meldung wird im unteren Rand gezeichnet",
         bild.getpixel((120, 260)) != (10, 10, 10))
    pruefe("und oben nichts angefasst",
           bild.getpixel((120, 100)), (10, 10, 10))
else:
    print("  hinw  Pillow fehlt -- Zeichentests übersprungen")

# --- Gegenproben -----------------------------------------------------------

print()
print("=== Gegenproben ===")

# 1. Der Katalog MUSS die Abstandsregel verletzen können -- sonst prüft der
#    Test oben nichts.
kaputt = dict(QUELLEN)
kaputt["dazwischen"] = QUELLEN["hitze"] - 1
wahr("Gegenprobe: ein zu enger Katalog wird beanstandet",
     len(Arbiter.abstaende_pruefen(kaputt)) >= 1)

# 2. Und die Statuszeile darf mit so einem Katalog nicht starten. Das ist
#    der Unterschied zwischen einer geprüften und einer behaupteten Regel.
import chimera.display.statusline as modul  # noqa: E402

alt = modul.QUELLEN
try:
    modul.QUELLEN = kaputt
    try:
        modul.StatusLine()
        wahr("Gegenprobe: mit kaputtem Katalog startet sie nicht", False)
    except ValueError as exc:
        wahr("Gegenprobe: mit kaputtem Katalog startet sie nicht", True)
        wahr("und die Meldung nennt den Grund", "Abstand" in str(exc))
finally:
    modul.QUELLEN = alt

# 3. Die Zeile darf keine eigene Auflösung mitbringen. Prüfbar daran, dass
#    sie einen Arbiter benutzt -- baute sie eine eigene Sortierung, wäre
#    das die Doppelimplementierung, die Regel 7c verhindern soll.
sl6 = StatusLine()
wahr("die Zeile benutzt den gemeinsamen Verwalter",
     isinstance(sl6._arbiter, Arbiter))

print()
print(f"Ergebnis: {OK} ok, {BAD} fehlgeschlagen")
sys.exit(1 if BAD else 0)
