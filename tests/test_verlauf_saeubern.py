"""Ein Verlauf aus der Textzeit lehrt den verbotenen Weg (DESIGN, Regel
„Aufrufe, nicht Text", Nachtrag 15.11.2026).

Am Pi gemessen: Das Modell schrieb `TOOL: …` als Text, obwohl die
Werkzeugschnittstelle aktiv war — weil sein eigener Verlauf 26 solche Zeilen
enthielt und das Ergebnis darauf. Die Rüge half genau eine Runde.

`ablage.abspielen()` baut das Fenster jetzt ohne diese Zeilen. Das Protokoll
bleibt unverändert (Regel 8d).

Aufruf: python3 tests/test_verlauf_saeubern.py [--gegenprobe]
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# CHIMERA_SRC laesst die Gegenprobe eine veraenderte Kopie pruefen, ohne den
# echten Quellbaum anzufassen (Muster aus test_freigabe_erinnerung.py).
sys.path.insert(0, str(Path(os.environ.get("CHIMERA_SRC") or ROOT / "src")))

from chimera.ablage import abspielen  # noqa: E402

GEGENPROBE = "--gegenprobe" in sys.argv
PASS = FAIL = 0

def ok(m):
    global PASS
    PASS += 1
    print(f"  ok    {m}")

def bad(m):
    global FAIL
    FAIL += 1
    print(f"  FAIL  {m}")

def check(m, got, want):
    ok(m) if got == want else bad(f"{m} — erwartet {want!r}, bekam {got!r}")

def nachricht(rolle, inhalt):
    return {"art": "nachricht", "rolle": rolle, "inhalt": inhalt}

print("== ein Textaufruf fliegt aus dem Fenster ==")
protokoll = [
    nachricht("user", "setze das gesicht auf CHAOS"),
    nachricht("assistant", 'TOOL: set_face {"mood": "CHAOS", "hard": "ja"}'),
    nachricht("user", "Ergebnis von set_face:\nAusdruck gesetzt: CHAOS (sofort)"),
    nachricht("assistant", "Erledigt."),
]
fenster = abspielen(protokoll)
check("Aufruf weg", [m["content"] for m in fenster],
      ["setze das gesicht auf CHAOS", "Erledigt."])

print("== Text neben dem Aufruf bleibt stehen ==")
fenster = abspielen([
    nachricht("assistant", 'Ich lege das an.\nTOOL: mood_anlegen {"name": "T"}'),
    nachricht("user", "Ergebnis von mood_anlegen:\nAngelegt: T"),
])
check("Text bleibt, Aufruf geht", [m["content"] for m in fenster],
      ["Ich lege das an."])

print("== normale Nachrichten bleiben unangetastet ==")
unberuehrt = [
    nachricht("user", "Was kannst du?"),
    nachricht("assistant", "Ich habe Werkzeuge. TOOL: steht nur im Beispiel."),
    nachricht("user", "Danke."),
]
fenster = abspielen(unberuehrt)
check("nichts verändert", [m["content"] for m in fenster],
      ["Was kannst du?", "Ich habe Werkzeuge. TOOL: steht nur im Beispiel.",
       "Danke."])

print("== ein Ergebnis ohne Aufruf bleibt nicht stehen ==")
fenster = abspielen([
    nachricht("user", "hallo"),
    nachricht("tool", "Ergebnis von moods:\n- IDLE"),
])
check("Ergebnis weg", [m["content"] for m in fenster], ["hallo"])

print("== das Protokoll selbst wird nicht angefasst ==")
check("Eingabe unverändert", protokoll[1]["inhalt"].startswith("TOOL:"), True)
check("gleiche Anzahl Nachrichten", len(protokoll), 4)

if GEGENPROBE:
    print("== Gegenprobe: ohne Bereinigung muss es rot werden ==")
    import chimera.ablage as ab
    roh = ab.ohne_textaufrufe
    ab.ohne_textaufrufe = lambda f: f          # die alte Fassung
    try:
        fenster = abspielen(protokoll)
        check("Gegenprobe: Aufruf weg", [m["content"] for m in fenster],
              ["setze das gesicht auf CHAOS", "Erledigt."])
    finally:
        ab.ohne_textaufrufe = roh

print()
print(f"Ergebnis: {PASS} ok, {FAIL} fehlgeschlagen")
sys.exit(0 if FAIL == 0 else 1)
