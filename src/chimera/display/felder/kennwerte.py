"""Kennwerte in einer Zeile: Modell, Anbieter, Akku.

Das ist der Platz für das, was man **wissen** will, ohne dass es den
Haupttext verdrängen darf — deshalb kleinere Schrift und die niedrigste
Priorität im Bereich. Steht nichts an, kostet das Feld kein Band
(``sichtbar``), der Text bekommt den Platz.

Die Reihenfolge ist fest und knapp: erst was antwortet (`modell`, sonst
`anbieter`), dann der Akku. Getrennt durch „·" — auf 240 px ist jedes
Trennzeichen Platz.
"""

from __future__ import annotations

from ..feld import Feld


def _zeile(kontext: dict) -> str:
    teile: list[str] = []
    modell = str(kontext.get("modell") or "").strip()
    anbieter = str(kontext.get("anbieter") or "").strip()
    if modell:
        teile.append(modell)
    elif anbieter:
        teile.append(anbieter)
    elif kontext.get("anbieter_weg"):
        teile.append("kein Modell")
    akku = kontext.get("akku")
    if isinstance(akku, (int, float)):
        teile.append(f"{int(round(float(akku)))}%")
    elif isinstance(akku, str) and akku.strip():
        teile.append(akku.strip())
    return " · ".join(teile)


def _zeichnen(flaeche, kontext: dict) -> None:
    """Zentriert; reicht eine Zeile nicht, wird umgebrochen (zwei Zeilen).

    smilez (15.11.2026): *„das Modell das in der Infoleiste angezeigt wird,
    steht nur halb da, der erste Teil ist nicht auf dem Display, sitzt zu weit
    links, müsste immer Center stehen und braucht Zeilenumbruch wenn zu lang
    und dann auch doppelte höhe"*. Vorher: linksbündig, eine Zeile, und was
    nicht passte, lief über den Rand (links abgeschnitten).
    """
    text = _zeile(kontext)
    if not text:
        return
    gross = max(10, int(flaeche.hoehe * 0.85))
    schrift = flaeche.schrift(gross)
    if schrift is not None and flaeche.passt(text, schrift):
        flaeche.text(text, groesse=gross, farbe=FELD.farbe,
                     ausrichtung="mitte", zeilen=1)
        return
    # Zwei Zeilen: die Schrift muss halb so hoch sein, sonst passen sie nicht.
    klein = max(9, int(flaeche.hoehe * 0.5 * 0.92))
    flaeche.text(text, groesse=klein, farbe=FELD.farbe,
                 ausrichtung="mitte", zeilen=2)


def _hoehe(kontext: dict) -> int:
    """Zwei Zeilen, wenn der Text in eine nicht passt (smilez, 15.11.2026)."""
    text = _zeile(kontext)
    if not text:
        return 13
    from ..feld import Flaeche

    schrift = Flaeche._laden(max(10, int(13 * 0.85)))
    if schrift is None:
        return 13
    try:
        from PIL import Image, ImageDraw
        zeichner = ImageDraw.Draw(Image.new("RGB", (1, 1)))
        breite = zeichner.textlength(text, font=schrift)
    except Exception:                          # noqa: BLE001
        return 13
    return 26 if breite > (240 - 4) else 13


FELD = Feld(
    name="kennwerte",
    titel="Modell · Anbieter · Akku",
    wunsch=13,
    mindestens=12,
    prioritaet=60,      # weicht zuerst, wenn der Platz knapp wird
    zeichnen=_zeichnen,
    ausrichtung="mitte",
    farbe=(150, 150, 150),
    hintergrund=(20, 20, 20),
    sichtbar=lambda k: bool(_zeile(k)),
    hoehe_fuer=_hoehe,
)
