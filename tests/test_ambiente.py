"""Selbsttaetige Aktionen: Fenster, Abstand, Ruhe (DESIGN, Regel „Ambiente").

Fund smilez (15.11.2026): *„das Display sollte per Design und readme.md immer
den ehrlichen Zustand anzeigen, und ab und zu Bing rauchen oder Joint rauchen,
morgens Kaffee trinken etc. automatisch ausführen"*.

Geprüft wird die echte Entscheidung (`agent/ambiente.py`) mit eingesetzter Uhr
und eingesetztem Zufall -- kein Nachbau der Regel. Dazu die eine Bedingung,
die den ehrlichen Zustand traegt: `Face.laeuft`.

Aufruf: python3 tests/test_ambiente.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(os.environ.get("CHIMERA_SRC") or ROOT / "src")))

from chimera.agent.ambiente import (  # noqa: E402
    CHANCE, MIN_ABSTAND_S, SPERRE_JE_AUSDRUCK_S, Ambiente, kandidaten)
from chimera.agent.face import Face  # noqa: E402
from chimera.mood.registry import Registry  # noqa: E402
from chimera.render.avatar import State  # noqa: E402

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


class Uhr:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t

    def vor(self, s: float) -> None:
        self.t += s


class Wuerfel:
    """Fester Zufall: erst der Wurf fuer die Chance, dann der fuer die Wahl."""

    def __init__(self, werte):
        self.werte = list(werte)

    def __call__(self) -> float:
        return self.werte.pop(0) if self.werte else 0.0


ALLE = {"COFFEE", "YAWN", "STRETCH", "CHILL", "ROCK", "MUSIC", "BONG", "JOINT"}


def bau(werte=(0.0, 0.0)):
    uhr, w = Uhr(), Wuerfel(list(werte))
    return Ambiente(uhr=uhr, zufall=w), uhr


print("== 1. Welche Ausdruecke passen zu welcher Stunde")
pruefe(kandidaten(7)[0], "COFFEE", "frueh: Kaffee zuerst")
pruefe("ROCK" in kandidaten(12), True, "tagsueber: ROCK dabei")
pruefe("BONG" in kandidaten(20), True, "abends: BONG dabei")
pruefe(kandidaten(2), (), "nachts: nichts")
pruefe(kandidaten(23), (), "23 Uhr ist Nacht")
pruefe(kandidaten(6)[0], "COFFEE", "6 Uhr ist frueh")

print("== 2. Ohne Ruhe passiert nichts")
amb, uhr = bau()
pruefe(amb.tick(stunde=7, frei=False, haelt=False, vorhanden=ALLE), None,
       "laufender Auftrag: keine Aktion")
amb, uhr = bau()
pruefe(amb.tick(stunde=20, frei=True, haelt=True, vorhanden=ALLE), None,
       "laufender Ausdruck: keine Aktion")

print("== 3. Eine Aktion, dann Ruhe im Mindestabstand")
amb, uhr = bau((0.0, 0.0))
erste = amb.tick(stunde=7, frei=True, haelt=False, vorhanden=ALLE)
pruefe(erste, "COFFEE", "erste Aktion morgens")
uhr.vor(MIN_ABSTAND_S - 1)
pruefe(amb.tick(stunde=7, frei=True, haelt=False, vorhanden=ALLE), None,
       "kurz vor dem Mindestabstand: nichts")
uhr.vor(2)
zweite = amb.tick(stunde=7, frei=True, haelt=False, vorhanden=ALLE)
pruefe(zweite is not None and zweite != "COFFEE", True,
       "nach dem Abstand: ein anderer Ausdruck (COFFEE ist gesperrt)")

print("== 4. Derselbe Ausdruck kommt nicht sofort wieder")
amb, uhr = bau((0.0, 0.0))
amb.tick(stunde=20, frei=True, haelt=False, vorhanden=ALLE)
uhr.vor(MIN_ABSTAND_S + 1)
zweite = amb.tick(stunde=20, frei=True, haelt=False, vorhanden=ALLE)
pruefe(zweite in ("BONG", "JOINT", "CHILL"), True,
       "abends nach dem Abstand: aus dem Abendfenster")
uhr.vor(MIN_ABSTAND_S + 1)
dritte = amb.tick(stunde=20, frei=True, haelt=False, vorhanden=ALLE)
pruefe(dritte is not None and dritte != zweite, True,
       "auch der zweite wiederholt sich nicht sofort")

print("== 5. Die Sperre je Ausdruck greift, wenn nichts anderes da ist")
amb, uhr = bau((0.0, 0.0))
amb.tick(stunde=7, frei=True, haelt=False, vorhanden={"COFFEE"})
uhr.vor(MIN_ABSTAND_S + 1)
pruefe(amb.tick(stunde=7, frei=True, haelt=False, vorhanden={"COFFEE"}), None,
       "COFFEE gesperrt: keine Wahl statt Wiederholung")
uhr.vor(SPERRE_JE_AUSDRUCK_S)
pruefe(amb.tick(stunde=7, frei=True, haelt=False, vorhanden={"COFFEE"}),
       "COFFEE", "nach der Sperre wieder erlaubt")

print("== 6. Der Zufall entscheidet, aber gedeckelt")
amb, uhr = bau((0.99, 0.0))
pruefe(amb.tick(stunde=7, frei=True, haelt=False, vorhanden=ALLE), None,
       f"Wurf ueber CHANCE ({CHANCE}): nichts")
amb, uhr = bau((0.0, 0.0))
pruefe(amb.tick(stunde=7, frei=True, haelt=False, vorhanden=ALLE) is not None,
       True, "Wurf unter CHANCE: eine Aktion")

print("== 7. Eine kleinere Bibliothek ist kein Fehler")
amb, uhr = bau((0.0, 0.0))
pruefe(amb.tick(stunde=20, frei=True, haelt=False,
                vorhanden={"CHILL", "IDLE"}), "CHILL",
       "nur was es gibt")

print("== 8. Face.laeuft sagt, ob gerade gesperrt ist")
reg = Registry.load(ROOT / "data" / "moods-builtin.json")
st = State()
uhr = Uhr()
face = Face(reg, st, clock=uhr)
pruefe(face.laeuft, False, "frisch: nichts laeuft")
face.set_by_name("BONG")                  # dauer_s = 13 s
pruefe(face.laeuft, True, "Zug laeuft: gesperrt")
uhr.vor(13.5)
pruefe(face.laeuft, False, "Zug vorbei: frei")
face.set_by_name("ROCK")                  # endlos
pruefe(face.laeuft, False, "endloser Ausdruck sperrt nicht")

print("== 9. Der Dienst ruft den Takt wirklich (Verdrahtung) ==")
# Ohne diesen Punkt waere das Modul gebaut, aber nicht einghaengt -- der
# Fehler, der am 15.11. beim Verbrauch Zeit gekostet hat (Op gesendet,
# niemand liest sie). Der Takt wird auf 50 ms gestellt, damit der Test nicht
# wartet; die Notbremse haelt ihn an, falls er nie ruft.
import threading  # noqa: E402

from chimera import __main__ as dienst_modul  # noqa: E402

alt_takt = dienst_modul.ANBIETER_TAKT_S
dienst_modul.ANBIETER_TAKT_S = 0.05


class FalscherDienst:
    """Nur so viel, wie `dienst()` anfasst."""

    def __init__(self, stop):
        self.stop = stop
        self.gerufen = 0
        self.notes = []
        self.renderer = None
        self.registry = type("R", (), {"available": lambda _s: []})()
        self.session = None

    def start_display(self):
        return False

    def ambient_takt(self):
        self.gerufen += 1
        if self.gerufen >= 3:
            self.stop.set()
        return None


stop = threading.Event()
doppel = FalscherDienst(stop)
notbremse = threading.Timer(10.0, stop.set)
notbremse.start()
try:
    rc = dienst_modul.dienst(doppel, stop=stop, env={})
finally:
    notbremse.cancel()
    dienst_modul.ANBIETER_TAKT_S = alt_takt
pruefe(rc, 0, "Dienst endet sauber")
pruefe(doppel.gerufen >= 3, True, "Dienst ruft den Ambiente-Takt")

print()
print(f"Ergebnis: {PASS} ok, {FAIL} fehlgeschlagen")
sys.exit(0 if FAIL == 0 else 1)
