#!/usr/bin/env python3
"""Tests für die Tastengesten (Regel 7d: reine Funktion der Zeit).

Fünf Absichten auf einer Taste: kurz, lang, halten, doppelt, dreifach.
Geprüft werden Zeitpunkte, nicht Sekunden — kein Test schläft, außer dem
einen für den Taktgeber (der ist ohne Warten nicht prüfbar).
"""

import os
import sys
import time
from pathlib import Path

SRC = Path(os.environ.get("CHIMERA_SRC")
           or Path(__file__).resolve().parent.parent / "src")
sys.path.insert(0, str(SRC))

from chimera.display.gesten import (  # noqa: E402
    Gesten, GestenTakt, ALLE, KURZ, LANG, HALTEN, HALTEN_ENDE, DOPPELT,
    DREIFACH,
)

PASS = FAIL = 0

def ok(m):
    global PASS; PASS += 1; print(f"  ok    {m}")

def bad(m):
    global FAIL; FAIL += 1; print(f"  FAIL  {m}")

def check(m, got, want):
    ok(m) if got == want else bad(f"{m} — erwartet {want!r}, bekam {got!r}")


print("== 1. Die fünf Gesten ==")

# kurz: 0,3 s gedrückt, danach Fenster abwarten
g = Gesten()
check("Drücken meldet nichts", g.taste(True, 0.0), [])
check("Loslassen meldet nichts (Fenster offen)", g.taste(False, 0.3), [])
check("kurz am Fensterende", g.tick(1.1), [KURZ])
check("kurz wird nicht wiederholt", g.tick(5.0), [])

# lang: 1,0 s gedrückt
g = Gesten()
g.taste(True, 0.0)
check("lang beim Loslassen", g.taste(False, 1.0), [LANG])
check("lang zählt nicht als Klick", g.tick(3.0), [])

# halten: geht bei 2,0 s los, ohne Loslassen
g = Gesten()
g.taste(True, 0.0)
check("kurz vor der Schwelle noch nichts", g.tick(1.99), [])
check("halten bei 2,0 s", g.tick(2.0), [HALTEN])
check("halten nur einmal", g.tick(3.0), [])
check("Loslassen beendet das Halten (Push-to-Talk aus)",
      g.taste(False, 3.5), [HALTEN_ENDE])

# doppelt: zwei kurze Drücke im Fenster
g = Gesten()
g.taste(True, 0.0); check("erster Druck", g.taste(False, 0.2), [])
g.taste(True, 0.5); check("zweiter Druck", g.taste(False, 0.7), [])
check("doppelt am Fensterende", g.tick(1.6), [DOPPELT])

# dreifach: drei kurze Drücke
g = Gesten()
for an, aus in ((0.0, 0.2), (0.4, 0.6), (0.8, 1.0)):
    g.taste(True, an); g.taste(False, aus)
check("dreifach am Fensterende", g.tick(2.0), [DREIFACH])

# vier Drücke sind auch dreifach (3+), nicht doppelt
g = Gesten()
for an, aus in ((0.0, 0.2), (0.4, 0.6), (0.8, 1.0), (1.2, 1.4)):
    g.taste(True, an); g.taste(False, aus)
check("vier Drücke: dreifach", g.tick(2.3), [DREIFACH])

# Ein langer Druck zwischen zwei kurzen löscht den Zähler.
g = Gesten()
g.taste(True, 0.0); g.taste(False, 0.2)          # Klick 1
g.taste(True, 0.5); check("lang dazwischen", g.taste(False, 1.5), [LANG])
g.taste(True, 2.0); g.taste(False, 2.2)          # Klick, aber allein
check("nach lang: wieder kurz", g.tick(3.2), [KURZ])


print("== 2. Randfälle ==")
g = Gesten()
check("Loslassen ohne Drücken wird ignoriert", g.taste(False, 1.0), [])
check("… und erzeugt später keinen Klick", g.tick(5.0), [])
check("Doppeltes Drücken startet nicht neu", (g.taste(True, 2.0), g.taste(True, 2.1)), ([], []))
check("… und hält ab 4,0 s", g.tick(4.0), [HALTEN])

g = Gesten()
g.taste(True, 0.0)
check("halten löst kein zweites Mal aus, wenn das Loslassen fehlt",
      (g.tick(10.0), g.taste(False, 10.5)), ([HALTEN], [HALTEN_ENDE]))

try:
    Gesten(kurz_max_s=2.0, halten_ab_s=1.0)
    bad("unsinnige Schwellen — erwartet ValueError, bekam keinen")
except ValueError:
    ok("unsinnige Schwellen werden abgewiesen")

check("ALLE nennt fünf Gesten", len(ALLE), 5)


print("== 3. Die Frist für den Taktgeber ==")
g = Gesten()
check("nichts geplant: keine Frist", g.frist(), None)
g.taste(True, 0.0)
check("gedrückt: Frist ist die Haltenschwelle", g.frist(), 2.0)
g.taste(False, 0.2)
_frist = g.frist()
check("nach kurzem Druck: Frist ist das Klickfenster",
      round(_frist, 3) if _frist is not None else None, 1.0)
g.tick(1.0)
check("nach der Entscheidung: keine Frist", g.frist(), None)


print("== 4. Der Taktgeber wartet wirklich auf die Frist ==")
# Ohne echtes Warten nicht prüfbar; die Schwellen sind hier winzig.
gesehen = []
g = Gesten(kurz_max_s=0.05, halten_ab_s=0.2, fenster_s=0.08)
takt = GestenTakt(g, gesehen.append).start()
try:
    g.taste(True, time.monotonic())
    takt.anstoss()
    time.sleep(0.03)
    g.taste(False, time.monotonic())
    takt.anstoss()
    time.sleep(0.3)
finally:
    takt.stop()
check("der Taktgeber meldet die kurze Geste", gesehen, [KURZ])

print(f"\nErgebnis: {PASS} ok, {FAIL} fehlgeschlagen")
sys.exit(0 if FAIL == 0 else 1)
