"""Obere Leiste: Temperatur mit Ampel und die zwei Sprachsymbole.

Auftrag smilez (15.11.2026): *„oben in der Infoleiste könnte die Temperatur
farblich mit Ampelsystem stehen, und ein Platzhalter für ein künftiges
Mikrofon- und Lautsprecher-Symbol für Sprachaus- und -eingabe anzuzeigen …
durchgestrichen solange es aus ist und nicht durchgestrichen sobald
aktiviert"*.

**Ampel statt Zahl.** Eine Temperatur ist nur dann nützlich, wenn man sie
nicht erst einordnen muss: grün bis 50 °C, gelb bis 65 °C, rot darüber. Die
Grenzen sind die des Geräts, nicht die eines PCs — der Zero 2 W läuft im
Betrieb bei 40–55 °C, und ab etwa 80 °C drosselt er (am Pi gemessen, siehe
``docs/HARDWARE-BEFUNDE.md``).

**Die Symbole sind Platzhalter mit Zustand.** Die Sprachschicht gibt es noch
nicht (``docs/ROADMAP.md``); die Schalter stehen bereit und werden später
von ihr gesetzt. Bis dahin sind beide aus und damit durchgestrichen — ehrlich
statt dekorativ. Wird einer aktiv, verschwindet der Strich.

Gezeichnet wird mit einfachen Formen auf dem Band: ein Mikrofon (Kapsel,
Bügel, Stiel) und ein Lautsprecher (Gehäuse plus zwei Schallbögen). Keine
Schriftzeichen — die sind bei 13 px nicht lesbar und werden je nach Schrift
zu Emoji.
"""

from __future__ import annotations

from ..feld import Feld

#: Grenzen der Ampel in Grad Celsius.
WARM = 50.0
HEISS = 65.0

GRUEN = (90, 200, 110)
GELB = (235, 190, 70)
ROT = (225, 80, 70)
AUS = (110, 110, 110)


def farbe_fuer(grad: float) -> tuple[int, int, int]:
    """Die Ampelfarbe zu einer Temperatur (reine Funktion, prüfbar)."""
    if grad >= HEISS:
        return ROT
    if grad >= WARM:
        return GELB
    return GRUEN


def _grad(kontext: dict) -> float | None:
    wert = kontext.get("temperatur")
    if isinstance(wert, bool) or not isinstance(wert, (int, float)):
        return None
    return float(wert)


def _zeichnen(flaeche, kontext: dict) -> None:
    from PIL import ImageDraw

    grad = _grad(kontext)
    zeichner = ImageDraw.Draw(flaeche.bild)
    oben = flaeche.oben + 1
    unten = flaeche.oben + flaeche.hoehe - 1
    mitte = (oben + unten) // 2
    x = flaeche.rand

    if grad is not None:
        schrift = flaeche.schrift(max(9, int(flaeche.hoehe * 0.8)))
        text = f"{int(round(grad))}°C"
        if schrift is not None:
            breite = int(zeichner.textlength(text, font=schrift))
            zeichner.text((x, oben), text, fill=farbe_fuer(grad), font=schrift)
            x += breite + 6

    # Mikrofon: Kapsel (abgerundet), Bügel, Stiel
    an = bool(kontext.get("mikrofon_an"))
    farbe = GRUEN if an else AUS
    kapsel_breit, kapsel_hoch = 4, max(4, flaeche.hoehe - 6)
    zeichner.rounded_rectangle(
        [x, oben, x + kapsel_breit, oben + kapsel_hoch], radius=2, fill=farbe)
    zeichner.arc([x - 2, oben + 1, x + kapsel_breit + 2, unten], 0, 180,
                 fill=farbe)
    zeichner.line([x + kapsel_breit // 2, unten - 1,
                   x + kapsel_breit // 2, unten], fill=farbe)
    if not an:
        # Durchgestrichen, solange aus (smilez: „durchgestrichen solange es
        # aus ist und nicht durchgestrichen sobald aktiviert").
        zeichner.line([x - 2, unten, x + kapsel_breit + 2, oben], fill=farbe)
    x += kapsel_breit + 8

    # Lautsprecher: Gehäuse (Rechteck + Spitze) und zwei Schallbögen
    an = bool(kontext.get("lautsprecher_an"))
    farbe = GRUEN if an else AUS
    zeichner.rectangle([x, mitte - 2, x + 2, mitte + 2], fill=farbe)
    zeichner.polygon([(x + 2, mitte - 2), (x + 5, mitte - 5),
                      (x + 5, mitte + 5), (x + 2, mitte + 2)], fill=farbe)
    if an:
        zeichner.arc([x + 2, mitte - 6, x + 10, mitte + 6], -60, 60, fill=farbe)
        zeichner.arc([x + 1, mitte - 8, x + 13, mitte + 8], -50, 50, fill=farbe)
    else:
        zeichner.line([x - 1, unten, x + 7, oben], fill=farbe)


FELD = Feld(
    name="oben",
    titel="Temperatur und Sprache",
    wunsch=13,
    mindestens=11,
    prioritaet=40,
    zeichnen=_zeichnen,
    seite="oben",
    ausrichtung="links",
    farbe=(150, 150, 150),
    hintergrund=(20, 20, 20),
    # Steht nur da, wenn es etwas zu zeigen gibt: eine Temperatur oder ein
    # Sprachzustand. Sonst kostet die Leiste kein Band.
    sichtbar=lambda k: (_grad(k) is not None
                        or "mikrofon_an" in k
                        or "lautsprecher_an" in k),
)
