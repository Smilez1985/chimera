"""Ein vom Agenten gesetztes Gesicht bleibt stehen (15.11.2026, smilez).

Befund: *„wenn das Modell auf meine Ansage hin einen Befehl für das Gesicht
rausschickt, wird das so schnell abgespielt … das es kaum zu sehen und sofort
vorbei ist"*.

Nachgemessen (nicht geraten): Die Bewegung der eingebauten Moods ist in
Ordnung — ihre Schwingungen liegen zwischen 0,5 s und 21 s je Periode. Was zu
kurz war, ist die **Standzeit**: `set_face` setzte den Ausdruck, 0,45 s später
blendete der Zustand ``arbeitet`` darauf (``Transition.DEFAULT_DURATION``),
und der Ausdruck war weg. Deshalb hält ein bewusst gesetztes Gesicht jetzt
``HALT_S`` Sekunden (Vorgabe 5 s), bevor ein Zustand es übernehmen darf. Ein
Reflex (``verwirrt``, ``fehler``) bricht die Frist — ein Schreck blendet nicht
ein (Regel 6b).

Geprüft wird der echte ``Face`` mit der echten Bibliothek und einem echten
``State``; nur die Uhr ist eingesetzt, damit der Test nicht wartet.

Aufruf: python3 tests/test_gesicht_haltezeit.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(os.environ.get("CHIMERA_SRC") or ROOT / "src")))

from chimera.agent.face import HALT_S, Face  # noqa: E402
from chimera.render.avatar import State, ablauf_pruefen  # noqa: E402

BUILTIN = ROOT / "data" / "moods-builtin.json"
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
    (ok if ist == soll else bad)(
        f"{was}: {ist!r}" + ("" if ist == soll else f" (erwartet {soll!r})"))


class Uhr:
    def __init__(self) -> None:
        self.t = 500.0

    def __call__(self) -> float:
        return self.t

    def vor(self, sekunden: float) -> None:
        self.t += sekunden


def bau(tmp=None):
    from chimera.mood.registry import Registry
    moods = Registry.load(BUILTIN)
    state = State()
    uhr = Uhr()
    face = Face(moods, state, ablage=None, clock=uhr)
    return face, state, uhr


def aktuell(state):
    return (state.mood_name or "").upper()


print("== 1. Ein gesetzter Ausdruck ist sofort da")
face, state, uhr = bau()
face.set_by_name("CHILL")
pruefe(aktuell(state), "CHILL", "Gesicht nach set_face")

print("== 2. Ohne Dauer ist der Ausdruck das stehende Gesicht (ohne Sperre)")
# Seit 15.11.2026 sperrt nur ein Ausdruck mit fester Länge (smilez: „moods
# wie Rock ohne feste länge … brauchen keine harte Laufzeit"). Ein endloser
# Ausdruck ist das Gesicht der Ruhe, Zustände lösen ihn ab und danach gilt
# er wieder.
face.show_state("arbeitet")
pruefe(aktuell(state), "WORK", "nach 'arbeitet' zeigt der Zustand")
face.show_state("wartet")
pruefe(aktuell(state), "CHILL", "in der Ruhe steht der Ausdruck wieder")
uhr.vor(3600)
face.show_state("denkt")
pruefe(aktuell(state), "CURIOUS", "auch nach einer Stunde: Zustand zuerst")
face.show_state("wartet")
pruefe(aktuell(state), "CHILL", "danach wieder der Ausdruck")

print("== 3. Mit Dauer übernimmt der Zustand nach Ablauf")
face, state, uhr = bau()
face.set_by_name("CHILL", dauer=4)
face.show_state("arbeitet")
pruefe(aktuell(state), "CHILL", "während der Frist")
uhr.vor(3.5)
face.show_state("spricht")
pruefe(aktuell(state), "CHILL", "kurz vor Ablauf")
uhr.vor(0.6)
face.show_state("arbeitet")
pruefe(aktuell(state), "WORK", "nach Ablauf übernimmt 'arbeitet'")

print("== 4. Ein Reflex bricht die Frist (Schreck blendet nicht ein)")
face, state, uhr = bau()
face.set_by_name("CHILL", dauer=6)      # laufender Ausdruck mit Frist
face.show_state("verwirrt")
pruefe(aktuell(state), "CHAOS", "Reflex geht sofort durch")
face.show_state("fehler")
pruefe(aktuell(state), "SAD", "auch 'fehler'")

print("== 5. Ein neuer Befehl setzt die Frist neu")
face, state, uhr = bau()
face.set_by_name("CHILL", dauer=4)
uhr.vor(3.0)
face.set_by_name("ROCK", dauer=4)
uhr.vor(3.0)
face.show_state("arbeitet")
pruefe(aktuell(state), "ROCK", "zweiter Befehl setzt die Frist neu")

print("== 5b. Der Ausdruck bringt seine Dauer selbst mit (Animation mit Ablauf)")
from chimera.mood.blend import mix  # noqa: E402
face, state, uhr = bau()
bong = face.moods.get("BONG")
bong = dict(bong, dauer_s=3.0)
face.state.set_mood(face.moods.get("IDLE"))
face.state.set_mood(bong)
face._agent_mood = "BONG"
face._haelt_bis = uhr() + 3.0
face.state.mood_bis = uhr() + 3.0
face.state.mood_zurueck = face.moods.get("IDLE")
pruefe(round(face._dauer_von(bong, None)), 3, "dauer_s des Ausdrucks gilt")
pruefe(round(face._dauer_von(bong, 0)), 3,
       "0 heißt bei endlichem Ausdruck: einmal ganz")
pruefe(round(face._dauer_von(bong, 9)), 9, "Modell schlägt den Ausdruck")

print("== 6. Am Turn-Ende steht wieder der Agentenausdruck")
face, state, uhr = bau()
face.set_by_name("ROCK", dauer=2)
uhr.vor(3)
face.show_state("spricht")
pruefe(aktuell(state), "SPEAK", "während des Sprechens")
face.show_state("wartet")
pruefe(aktuell(state), "ROCK", "'wartet' kehrt zum Agentengesicht zurück")

print("== 7. Ohne Befehl verhält sich der Zustand wie vorher")
face, state, uhr = bau()
face.show_state("hoert")
pruefe(aktuell(state), "LISTEN", "'hoert'")
face.show_state("wartet")
pruefe(aktuell(state), "IDLE", "'wartet' ohne Agentengesicht → IDLE")

print("== 7b. Nach Ablauf der Dauer kehrt das Gesicht von selbst zurück")
face, state, uhr = bau()
face.set_by_name("IDLE")
face.set_by_name("BONG", dauer=3)
pruefe(aktuell(state), "BONG", "Animation läuft")
# BONG bringt dauer_s = 13 s mit: die Modellangabe 3 s verlängert nicht,
# sondern wird auf die eigene Länge gehoben (smilez, 15.11.2026 — ein Zug
# muss ganz laufen).
pruefe(ablauf_pruefen(state, jetzt=uhr() + 1), False, "vor Ablauf nichts")
pruefe(ablauf_pruefen(state, jetzt=uhr() + 3.5), False,
       "die kurze Modellangabe kürzt den Zug nicht")
pruefe(ablauf_pruefen(state, jetzt=uhr() + 13.5), True, "nach dem Zug zurückgenommen")
pruefe(aktuell(state), "IDLE", "das vorherige Gesicht gilt wieder")
pruefe(face.state.mood_bis, None, "keine Frist mehr gesetzt")
face.show_state("arbeitet")
pruefe(aktuell(state), "WORK", "danach darf der Zustand wieder ran")

print("== 7c. Der Ausdruck selbst bringt seine Dauer mit")
face, state, uhr = bau()
bong = face.moods.get("BONG")
pruefe(round(float(bong.get("dauer_s") or 0)), 13,
       "BONG hat dauer_s (ein Zug dauert 13 s)")

print("== 7d. Nach Ablauf bleibt der vorherige Ausdruck das Agentengesicht")
# Befund am Pi (15.11.2026, 05:00): das Modell sagte „das Gesicht bleibt WORK",
# auf dem Display stand danach IDLE. Ursache war `_ablauf` -- es leerte
# `_agent_mood`, und `wartet` fand dann kein Agentengesicht mehr.
face, state, uhr = bau()
face.set_by_name("ROCK")                 # endlos, kein Lauf, keine Sperre
face.set_by_name("BONG")                 # dauer_s = 13 s
pruefe(aktuell(state), "BONG", "Animation läuft")
ablauf_pruefen(state, jetzt=uhr() + 13.5)
pruefe(aktuell(state), "ROCK", "nach Ablauf gilt der vorherige Ausdruck")
face.show_state("wartet")
pruefe(aktuell(state), "ROCK",
       "und die Ruhe bleibt dort -- nicht IDLE")

print("== 7e. Ein Tätigkeitsausdruck kommt nach dem Zug nicht zurück")
# Zweiter Fund am Pi (15.11.2026, 05:50): set_face WORK -> set_face BONG
# (13 s) -> nach dem Zug stand wieder WORK, und niemand meldete je wieder
# 'wartet'. Das Display behauptete stundenlang Arbeit.
face, state, uhr = bau()
face.set_by_name("WORK")                  # Tätigkeitsausdruck, keine Frist
face.set_by_name("BONG")                  # dauer_s = 13 s
pruefe(aktuell(state), "BONG", "der Zug läuft")
ablauf_pruefen(state, jetzt=uhr() + 13.5)
pruefe(aktuell(state), "IDLE", "danach steht die Ruhe, nicht WORK")
face.show_state("wartet")
pruefe(aktuell(state), "IDLE", "und die Ruhe bleibt")

print("== 8. Ein gelöschter Ausdruck fällt in der Ruhe auf IDLE zurück")
face, state, uhr = bau()
face.set_by_name("CHAOS")
face.moods.remove("CHAOS")
face.show_state("wartet")
pruefe(aktuell(state), "IDLE",
       "'wartet' ist von der Haltezeit ausgenommen (gelöschter Ausdruck)")

print(f"\n{PASS} ok, {FAIL} FAIL")
sys.exit(1 if FAIL else 0)
