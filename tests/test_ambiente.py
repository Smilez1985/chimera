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


ALLE = {"COFFEE", "YAWN", "STRETCH", "CHILL", "ROCK", "MUSIC", "BONG", "JOINT",
        "HIPHOP", "JAZZ", "CLASSIC", "REGGAE", "HOUSE", "TV", "POPCORN", "DANCE",
        "NATURE", "WEATHER", "EXERCISE", "MEDITATE"}


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
pruefe(zweite in kandidaten(20), True,
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

print("== 10. Keine feste Reihenfolge (Fund 15.11.2026 am Pi)")
# Mit 20 min Abstand und 90 min Sperre blieb je Takt genau ein Kandidat
# uebrig: aus dem Wurf wurde ROCK -> CHILL -> MUSIC -> ROCK, und smilez sah
# "seit Stunden das face chill". Gemessen wird hier am **echten** Aufruf --
# die Zahl der Moeglichkeiten steht in der Protokollzeile von `tick` selbst.
# (Ein Nachbau der Regel im Test hat am 15.11. die Mutation "nur-ein-
# kandidat" gruen gelassen: der Test prueft dann sich selbst.)
import logging  # noqa: E402


class Mitschrift(logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=logging.INFO)
        self.zeilen = []

    def emit(self, record) -> None:
        self.zeilen.append(record.args)


logger = logging.getLogger("chimera.agent.ambiente")
logger.setLevel(logging.INFO)
mitschrift = Mitschrift()
logger.addHandler(mitschrift)
try:
    uhr = Uhr()
    rnd = __import__("random").Random(11)
    amb = Ambiente(uhr=uhr, zufall=rnd.random)
    wahlen, moeglich = [], []
    for _ in range(6 * 3600 // 30):               # 6 Stunden Takt
        uhr.vor(30)
        wahl = amb.tick(stunde=6 + int((uhr() - 1000.0) // 3600) % 3 + 6,
                        frei=True, haelt=False, vorhanden=ALLE)
        if wahl:
            wahlen.append(wahl)
finally:
    logger.removeHandler(mitschrift)

# (wahl, stunde, kandidaten, namen) -- args der Protokollzeile
moeglich = [int(a[2]) for a in mitschrift.zeilen]
pruefe(len(wahlen) >= 8, True, f"in 6 h passiert etwas ({len(wahlen)} Aktionen)")
pruefe(bool(moeglich) and min(moeglich) >= 2, True,
       f"jede Wahl hatte mindestens zwei Moeglichkeiten {sorted(set(moeglich))}")
pruefe(any(a != b for a, b in zip(wahlen, wahlen[1:])), True,
       f"die Reihenfolge wechselt ({wahlen[:6]})")

print("== 11. Nie zweimal derselbe Ausdruck hintereinander")
# Zwei Namen im Fenster, beide nach 36 min wieder frei. Ohne die Regel
# "nie zweimal hintereinander" faellt der Wurf bei zufall=0 wieder auf den
# ersten -- das Gesicht staende zweimal nacheinander still.
amb, uhr = bau((0.0, 0.0))
amb.zufall = lambda: 0.0
erste = amb.tick(stunde=12, frei=True, haelt=False,
                 vorhanden={"ROCK", "MUSIC"})
uhr.vor(SPERRE_JE_AUSDRUCK_S + 60)
zweite = amb.tick(stunde=12, frei=True, haelt=False,
                  vorhanden={"ROCK", "MUSIC"})
pruefe(erste is not None and zweite is not None and zweite != erste, True,
       f"zwei Wahlen, verschiedene Ausdruecke ({erste} -> {zweite})")

print("== 12. Auch bei duennem Fenster bleiben zwei Moeglichkeiten")
# Die Bibliothek darf kleiner sein als die Tabelle (DESIGN). Stehen nur drei
# Namen im Fenster -- wie am Pi --, laeuft die Sperre nach zwei Aktionen der
# Auswahl davon: ohne den Rueckfall bleibt genau einer uebrig, und der
# "Wurf" ist wieder eine feste Reihenfolge.
uhr = Uhr()
amb = Ambiente(uhr=uhr, zufall=__import__("random").Random(5).random)
mitschrift.zeilen.clear()
logger.addHandler(mitschrift)
try:
    for _ in range(3 * 3600 // 30):
        uhr.vor(30)
        amb.tick(stunde=20, frei=True, haelt=False,
                 vorhanden={"BONG", "JOINT", "CHILL"})
finally:
    logger.removeHandler(mitschrift)
zahlen = [int(a[2]) for a in mitschrift.zeilen]
pruefe(len(zahlen) >= 3, True, f"auch im duennen Fenster passiert etwas ({len(zahlen)})")
pruefe(bool(zahlen) and min(zahlen) >= 2, True,
       f"immer zwei zur Wahl {sorted(set(zahlen))}")

print("== 13. BONG, JOINT und COFFEE sind zu Gast, nicht verschwunden")
# Fund smilez (15.11.2026): *"warum hast du die idle Animationen wie Joint,
# bong und Kaffee ignoriert?"* -- sie standen im Fenster, kamen bei zehn
# Musiknamen aber nie dran. Jetzt sind sie Gaeste mit kleinem Gewicht.
from chimera.agent.ambiente import gewicht  # noqa: E402
pruefe("BONG" in kandidaten(13), True, "BONG ist tagsueber im Fenster")
pruefe("JOINT" in kandidaten(13), True, "JOINT ist tagsueber im Fenster")
pruefe("COFFEE" in kandidaten(13), True, "COFFEE ist tagsueber im Fenster")
pruefe(gewicht("BONG", 13) < gewicht("ROCK", 13), True,
       f"BONG ist seltener als ROCK ({gewicht('BONG', 13)} < {gewicht('ROCK', 13)})")
pruefe(gewicht("BONG", 2), 0.0, "nachts gibt es gar nichts")
pruefe("BONG" in kandidaten(20), True, "abends bleibt BONG zu Hause")
pruefe(gewicht("BONG", 20), 1.0, "abends ist BONG kein Gast mehr")

# Ueber einen Tag gezaehlt: BONG kommt vor, aber deutlich seltener.
uhr = Uhr()
amb = Ambiente(uhr=uhr, zufall=__import__("random").Random(23).random)
zaehler = {}
mitschrift.zeilen.clear()
logger.addHandler(mitschrift)
try:
    for _ in range(8 * 3600 // 30):           # 8 Stunden tagsueber
        uhr.vor(30)
        wahl = amb.tick(stunde=13, frei=True, haelt=False, vorhanden=ALLE)
        if wahl:
            zaehler[wahl] = zaehler.get(wahl, 0) + 1
finally:
    logger.removeHandler(mitschrift)
gaeste = sum(zaehler.get(n, 0) for n in ("BONG", "JOINT", "COFFEE"))
pruefe(gaeste > 0, True, f"die Gaeste kommen tagsueber vor ({gaeste}x)")
pruefe(gaeste < zaehler.get("ROCK", 0) + zaehler.get("HOUSE", 0), True,
       f"... aber seltener als die Musik ({gaeste} < "
       f"{zaehler.get('ROCK', 0) + zaehler.get('HOUSE', 0)})")

print()
print(f"Ergebnis: {PASS} ok, {FAIL} fehlgeschlagen")
sys.exit(0 if FAIL == 0 else 1)
