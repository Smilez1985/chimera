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
    text = _zeile(kontext)
    if not text:
        return
    flaeche.text(text, groesse=max(10, int(flaeche.hoehe * 0.85)),
                 farbe=FELD.farbe, ausrichtung="links", zeilen=1)


FELD = Feld(
    name="kennwerte",
    titel="Modell · Anbieter · Akku",
    wunsch=13,
    mindestens=12,
    prioritaet=60,      # weicht zuerst, wenn der Platz knapp wird
    zeichnen=_zeichnen,
    ausrichtung="links",
    farbe=(150, 150, 150),
    hintergrund=(20, 20, 20),
    sichtbar=lambda k: bool(_zeile(k)),
)
