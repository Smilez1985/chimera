"""Werkzeugkennung im Verlaufsprotokoll (15.11.2026).

Fund aus der Übergabe: `Verlauf.append` schrieb nur Rolle und Text — welches
Werkzeug gerufen wurde und was es zurückgab, war im gespeicherten Protokoll
nicht mehr zu sehen. Ohne diese Angaben lässt sich hinterher weder ein Turn
nachvollziehen noch ein Verlauf nach einem Neustart fortsetzen.

Geprüft wird an echten Dateien: Protokoll schreiben, aus dem Protokoll
abspielen, vergleichen.

Aufruf: python3 tests/test_protokoll_werkzeuge.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(os.environ.get("CHIMERA_SRC") or ROOT / "src")))

from chimera import ablage as ab  # noqa: E402

PASS = FAIL = 0


def ok(m):
    global PASS
    PASS += 1
    print(f"  ok    {m}")


def bad(m):
    global FAIL
    FAIL += 1
    print(f"  FAIL  {m}")


def pruefe(ist, soll, was):
    if ist == soll:
        ok(f"{was}: {ist!r}")
    else:
        bad(f"{was}: {ist!r} (erwartet {soll!r})")


mit_tmp = tempfile.TemporaryDirectory()
wurzel = Path(mit_tmp.name) / "ablage"
ablage = ab.Ablage(wurzel)
verlauf = ab.Verlauf(ablage, [])

print("== 1. Der Aufruf steht im Protokoll")
verlauf.append({"role": "user", "content": "Wie viel Speicher?"})
verlauf.append({"role": "assistant", "content": "",
                "gedacht": "erst nachsehen",
                "tool_calls": [{"function": {"name": "status",
                                             "arguments": {"mit_befehlen": True}}}]})
verlauf.append({"role": "tool", "content": "144 MB frei", "tool_name": "status"})

zeilen = [json.loads(z) for z in
          (wurzel / "sitzungen" / verlauf.sitzung / "verlauf.jsonl")
          .read_text(encoding="utf-8").splitlines() if z.strip()]
pruefe(len(zeilen), 3, "drei Nachrichten im Protokoll")
pruefe(zeilen[1].get("werkzeuge"),
       [{"name": "status", "argumente": {"mit_befehlen": True}}],
       "Assistenz: Werkzeugname und Argumente")
pruefe(zeilen[1].get("gedacht"), "erst nachsehen", "Assistenz: Denktext")
pruefe(zeilen[2].get("werkzeug"), "status", "Ergebnis: Werkzeugname")

print("== 2. Abspielen gibt sie zurueck")
fenster = ablage.laden()
pruefe(len(fenster), 3, "drei Nachrichten im Fenster")
pruefe(fenster[1].get("tool_calls"),
       [{"function": {"name": "status", "arguments": {"mit_befehlen": True}}}],
       "Aufruf wieder da")
pruefe(fenster[1].get("gedacht"), "erst nachsehen", "Denktext wieder da")
pruefe(fenster[2].get("tool_name"), "status", "Werkzeugname wieder da")

print("== 3. Ein Aufruf ohne Ergebnis wird verworfen")
# Ein Turn kann mitten im Werkzeugaufruf enden. Eine Nachricht mit Aufrufen
# ohne Ergebnisse weist die Schnittstelle ab -- also bleibt der Text, die
# Aufrufe gehen.
halb = ab.abspielen([
    {"art": "nachricht", "rolle": "user", "inhalt": "hallo"},
    {"art": "nachricht", "rolle": "assistant", "inhalt": "einen Moment",
     "werkzeuge": [{"name": "status", "argumente": {}}]},
])
pruefe(halb[1].get("tool_calls"), None, "Aufruf ohne Ergebnis ist weg")
pruefe(halb[1].get("content"), "einen Moment", "der Text bleibt")

print("== 4. Alte Protokolle ohne die Felder bleiben lesbar")
alt = ab.abspielen([
    {"art": "nachricht", "rolle": "user", "inhalt": "alt"},
    {"art": "nachricht", "rolle": "assistant", "inhalt": "Antwort"},
])
pruefe([m["content"] for m in alt], ["alt", "Antwort"], "unveraendert lesbar")
pruefe("tool_calls" in alt[1], False, "kein leeres Feld erfunden")

mit_tmp.cleanup()
print()
print(f"Ergebnis: {PASS} ok, {FAIL} fehlgeschlagen")
sys.exit(0 if FAIL == 0 else 1)
