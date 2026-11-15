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
from chimera.render.avatar import State  # noqa: E402

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

print("== 2. Der nächste Zustand übernimmt ihn NICHT (Haltezeit)")
face.show_state("arbeitet")
pruefe(aktuell(state), "CHILL", f"nach 'arbeitet' ({HALT_S:.0f} s Haltezeit)")
face.show_state("spricht")
pruefe(aktuell(state), "CHILL", "nach 'spricht'")
uhr.vor(HALT_S - 0.5)
face.show_state("denkt")
pruefe(aktuell(state), "CHILL", "kurz vor Ablauf der Frist")

print("== 3. Nach Ablauf der Frist gilt der Zustand wieder")
uhr.vor(1.0)
face.show_state("arbeitet")
pruefe(aktuell(state), "WORK", "nach der Frist übernimmt 'arbeitet'")

print("== 4. Ein Reflex bricht die Frist (Schreck blendet nicht ein)")
face, state, uhr = bau()
face.set_by_name("CHILL")
face.show_state("verwirrt")
pruefe(aktuell(state), "CHAOS", "Reflex geht sofort durch")
face.show_state("fehler")
pruefe(aktuell(state), "SAD", "auch 'fehler'")

print("== 5. Ein neuer Befehl verlängert die Frist")
face, state, uhr = bau()
face.set_by_name("CHILL")
uhr.vor(4.0)
face.set_by_name("ROCK")
uhr.vor(4.0)
face.show_state("arbeitet")
pruefe(aktuell(state), "ROCK", "zweiter Befehl setzt die Frist neu")

print("== 6. Am Turn-Ende steht wieder der Agentenausdruck")
face, state, uhr = bau()
face.set_by_name("ROCK")
uhr.vor(HALT_S + 1)
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

print("== 8. Ein gelöschter Ausdruck fällt in der Ruhe auf IDLE zurück")
face, state, uhr = bau()
face.set_by_name("CHAOS")
face.moods.remove("CHAOS")
face.show_state("wartet")
pruefe(aktuell(state), "IDLE",
       "'wartet' ist von der Haltezeit ausgenommen (gelöschter Ausdruck)")

print(f"\n{PASS} ok, {FAIL} FAIL")
sys.exit(1 if FAIL else 0)
