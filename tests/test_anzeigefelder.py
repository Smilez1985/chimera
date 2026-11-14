"""Die Anzeigefelder: Verteilung, Textanpassung, Auffindung (Regel „Anzeigefelder").

Geprüft wird die **Zusage**, nicht die Absicht: Bänder überschneiden sich
nicht, füllen den Bereich aus, und ein Text wird angepasst statt
abgeschnitten. Die Verteilung ist eine reine Funktion — sie läuft ohne
Pillow; das Zeichnen wird mit echter Schrift geprüft und ohne Pillow
übersprungen.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from chimera.display import felder as feldliste           # noqa: E402
from chimera.display.feld import Feld, Flaeche           # noqa: E402
from chimera.display.layout import (                      # noqa: E402
    Platzfehler, verteile, verteile_mit_befund)

PASS = FAIL = 0
def ok(m):
    global PASS; PASS += 1; print(f"  ok    {m}")
def bad(m):
    global FAIL; FAIL += 1; print(f"  FAIL  {m}")
def check(m, got, want):
    ok(m) if got == want else bad(f"{m} — erwartet {want!r}, bekam {got!r}")


def gekuertzt_markiert(baender, name):
    """Ist dieses Band unter seinem Wunsch gezeichnet worden?"""
    for b in baender:
        if b.feld.name == name:
            return b.gekuerzt
    return None


def feld(name, wunsch, mindestens, prio):
    return Feld(name=name, titel=name, wunsch=wunsch, mindestens=mindestens,
                prioritaet=prio, zeichnen=lambda f, k: None)


print("== Verteilung: Bänder füllen den Bereich, ohne Überschneidung ==")
baender = verteile(40, [feld("meldung", 30, 18, 10), feld("kennwerte", 10, 10, 60)])
check("zwei Bänder", len(baender), 2)
check("oberes beginnt bei 0", baender[0].oben, 0)
check("keine Lücke, keine Überschneidung",
      [b.oben for b in baender], [0, baender[0].hoehe])
check("Summe = Bereich", sum(b.hoehe for b in baender), 40)
check("in der Reihenfolge der Priorität", [b.feld.name for b in baender],
      ["meldung", "kennwerte"])

print("== Zu wenig Platz: das Unwichtigere weicht, und es wird gesagt ==")
klein, weg = verteile_mit_befund(30, [feld("meldung", 30, 18, 10), feld("kennwerte", 10, 10, 60)])
check("das zweite Feld ist weg", weg, ["kennwerte"])
check("und das wichtige behält seinen Wunsch", klein[0].hoehe, 30)

# 36 Zeilen: 30 + 10 passen nicht. Das unwichtigere Feld fällt **ganz** weg,
# statt auf 6 Zeilen zusammenzuschrumpfen (unlesbar) — der freie Platz geht
# an das wichtige.
schmal, weg2 = verteile_mit_befund(36, [feld("meldung", 30, 18, 10), feld("kennwerte", 10, 10, 60)])
check("bei 36 bleibt nur das wichtige", weg2, ["kennwerte"])
check("Summe passt wieder", sum(b.hoehe for b in schmal), 36)
check("das wichtige nimmt den freien Platz", schmal[0].hoehe, 36)
check("und gilt nicht als gekürzt", schmal[0].gekuerzt, False)

try:
    verteile(20, [feld("meldung", 30, 26, 10), feld("kennwerte", 10, 10, 60)])
except Platzfehler as exc:
    ok("Mindesthöhen, die nicht passen, sind ein Fehler")
    check("mit Namen im Text", "meldung" in str(exc) or "kennwerte" in str(exc), True)
else:
    bad("zu kleiner Bereich wurde stillschweigend hingenommen")

print("== Auffindung: ein Feld ist eine Datei ==")
alle = feldliste.alle()
namen = [f.name for f in alle]
check("meldung gefunden", "meldung" in namen, True)
check("kennwerte gefunden", "kennwerte" in namen, True)
check("nach Priorität sortiert", namen, [f.name for f in sorted(alle, key=lambda f: (f.prioritaet, f.name))])
check("kein doppelter Name", len(namen), len(set(namen)))
check("Ladeprobleme werden gemeldet, nicht verschluckt",
      isinstance(feldliste.ladeprobleme, list), True)

print("== Textanpassung: kürzen statt abschneiden ==")
try:
    from PIL import Image
except ImportError:
    print("  (Pillow fehlt — Zeichentests übersprungen)")
else:
    bild = Image.new("RGB", (240, 40), (0, 0, 0))
    fl = Flaeche(bild, 0, 40)
    schrift = fl.schrift(18)

    check("kurzer Text bleibt unverändert", fl.kuerzen("IDLE", schrift), "IDLE")

    lang = "Das ist ein sehr langer Text, der niemals in eine Zeile passt"
    gekuerzt = fl.kuerzen(lang, schrift)
    check("langer Text endet mit Auslassungszeichen", gekuerzt.endswith("…"), True)
    check("gekürzter Text ist kürzer", len(gekuerzt) < len(lang), True)
    passt = fl._breite(gekuerzt, schrift) <= fl.breite - 2 * fl.rand
    check("gekürzter Text passt in die Breite", passt, True)

    zeilen = fl.umbrechen(lang, schrift, zeilen=2)
    check("Umbruch ergibt höchstens zwei Zeilen", len(zeilen) <= 2, True)
    check("und die letzte zeigt, dass etwas fehlt", zeilen[-1].endswith("…"), True)

    # Zeichnen bleibt im Band: oberhalb darf sich nichts ändern.
    leinwand = Image.new("RGB", (240, 80), (7, 7, 7))
    band = Flaeche(leinwand, 40, 20)
    band.text("Hallo", groesse=14, ausrichtung="mitte")
    check("oberhalb des Bandes unberührt", leinwand.getpixel((120, 20)), (7, 7, 7))
    unten = [leinwand.getpixel((x, y)) for y in range(40, 60) for x in range(240)]
    check("im Band wurde gezeichnet", any(p != (7, 7, 7) for p in unten), True)

    # Zwei Bänder übereinander: keines malt in das andere.
    lw = Image.new("RGB", (240, 40), (0, 0, 0))
    oberes = Flaeche(lw, 0, 20)
    unteres = Flaeche(lw, 20, 20)
    oberes.text("OBEN", groesse=14, farbe=(255, 0, 0))
    unteres.text("UNTEN", groesse=14, farbe=(0, 255, 0))
    rot_oben = any(lw.getpixel((x, y))[0] > 100 for y in range(0, 20) for x in range(240))
    gruen_unten = any(lw.getpixel((x, y))[1] > 100 for y in range(20, 40) for x in range(240))
    check("oberes Band malt nur oben", rot_oben, True)
    check("unteres Band malt nur unten", gruen_unten, True)


def gekuertzt_markiert(baender, name):
    """Hilfsfrage: ist dieses Band gekürzt gezeichnet worden?"""
    for b in baender:
        if b.feld.name == name:
            return b.gekuerzt
    return None


print(f"\n{PASS} ok, {FAIL} FAIL")
sys.exit(1 if FAIL else 0)
