"""Tests für die Auflösung konkurrierender Anzeigequellen (Regel 7c/7d).

Ausgeführt mit:  PYTHONPATH=src python3 tests/test_arbiter.py

Der Verwalter bekommt die Zeit von außen (Regel 7d). Darum schläft hier
kein Test: Zeitpunkte werden gesetzt, nicht abgewartet. Ein Test, der eine
Sekunde wartet, um einen Ablauf zu prüfen, ist langsam und trotzdem
unzuverlässig.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from chimera.arbiter import MIN_ABSTAND, Arbiter, Slot  # noqa: E402

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


print("=== Auflösung konkurrierender Quellen ===")

# --- Grundfall --------------------------------------------------------------

a = Arbiter()
pruefe("leer: kein Gewinner", a.gewinner(0), None)
pruefe("leer: Länge 0", len(a), 0)

a.setzen(Slot("stimmung", 20, "ruhig"), 1000)
g = a.gewinner(1000)
pruefe("einziger Eintrag gewinnt", g.quelle if g else None, "stimmung")

a.setzen(Slot("alarm", 90, "zu heiss"), 1000)
g = a.gewinner(1000)
pruefe("höhere Priorität gewinnt", g.quelle if g else None, "alarm")
pruefe("beide sind aktiv", len(a.aktive(1000)), 2)

# --- Ein Platz je Quelle ----------------------------------------------------

a.setzen(Slot("stimmung", 20, "fröhlich"), 1100)
pruefe("Quelle verdrängt sich selbst, keine zweite Zeile", len(a), 2)
inhalte = [s.inhalt for s in a.aktive(1100) if s.quelle == "stimmung"]
pruefe("der neue Inhalt gilt", inhalte, ["fröhlich"])

# --- Verfall ----------------------------------------------------------------

a2 = Arbiter()
a2.setzen(Slot("kurz", 50, "weg gleich", laufzeit_ms=1000), 0)
wahr("vor Ablauf da", a2.gewinner(999) is not None)
pruefe("nach Ablauf weg", a2.gewinner(1000), None)
pruefe("verfallener Slot wird ausgeräumt", len(a2), 0)

a3 = Arbiter()
a3.setzen(Slot("bleibt", 50, "ohne Laufzeit"), 0)
wahr("ohne Laufzeit bleibt beliebig lange", a3.gewinner(10**9) is not None)

# --- Erneuerungsbedingung ---------------------------------------------------

zu_heiss = {"wert": True}
a4 = Arbiter()
a4.setzen(
    Slot("hitze", 90, "zu heiss", laufzeit_ms=1000,
         erneuern=lambda: zu_heiss["wert"]),
    0,
)
wahr("solange die Bedingung gilt, bleibt der Eintrag",
     a4.gewinner(50_000) is not None)
zu_heiss["wert"] = False
pruefe("fällt die Bedingung weg, verfällt er von selbst",
       a4.gewinner(50_000), None)

# Eine kaputte Bedingung darf nicht hängenbleiben.
def kaputt():
    raise RuntimeError("Sensor weg")

a5 = Arbiter()
a5.setzen(Slot("kaputt", 90, "x", laufzeit_ms=100, erneuern=kaputt), 0)
pruefe("kaputte Bedingung: Eintrag verfällt, statt zu bleiben",
       a5.gewinner(200), None)

# --- Auflösung in drei Stufen ----------------------------------------------

a6 = Arbiter()
a6.setzen(Slot("alt", 50, "alt"), 100)
a6.setzen(Slot("neu", 50, "neu"), 200)
g = a6.gewinner(300)
pruefe("bei gleicher Priorität gewinnt der jüngere", g.quelle, "neu")

# Dritte Stufe: gleiche Priorität UND gleicher Zeitstempel.
a7 = Arbiter(reihenfolge=("bbb", "aaa"))
a7.setzen(Slot("aaa", 50, "a"), 100)
a7.setzen(Slot("bbb", 50, "b"), 100)
g = a7.gewinner(100)
pruefe("bei Gleichstand entscheidet die feste Reihenfolge", g.quelle, "bbb")

# Und das Ergebnis muss reproduzierbar sein -- unabhängig von der
# Einfügereihenfolge. Genau dafür ist die dritte Stufe da.
a8 = Arbiter(reihenfolge=("bbb", "aaa"))
a8.setzen(Slot("bbb", 50, "b"), 100)
a8.setzen(Slot("aaa", 50, "a"), 100)
pruefe("umgekehrt eingetragen, gleiches Ergebnis",
       a8.gewinner(100).quelle, "bbb")

# Unbekannte Quellen kommen hinten, aber festgelegt.
a9 = Arbiter(reihenfolge=("bekannt",))
a9.setzen(Slot("unbekannt_z", 50, "z"), 100)
a9.setzen(Slot("unbekannt_a", 50, "a"), 100)
pruefe("unbekannte Quellen nach Namen sortiert",
       a9.gewinner(100).quelle, "unbekannt_a")

# --- Löschen ----------------------------------------------------------------

a10 = Arbiter()
a10.setzen(Slot("x", 50, "x"), 0)
pruefe("löschen meldet Erfolg", a10.loeschen("x"), True)
pruefe("zweites Löschen meldet, dass nichts da war", a10.loeschen("x"), False)

# --- Unveränderlichkeit -----------------------------------------------------

s = Slot("q", 10, "inhalt")
try:
    s.prioritaet = 99  # type: ignore[misc]
    wahr("Slot ist unveränderlich", False)
except Exception:
    wahr("Slot ist unveränderlich", True)

# --- Abstandsprüfung --------------------------------------------------------

pruefe("saubere Abstände: keine Beanstandung",
       Arbiter.abstaende_pruefen({"a": 10, "b": 20, "c": 90}), [])

eng = Arbiter.abstaende_pruefen({"a": 10, "b": 15})
wahr("zu enge Abstände werden beanstandet", len(eng) == 1)
wahr("die Beanstandung nennt den Mindestabstand", str(MIN_ABSTAND) in eng[0])

doppelt = Arbiter.abstaende_pruefen({"a": 50, "b": 50})
wahr("doppelt vergebene Priorität wird beanstandet", len(doppelt) >= 1)
wahr("die Beanstandung nennt beide Namen",
     "a" in doppelt[0] and "b" in doppelt[0])

# --- Gegenproben ------------------------------------------------------------
#
# Ein Test, von dem niemand gezeigt hat, dass er rot werden kann, ist eine
# Zusage ohne Beleg. Hier wird die kaputte Variante nachgebaut und geprüft,
# dass sie das Ergebnis ändert.

print()
print("=== Gegenproben ===")


class OhneDritteStufe(Arbiter):
    """Der Verwalter ohne dritte Auflösungsstufe.

    Genau die Fassung, die auf den ersten Blick genügt: Priorität und
    Zeitstempel. Bei echtem Gleichstand entscheidet dann die
    Einfügereihenfolge des Wörterbuchs -- und das Ergebnis dreht sich, wenn
    man die Einträge tauscht.
    """

    def _rang(self, slot):
        return (-slot.prioritaet, -slot.gesetzt_ms)


b1 = OhneDritteStufe(reihenfolge=("bbb", "aaa"))
b1.setzen(Slot("aaa", 50, "a"), 100)
b1.setzen(Slot("bbb", 50, "b"), 100)

b2 = OhneDritteStufe(reihenfolge=("bbb", "aaa"))
b2.setzen(Slot("bbb", 50, "b"), 100)
b2.setzen(Slot("aaa", 50, "a"), 100)

wahr("Gegenprobe: ohne dritte Stufe hängt das Ergebnis an der Reihenfolge",
     b1.gewinner(100).quelle != b2.gewinner(100).quelle)

# Und die Umkehrung: mit dritter Stufe darf genau das NICHT passieren.
c1 = Arbiter(reihenfolge=("bbb", "aaa"))
c1.setzen(Slot("aaa", 50, "a"), 100)
c1.setzen(Slot("bbb", 50, "b"), 100)
c2 = Arbiter(reihenfolge=("bbb", "aaa"))
c2.setzen(Slot("bbb", 50, "b"), 100)
c2.setzen(Slot("aaa", 50, "a"), 100)
wahr("Gegenprobe: mit dritter Stufe ist das Ergebnis gleich",
     c1.gewinner(100).quelle == c2.gewinner(100).quelle)

# Gegenprobe zur Abstandsprüfung: Findet sie einen echten Verstoß?
wahr("Gegenprobe: die Abstandsprüfung schlägt bei Abstand 1 an",
     len(Arbiter.abstaende_pruefen({"a": 50, "b": 51})) == 1)
wahr("Gegenprobe: und nicht bei Abstand 10",
     Arbiter.abstaende_pruefen({"a": 50, "b": 60}) == [])

print()
print(f"Ergebnis: {OK} ok, {BAD} fehlgeschlagen")
sys.exit(1 if BAD else 0)
